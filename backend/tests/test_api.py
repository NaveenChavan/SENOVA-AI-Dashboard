"""
End-to-end API tests, with the security rules as the main subject.

What is proven here
-------------------
* the full upload → confirm-mapping → analyse flow works over HTTP;
* a second signed-in user cannot read another user's file (the IDOR fix) and
  gets an indistinguishable 404;
* malformed file ids are rejected before touching the filesystem;
* analysing before confirming a mapping returns 409, not a wrong guess;
* filter/dimension/measure inputs outside the allowed registry return 422;
* pagination, horizon and top-N caps are enforced by the schema;
* every Pro endpoint answers for a filtered slice, and the PDF really builds.

Auth is stubbed by overriding the ``get_current_user`` dependency, which lets
one test act as two different users without any Firebase involvement.
"""

from __future__ import annotations

import io
import os
import tempfile

import pandas as pd
import pytest

# Point uploads at a throwaway directory and disable Firebase before the app
# module (and therefore the config module) is imported.
_TEMP_UPLOAD_DIR = tempfile.mkdtemp(prefix="senova-test-uploads-")
os.environ["UPLOAD_DIR"] = _TEMP_UPLOAD_DIR
os.environ["DISABLE_AUTH"] = "true"

from fastapi.testclient import TestClient  # noqa: E402  (import after env setup)

from app.main import app  # noqa: E402
from app.services import frame_cache  # noqa: E402
from app.services import tier2_gemini  # noqa: E402
from app.utils.auth_verifier import get_current_user  # noqa: E402
from tests.conftest import INTRUDER, OWNER  # noqa: E402  (shared identity fixtures)

#: A well-formed but non-existent id (32 hex chars), for "not found" cases.
UNKNOWN_FILE_ID = "0" * 32


def _act_as(user: str) -> None:
    """Swap the authenticated identity for the next request."""
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture
def uploaded(client, raw_sales_frame, mapping):
    """Upload the synthetic export and confirm its mapping; returns the file id."""
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    response = client.post(
        "/upload/",
        files={"file": ("shop-export.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 201, response.text
    preview = response.json()

    confirm = client.post(f"/upload/{preview['file_id']}/confirm-mapping", json={"mapping": mapping})
    assert confirm.status_code == 200, confirm.text
    return preview["file_id"]


# ── Upload flow ─────────────────────────────────────────────────────────────


def test_upload_returns_mapping_preview(client, raw_sales_frame):
    """Step 1 must guess the columns and advertise the optional fields."""
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    response = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert response.status_code == 201
    body = response.json()
    guesses = {row["raw_column"]: row["suggested_field"] for row in body["detected_columns"]}

    assert guesses["Bill Date"] == "Date"
    assert guesses["Qty."] == "Quantity"
    assert guesses["Purchase Rate"] == "Cost Price"
    assert guesses["Remarks"] is None
    assert "Stock On Hand" in body["optional_fields"]
    assert body["field_help"]["Line Total"]
    assert len(body["sample_rows"]) == 5


def test_upload_carries_the_legacy_confidence_string(client, raw_sales_frame):
    """``confidence`` must stay the string the old frontend badge renders. The
    pipeline adds fields beside it; it does not repurpose it, because
    ConfidenceBadge keys off these exact three values."""

    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    response = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    by_name = {row["raw_column"]: row for row in response.json()["detected_columns"]}
    assert by_name["Bill Date"]["confidence"] == "exact"
    assert by_name["Remarks"]["confidence"] == "none"
    # The additive fields arrive alongside it.
    assert by_name["Bill Date"]["confidence_score"] == 1.0
    assert by_name["Bill Date"]["confidence_band"] in {"high", "medium", "low"}
    assert by_name["Bill Date"]["source"] in {"local", "gemini", "fallback"}
    assert isinstance(by_name["Bill Date"]["needs_review"], bool)


def test_upload_reports_pipeline_timings(client, raw_sales_frame):
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    body = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    ).json()

    timings = body["pipeline_timings"]
    assert timings["tier1_ms"] > 0
    assert timings["total_ms"] >= timings["tier1_ms"]
    # AI is off in tests, so Tier 2 must report zero rather than a guess.
    assert timings["tier2_ms"] == 0.0


def test_confirm_mapping_reports_pandas_timing(client, raw_sales_frame, mapping):
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    file_id = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    ).json()["file_id"]

    response = client.post(f"/upload/{file_id}/confirm-mapping", json={"mapping": mapping})
    body = response.json()

    assert response.status_code == 200
    assert body["valid_count"] > 0
    assert body["date_range"]["span_days"] == 90
    assert {"Branch", "Discount", "Payment Mode", "Stock On Hand"} <= set(body["optional_fields"])

    # confirm-mapping is the compute step, so it reports the normalisation cost
    # under the same timings envelope as upload's classification cost.
    assert body["pipeline_timings"]["pandas_ms"] > 0
    assert body["pipeline_timings"]["total_ms"] >= body["pipeline_timings"]["pandas_ms"]


# ── AI consent gate ──────────────────────────────────────────────────────────
#
# These are the tests that matter most in this file. Everything else here is
# about correctness; these are about a promise to the shopkeeper — that their
# data does not leave the server unless they said yes, on this request.


@pytest.fixture
def gemini_reachable(monkeypatch):
    """
    Make Gemini *available* but ensure every attempt would be recorded.

    A consent test that runs with AI switched off proves nothing, because Tier 2
    would skip for the other reason. So the operator switch and key are forced
    on, and ``httpx.AsyncClient`` is replaced with a counter that raises. The
    count is the assertion: a Gemini attempt is an outbound request.
    """
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")

    attempts: list[str] = []

    class _TrippedClient:
        def __init__(self, *args, **kwargs):
            attempts.append("client")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            attempts.append("post")
            raise AssertionError("A Gemini request was attempted without consent.")

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _TrippedClient)
    return attempts


