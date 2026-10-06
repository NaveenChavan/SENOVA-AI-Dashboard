"""
Tests for ``POST /analytics/{id}/ai-insights``.

Two separate claims are tested here and it matters that they are kept apart:

1. **The numbers are still ours.** ``insights_engine`` is untouched, and Gemini
   only rephrases. The existing insights tests remain the correctness guarantee;
   this file exists to prove the AI layer cannot change a single figure.
2. **Nothing leaves without consent.** With consent withheld and AI enabled
   server-side, the endpoint must produce its normal response and make zero
   outbound requests.

The privacy tests assert on the *captured request body*, not on logs — a log line
proves what we chose to write down, not what we actually sent.
"""

from __future__ import annotations

import io
import json

import pytest

from app.services import tier2_gemini


@pytest.fixture
def gemini_on(monkeypatch):
    """AI available server-side. The transport is the ``gemini_transport`` fixture."""
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(tier2_gemini, "GEMINI_TOTAL_BUDGET_SECONDS", 5.0)
    monkeypatch.setattr(tier2_gemini, "GEMINI_MAX_RETRIES", 0)


class _Handle:
    """What a test gets: recorded traffic plus the responder control."""

    def __init__(self):
        self.bodies: list[dict] = []
        self.headers: list[dict] = []
        self.payload = None
        self.status = 200

    def reply(self, payload, status_code: int = 200):
        self.payload = payload
        self.status = status_code

    def _respond(self):
        text = json.dumps(self.payload)
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        return type(
            "_Response",
            (),
            {"status_code": self.status, "json": lambda self: body, "request": None},
        )()


@pytest.fixture
def gemini_transport(monkeypatch):
    """
    A recording transport plus a way to choose what Gemini answers with.

    ``.bodies`` is every request that would have gone out — the only place in the
    suite where what left the server is observed rather than assumed. ``.reply()``
    sets the response payload; with no reply installed, posting raises, so a test
    that forgets to install one fails loudly instead of silently passing against an
    endpoint that never called out at all.

    Recording and responding are the same object on purpose: a test that installed a
    responder through a different mechanism than it installed the recorder would
    quietly stop observing its own traffic.
    """
    handle = _Handle()

    class _Client:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers", {})
            handle.headers.append(self.headers)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, **kwargs):
            handle.bodies.append(json)
            if handle.payload is None:
                raise AssertionError("No responder installed — call gemini_transport.reply().")
            return handle._respond()

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Client)
    return handle


def _upload_and_confirm(client, frame, mapping):
    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    file_id = client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
    ).json()["file_id"]
    client.post(f"/upload/{file_id}/confirm-mapping", json={"mapping": mapping})
    return file_id


@pytest.fixture
def rich_file_id(client, raw_sales_frame, mapping):
    """The conftest export: it reliably produces several insight cards."""
    return _upload_and_confirm(client, raw_sales_frame, mapping)


def _plain_insights(client, file_id):
    return client.post(f"/analytics/{file_id}/insights", json={"time_filter": "all"}).json()


# ── The numbers are still ours ───────────────────────────────────────────────


class TestAdditiveOnly:
    def test_returns_everything_the_plain_endpoint_returns(self, client, rich_file_id):
        """A client that ignores the AI fields entirely must see exactly the old
        response. That is what makes this safe to add to a working dashboard."""
        plain = _plain_insights(client, rich_file_id)
        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights", json={"time_filter": "all"}
        ).json()

        assert body["insights"] == plain["insights"]
        assert body["anomaly_dates"] == plain["anomaly_dates"]
        assert body["analysed_days"] == plain["analysed_days"]
        assert body["note"] == plain["note"]

    def test_ai_text_only_touches_the_message(self, gemini_on, gemini_transport, client, rich_file_id):
        """Metrics, evidence, severity, title and id all survive a rewrite
        untouched. Only the prose can change."""
        original = _plain_insights(client, rich_file_id)["insights"]
        target = original[0]["id"]

        gemini_transport.reply(
            {"rewrites": [{"id": target, "message": "Sales were much weaker on your busiest day."}]}
        )

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()

        rewritten = next(i for i in body["insights"] if i["id"] == target)
        baseline = next(i for i in original if i["id"] == target)
        assert rewritten["metrics"] == baseline["metrics"]
        assert rewritten["evidence"] == baseline["evidence"]
        assert rewritten["severity"] == baseline["severity"]
        assert rewritten["title"] == baseline["title"]

        narrative = next(n for n in body["ai_text"] if n["id"] == target)
        assert narrative["text"] == "Sales were much weaker on your busiest day."
        assert narrative["verified"] is True

    def test_no_new_insights_are_invented(self, gemini_on, gemini_transport, client, rich_file_id):
        """The model cannot add a card. An id it was never given is discarded, and
        the card count never grows."""
        gemini_transport.reply(
            {
                "rewrites": [
                    {"id": "invented-card", "message": "Your stock is dangerously low."},
                    {"id": "margin-leak", "message": "One line is selling below cost."},
                ]
            }
        )

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()

        assert len(body["ai_text"]) == 1
        assert body["ai_text"][0]["id"] == "margin-leak"
        assert len(body["insights"]) == len(_plain_insights(client, rich_file_id)["insights"])


# ── The number check, end to end ─────────────────────────────────────────────


class TestNumberCheckEndToEnd:
    def test_a_hallucinated_amount_is_marked_unverified(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """The case the whole feature is guarded by: a model inventing a figure on
        a card a shopkeeper will act on."""
        plain = _plain_insights(client, rich_file_id)["insights"]
        target = plain[0]["id"]

        gemini_transport.reply(
            {"rewrites": [{"id": target, "message": "You lost Rs 9,99,999 on this."}]}
        )

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()

        narrative = next(n for n in body["ai_text"] if n["id"] == target)
        assert narrative["verified"] is False
        assert narrative["rejected_numbers"]

        # The deterministic sentence is still there for the UI to fall back to.
        rewritten = next(i for i in body["insights"] if i["id"] == target)
        assert rewritten["message"] == plain[0]["message"]

    def test_one_bad_rewrite_does_not_take_the_others_down(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        original = _plain_insights(client, rich_file_id)["insights"]
        first, second = original[0]["id"], original[1]["id"]

        gemini_transport.reply(
            {
                "rewrites": [
                    {"id": first, "message": "You lost Rs 9,99,999 on this."},
                    {"id": second, "message": "This one is explained more simply."},
                ]
            }
        )

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()
        by_id = {n["id"]: n for n in body["ai_text"]}

        assert by_id[first]["verified"] is False
        assert by_id[second]["verified"] is True

    def test_a_rewrite_is_checked_against_its_own_insight(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """
        A number that belongs to a *different* card must not validate this one.

        This is the sharp edge of checking against a shared pool of dashboard
        figures: it would pass, because the number is real somewhere in the
        response. Checking per-insight is what makes "every figure in this card
        traces back to this card" true rather than approximately true.
        """
        original = _plain_insights(client, rich_file_id)["insights"]

        donor = next(
            (i for i in original if any(isinstance(v, (int, float)) for v in i["metrics"].values())),
            None,
        )
        assert donor is not None
        borrowed = next(v for v in donor["metrics"].values() if isinstance(v, (int, float)))

        others = [i for i in original if i["id"] != donor["id"]]
        assert others, "need at least two cards for this to mean anything"
        target = others[0]["id"]

        gemini_transport.reply(
            {"rewrites": [{"id": target, "message": f"Revenue was Rs {borrowed:,.0f}."}]}
        )

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()

        narrative = next(n for n in body["ai_text"] if n["id"] == target)
        assert narrative["verified"] is False, "a figure from another card must not validate this one"


# ── Consent, per request ─────────────────────────────────────────────────────


class TestConsentGate:
    def test_consent_false_makes_zero_calls(self, gemini_on, gemini_transport, client, rich_file_id):
        """The guarantee, end to end and over HTTP. AI enabled server-side, consent
        withheld: a complete, normal insights response and no request at all."""
        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": False},
        )

        assert response.status_code == 200
        assert gemini_transport.bodies == [], "a request left the server despite ai_consent=false"

        body = response.json()
        assert body["ai_text"] == []
        assert body["ai_source"] == "skipped"
        assert body["insights"], "the deterministic insights must still be present"

    def test_omitting_ai_consent_is_treated_as_declining(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """Absence must never mean consent — same reasoning as the upload form
        field, and the reason the body model defaults to False."""
        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights", json={"time_filter": "all"}
        )

        assert response.status_code == 200
        assert gemini_transport.bodies == []

    def test_ai_switched_off_server_side_makes_zero_calls(self, gemini_transport, client, rich_file_id):
        """The operator switch alone is enough to stop everything, regardless of
        consent. This is the production default."""
        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )

        assert response.status_code == 200
        assert gemini_transport.bodies == []
        assert response.json()["ai_source"] == "skipped"

    def test_consent_true_does_send_a_request(self, gemini_on, gemini_transport, client, rich_file_id):
        """The negative control. Without this, every test above would also pass
        against an endpoint that never called Gemini at all — which would prove
        nothing about the gate."""
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )
        assert len(gemini_transport.bodies) == 1