def _upload(client, frame, **form):
    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    return client.post(
        "/upload/",
        files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")},
        data=form,
    )


def test_consent_false_makes_zero_gemini_calls(client, gemini_reachable):
    """The headline guarantee. Consent withheld, AI enabled server-side, and a
    file whose headers force an escalation — the whole pipeline still returns a
    complete mapping and nothing goes out over the wire."""

    # Every header is unknown, so Tier 1 must escalate every column if Tier 2 is
    # going to run at all. If this test ever stops escalating, it stops proving
    # anything, which is why it asserts the columns were left for review.
    frame = pd.DataFrame(
        {
            "Zorp Factor": ["alpha", "beta"],
            "Quibble": ["x", "y"],
        }
    )

    response = _upload(client, frame, ai_consent="false")

    assert response.status_code == 201
    assert gemini_reachable == [], "Gemini was contacted despite ai_consent=false"

    # The degradation is honest, not silent: these columns are visibly unmapped.
    rows = response.json()["detected_columns"]
    assert all(row["suggested_field"] is None for row in rows)
    assert all(row["source"] == "fallback" for row in rows)
    assert all(row["needs_review"] is True for row in rows)


def test_omitting_ai_consent_is_treated_as_declining(client, gemini_reachable):
    """An older client that doesn't know about consent must not be able to opt
    itself in by silence. The field defaults to False precisely so absence can
    never mean yes."""

    frame = pd.DataFrame({"Zorp Factor": ["alpha", "beta"]})

    response = _upload(client, frame)  # no ai_consent sent at all

    assert response.status_code == 201
    assert gemini_reachable == []


def test_consent_false_yields_no_ai_notice(client, gemini_reachable):
    """Declining is a normal path, not an error. It must not produce the
    'Gemini unavailable' banner, which would imply something broke."""

    frame = pd.DataFrame({"Zorp Factor": ["alpha", "beta"]})
    response = _upload(client, frame, ai_consent="false")

    body = response.json()
    assert body["ai_notice"] is None or "not approved" in body["ai_notice"]["message"]
    # The flag is still reported so the UI knows consent is worth offering.
    assert body["ai_enabled"] is True


def test_unsupported_file_type_is_rejected(client):
    response = client.post(
        "/upload/", files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    )
    assert response.status_code == 400


# ── Dynamic schema endpoint ──────────────────────────────────────────────────


def test_schema_reports_what_the_file_supports(client, uploaded):
    body = client.post(f"/analytics/{uploaded}/schema").json()

    assert body["kpi_cards"] and body["charts"] and body["measures"]
    assert body["missing_required_columns"] == []
    assert body["date_range"]["span_days"] == 90