# ── What actually leaves the server ──────────────────────────────────────────


class TestPayloadPrivacy:
    def test_the_request_sends_no_metrics_or_evidence(self, gemini_on, gemini_transport, client, rich_file_id):
        """
        The ``metrics`` and ``evidence`` structures are the raw material behind the
        cards, and they are the parts that would carry per-item figures and item
        names. Neither is in the payload: the model gets the sentence, not the
        data behind it.
        """
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )

        assert gemini_transport.bodies, "the negative control in this file should have made a request"
        sent = json.dumps(gemini_transport.bodies[0], ensure_ascii=False)

        # The structured fields are absent by *key*, which is a stronger assertion
        # than searching for a value: it proves the whole structure was omitted
        # rather than one figure happening to be filtered out of it.
        for forbidden_key in ('"metrics"', '"evidence"', '"severity"'):
            assert forbidden_key not in sent, f"{forbidden_key} was included in the payload"

    def test_the_request_sends_no_shop_or_branch_values(self, gemini_on, gemini_transport, client, rich_file_id):
        """Branch names are shop-level identifiers a shopkeeper would not expect to
        be forwarded, and unlike the insight text they are never needed for a
        rewrite."""
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )
        sent = json.dumps(gemini_transport.bodies[0], ensure_ascii=False)

        for literal in ("MG Road", "Station Road"):
            assert literal not in sent, f"{literal!r} left the server"

    def test_item_names_leak_only_via_the_text_the_user_already_sees(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """
        A documented limitation, pinned rather than papered over.

        An insight message can name an item — the dead-stock card reads "Winter
        Shawl has not sold in 75 days" — and that name reaches Gemini because the
        sentence being rephrased *is* the payload. There is no way to rewrite text
        without sending it.

        This is accepted deliberately: the message is already on the user's own
        screen, and it is aggregate commentary rather than a record. What this test
        records is that the leak is confined to the visible sentence — ``metrics``,
        ``evidence`` and every other structure stay out — so the exposure is bounded
        and can be re-evaluated if the wording of the deterministic cards changes.
        """
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )
        sent = json.dumps(gemini_transport.bodies[0], ensure_ascii=False)

        # The dead-stock card's sentence does carry the item name, and it does go.
        assert "Winter Shawl" in sent
        # But nothing beyond that sentence: no figures, no evidence list.
        assert '"evidence"' not in sent
        assert '"metrics"' not in sent

    def test_the_api_key_is_a_header_not_in_the_body(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """The key must travel in the header only. If it ever ended up in a body it
        would be sitting in the model's context, and in any log of that context."""
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )

        assert gemini_transport.headers, "no client was constructed"
        assert gemini_transport.headers[0]["x-goog-api-key"] == "test-key-not-real"
        assert "test-key-not-real" not in json.dumps(gemini_transport.bodies[0])