def test_schema_finds_the_optional_columns_this_file_mapped(client, uploaded):
    """The conftest export maps Branch, Discount, Payment Mode and Stock On Hand.
    A false negative here would tell a paying shop it cannot see data it uploaded,
    which is worse than not offering the panel at all."""
    body = client.post(f"/analytics/{uploaded}/schema").json()

    cards = {c["key"]: c for c in body["kpi_cards"]}
    dimensions = {d["key"]: d for d in body["dimensions"]}
    assert cards["discount"]["available"] is True
    assert cards["stock_on_hand"]["available"] is True
    assert dimensions["branch"]["available"] is True
    assert dimensions["payment_mode"]["available"] is True


def test_schema_reports_the_confirmed_mapping(client, uploaded):
    """The UI joins schema entries back onto mapping-screen rows by name, so the
    mapping has to travel with the schema."""
    body = client.post(f"/analytics/{uploaded}/schema").json()
    assert body["mapped_columns"]["Bill Date"] == "Date"


def test_schema_never_reports_unavailable_without_a_reason(client, uploaded):
    body = client.post(f"/analytics/{uploaded}/schema").json()

    for group in ("kpi_cards", "charts", "dimensions", "measures"):
        for entry in body[group]:
            if not entry["available"]:
                assert entry["reason"], f"{entry['key']} unavailable with no reason"


def test_schema_makes_no_gemini_call(client, uploaded):
    """The schema is pure introspection — which columns exist. It must never reach
    the network, even with AI enabled server-side and consent implied."""
    from app.services import tier2_gemini

    attempts: list[str] = []

    class _Tripped:
        def __init__(self, *a, **k):
            attempts.append("client")

    original_enabled = tier2_gemini.AI_ASSIST_ENABLED
    original_key = tier2_gemini.GEMINI_API_KEY
    tier2_gemini.AI_ASSIST_ENABLED = True
    tier2_gemini.GEMINI_API_KEY = "test-key-not-real"
    tier2_gemini.httpx.AsyncClient = _Tripped
    try:
        response = client.post(f"/analytics/{uploaded}/schema")
    finally:
        tier2_gemini.AI_ASSIST_ENABLED = original_enabled
        tier2_gemini.GEMINI_API_KEY = original_key

    assert response.status_code == 200
    assert attempts == []


def test_schema_requires_a_confirmed_mapping(client, raw_sales_frame):
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    file_id = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    ).json()["file_id"]

    response = client.post(f"/analytics/{file_id}/schema")
    assert response.status_code == 409
    assert "confirm-mapping" in response.json()["detail"]


def test_schema_is_not_readable_by_another_user(client, uploaded):
    """Same rule as every other analytics route: someone else's file looks
    missing rather than forbidden."""
    _act_as(INTRUDER)
    response = client.post(f"/analytics/{uploaded}/schema")

    assert response.status_code == 404
    assert "not belong" not in response.text.lower()


# ── Security ────────────────────────────────────────────────────────────────


def test_another_user_cannot_read_the_file(client, uploaded):
    """The IDOR fix: a valid id in the wrong hands must look like 'not found'."""
    _act_as(INTRUDER)

    for method, path, kwargs in [
        ("get", f"/analytics/{uploaded}", {}),
        ("get", f"/analytics/{uploaded}/dimensions", {}),
        ("post", f"/analytics/{uploaded}/summary", {"json": {"time_filter": "all"}}),
        ("post", f"/analytics/{uploaded}/insights", {"json": {"time_filter": "all"}}),
        ("get", f"/analytics/{uploaded}/report.pdf", {}),
        ("get", f"/process/{uploaded}", {}),
    ]:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, f"{method.upper()} {path} leaked to another user"
        # The message must not confirm that the file exists.
        assert "not belong" not in response.text.lower()


def test_intruder_cannot_overwrite_the_mapping(client, uploaded, mapping):
    """Confirm-mapping is an owner-only action too."""
    _act_as(INTRUDER)
    response = client.post(f"/upload/{uploaded}/confirm-mapping", json={"mapping": mapping})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../.env",
        "..%2F..%2Fsecrets",
        "not-a-uuid",
        "0" * 31,  # too short
        "g" * 32,  # not hex
    ],
)
def test_malformed_file_ids_are_rejected(client, bad_id):
    """Anything that isn't a generated id is refused before any file access."""
    response = client.get(f"/analytics/{bad_id}")
    assert response.status_code in (404, 422)


def test_unknown_file_returns_404(client):
    response = client.get(f"/analytics/{UNKNOWN_FILE_ID}")
    assert response.status_code == 404


def test_analysis_before_mapping_returns_409(client, raw_sales_frame):
    """We never guess a shop's columns behind their back."""
    csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
    file_id = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    ).json()["file_id"]

    response = client.get(f"/analytics/{file_id}")
    assert response.status_code == 409
    assert "confirm-mapping" in response.json()["detail"]


def test_unknown_filter_dimension_returns_422(client, uploaded):
    response = client.post(
        f"/analytics/{uploaded}/summary",
        json={"time_filter": "all", "filters": {"__proto__": ["x"]}},
    )
    assert response.status_code == 422


def test_unknown_chart_dimension_returns_422(client, uploaded):
    response = client.post(
        f"/analytics/{uploaded}/chart-data",
        json={"time_filter": "all", "dimension": "nonsense", "measure": "revenue"},
    )
    assert response.status_code == 422


def test_oversized_filter_payload_is_rejected(client, uploaded):
    """Bounded filters keep one request from becoming a server-wide problem."""
    response = client.post(
        f"/analytics/{uploaded}/summary",
        json={"time_filter": "all", "filters": {"category": [f"c{i}" for i in range(200)]}},
    )
    assert response.status_code == 422


def test_out_of_range_parameters_are_rejected(client, uploaded):
    """top_n, page_size and horizon all have documented caps."""
    assert (
        client.post(
            f"/analytics/{uploaded}/chart-data",
            json={"dimension": "item", "measure": "revenue", "top_n": 5000},
        ).status_code
        == 422
    )
    assert (
        client.post(f"/analytics/{uploaded}/ledger", json={"page": 0}).status_code == 422
    )
    assert (
        client.post(f"/analytics/{uploaded}/forecast", json={"horizon": 400}).status_code == 422
    )


def test_custom_range_requires_both_ends(client, uploaded):
    response = client.post(
        f"/analytics/{uploaded}/summary",
        json={"time_filter": "custom", "start_date": "2026-02-01"},
    )
    assert response.status_code == 422


# ── Pro endpoints ───────────────────────────────────────────────────────────


def test_summary_respects_filters(client, uploaded):
    """Filtering by branch must reduce revenue below the unfiltered figure."""
    everything = client.post(f"/analytics/{uploaded}/summary", json={"time_filter": "all"}).json()
    one_branch = client.post(
        f"/analytics/{uploaded}/summary",
        json={"time_filter": "all", "filters": {"branch": ["MG Road"]}},
    ).json()

    assert everything["summary"]["revenue"]["value"] > one_branch["summary"]["revenue"]["value"] > 0
    assert one_branch["daily_trend"]
    assert one_branch["top_items"]


def test_trend_arrows_have_a_previous_period(client, uploaded):
    """A 30-day window must compare against the 30 days before it."""
    body = client.post(f"/analytics/{uploaded}/summary", json={"time_filter": "30days"}).json()
    assert body["summary"]["revenue"]["trend_percentage"] != 0.0


def test_dimensions_endpoint_lists_only_present_dimensions(client, uploaded):
    body = client.get(f"/analytics/{uploaded}/dimensions").json()
    keys = {dimension["key"] for dimension in body["dimensions"]}

    assert {"category", "item", "branch", "payment_mode"} <= keys
    assert "salesperson" not in keys
    assert body["date_range"]["span_days"] == 90