# ── Failure modes ────────────────────────────────────────────────────────────


class TestDegradation:
    def test_a_gemini_failure_keeps_the_dashboard_working(
        self, gemini_on, monkeypatch, client, rich_file_id
    ):
        class _Boom:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("network unreachable")

        monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Boom)

        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["insights"], "insights must survive a Gemini failure"
        assert body["ai_text"] == []
        assert body["ai_source"] == "fallback"
        assert body["ai_notice"]

    def test_a_malformed_response_degrades_to_no_rewrite(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        gemini_transport.reply({"unexpected": "shape"})

        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )

        assert response.status_code == 200
        assert response.json()["insights"]

    def test_an_empty_rewrite_list_is_fine(self, gemini_on, gemini_transport, client, rich_file_id):
        gemini_transport.reply({"rewrites": []})

        body = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        ).json()

        assert body["ai_text"] == []
        assert body["ai_source"] == "gemini"

    def test_a_short_file_still_returns_insights(
        self, gemini_on, gemini_transport, client, raw_sales_frame, mapping
    ):
        """Too little data for most checks to run. The AI layer must not turn a
        sparse-file note into an error."""
        csv_bytes = raw_sales_frame.head(3).to_csv(index=False).encode("utf-8")
        file_id = client.post(
            "/upload/", files={"file": ("tiny.csv", io.BytesIO(csv_bytes), "text/csv")}
        ).json()["file_id"]
        client.post(f"/upload/{file_id}/confirm-mapping", json={"mapping": mapping})

        gemini_transport.reply({"rewrites": []})
        response = client.post(
            f"/analytics/{file_id}/ai-insights", json={"time_filter": "all", "ai_consent": True}
        )
        assert response.status_code == 200


# ── Security, matching every other route in this file ────────────────────────


class TestSecurity:
    def test_another_user_gets_the_indistinguishable_404(self, client, rich_file_id):
        from app.main import app
        from app.utils.auth_verifier import get_current_user

        app.dependency_overrides[get_current_user] = lambda: "someone-else@shop.test"
        try:
            response = client.post(
                f"/analytics/{rich_file_id}/ai-insights",
                json={"time_filter": "all", "ai_consent": True},
            )
        finally:
            app.dependency_overrides[get_current_user] = lambda: "owner@shop.test"

        assert response.status_code == 404
        assert "not belong" not in response.text.lower()

    def test_unconfirmed_mapping_returns_409(self, client, raw_sales_frame):
        csv_bytes = raw_sales_frame.to_csv(index=False).encode("utf-8")
        file_id = client.post(
            "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}
        ).json()["file_id"]

        response = client.post(f"/analytics/{file_id}/ai-insights", json={"time_filter": "all"})
        assert response.status_code == 409

    def test_bad_filters_are_still_rejected(self, client, rich_file_id):
        """The AI route must not become a way around the closed filter registry."""
        response = client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "filters": {"__proto__": ["x"]}},
        )
        assert response.status_code == 422

    def test_ai_consent_is_not_persisted_between_requests(
        self, gemini_on, gemini_transport, client, rich_file_id
    ):
        """
        A consented call must not license a later unconsented one.

        This is the whole reason consent is a required field on each request rather
        than something remembered server-side: there is no state to inherit, so
        consent cannot leak from one upload to an unrelated later one.
        """
        gemini_transport.reply({"rewrites": []})

        client.post(
            f"/analytics/{rich_file_id}/ai-insights",
            json={"time_filter": "all", "ai_consent": True},
        )
        assert len(gemini_transport.bodies) == 1

        client.post(f"/analytics/{rich_file_id}/ai-insights", json={"time_filter": "all"})
        assert len(gemini_transport.bodies) == 1, "a second call must need its own consent"