@pytest.mark.parametrize(
    "dimension", ["category", "item", "day", "weekday", "month", "branch", "payment_mode"]
)
def test_chart_data_works_for_every_dimension(client, uploaded, dimension):
    response = client.post(
        f"/analytics/{uploaded}/chart-data",
        json={"time_filter": "all", "dimension": dimension, "measure": "revenue", "top_n": 6},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["points"]
    assert body["dimension_label"]


@pytest.mark.parametrize(
    "measure", ["revenue", "profit", "cost", "units", "transactions", "discount", "margin_pct", "avg_price"]
)
def test_chart_data_works_for_every_measure(client, uploaded, measure):
    response = client.post(
        f"/analytics/{uploaded}/chart-data",
        json={"time_filter": "all", "dimension": "category", "measure": measure},
    )
    assert response.status_code == 200
    assert response.json()["measure"] == measure


def test_heatmap_endpoint(client, uploaded):
    body = client.post(
        f"/analytics/{uploaded}/heatmap", json={"time_filter": "all", "measure": "revenue"}
    ).json()

    assert body["rows"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert body["cells"]
    assert body["max_value"] >= body["min_value"]


def test_insights_endpoint(client, uploaded):
    body = client.post(f"/analytics/{uploaded}/insights", json={"time_filter": "all"}).json()
    assert body["insights"]
    assert body["analysed_days"] == 90
    assert all(card["title"] and card["message"] for card in body["insights"])


def test_inventory_endpoint(client, uploaded):
    body = client.post(f"/analytics/{uploaded}/inventory", json={"time_filter": "all"}).json()
    assert body["stock_aware"] is True
    assert body["items"]
    assert body["abc_buckets"]


def test_forecast_endpoint(client, uploaded):
    body = client.post(
        f"/analytics/{uploaded}/forecast", json={"time_filter": "all", "horizon": 21}
    ).json()

    assert body["available"] is True
    assert body["horizon_days"] == 21
    assert len([point for point in body["points"] if point["is_future"]]) == 21


def test_ledger_pagination(client, uploaded):
    body = client.post(
        f"/analytics/{uploaded}/ledger", json={"time_filter": "all", "page": 2, "page_size": 25}
    ).json()

    assert body["page"] == 2
    assert len(body["entries"]) == 25
    assert body["total_rows"] > 25


def test_report_includes_discount_lines(client, uploaded):
    """The mapped Discount column must appear in the P&L as a deduction."""
    body = client.post(f"/analytics/{uploaded}/report", json={"time_filter": "all"}).json()
    labels = [line["label"] for line in body["pnl"]]

    assert "Less: Discounts Allowed" in labels
    assert "Net Revenue" in labels
    assert "Gross Profit" in labels
    assert body["category_ledger"]


def test_pdf_export_builds(client, uploaded):
    """The PDF must be a real PDF, and include the new sections without erroring."""
    response = client.post(f"/analytics/{uploaded}/report.pdf", json={"time_filter": "all"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 5_000


def test_classic_get_routes_still_work(client, uploaded):
    """The pre-Pro endpoints keep their contract for any existing consumer."""
    assert client.get(f"/analytics/{uploaded}", params={"time_filter": "week"}).status_code == 200
    assert client.get(f"/analytics/{uploaded}/report", params={"time_filter": "month"}).status_code == 200
    assert client.get(f"/analytics/{uploaded}/ledger", params={"page": 1}).status_code == 200
    assert client.get(f"/process/{uploaded}").status_code == 200
    assert client.get("/health").json() == {"status": "ok", "ai_enabled": tier2_gemini.gemini_enabled()}


def test_health_reports_whether_the_ai_tier_could_run(client, monkeypatch):
    """
    The upload page must know *before* it uploads whether consent is worth
    asking for — consent rides on the upload request itself, so a page that
    learned the answer afterwards could never grant it on the first try.

    Reported as a bare boolean: no key, no model id, no endpoint.
    """
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", False)
    assert client.get("/health").json()["ai_enabled"] is False

    # The switch alone is not enough — without a key there is nothing to call.
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "")
    assert client.get("/health").json()["ai_enabled"] is False

    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")
    assert client.get("/health").json()["ai_enabled"] is True


def test_empty_filter_result_returns_zeroed_payload(client, uploaded):
    """An impossible filter must render an empty state, not a 500."""
    response = client.post(
        f"/analytics/{uploaded}/summary",
        json={"time_filter": "custom", "start_date": "2030-01-01", "end_date": "2030-01-05"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["summary"]["revenue"]["value"] == 0
    assert body["top_items"] == []


def test_no_nan_or_infinity_in_json(client, uploaded):
    """
    NaN/Infinity are not valid JSON — if any response contained them the
    browser's JSON.parse would throw and the dashboard would show a network
    error instead of numbers.
    """
    payloads = [
        client.post(f"/analytics/{uploaded}/summary", json={"time_filter": "all"}),
        client.post(f"/analytics/{uploaded}/insights", json={"time_filter": "all"}),
        client.post(f"/analytics/{uploaded}/inventory", json={"time_filter": "all"}),
        client.post(f"/analytics/{uploaded}/forecast", json={"time_filter": "all"}),
        client.post(
            f"/analytics/{uploaded}/chart-data",
            json={"time_filter": "all", "dimension": "item", "measure": "margin_pct"},
        ),
    ]
    for response in payloads:
        assert response.status_code == 200
        text = response.text
        assert "NaN" not in text
        assert "Infinity" not in text
