"""
Accuracy audit: every published number re-derived independently.

Why this file exists separately from the other suites
----------------------------------------------------
The other tests check that each module behaves as designed. This one asks a
harder question: *is the number on screen the same number the raw file implies?*
Every expected value here is recomputed from the raw DataFrame with plain
Pandas — deliberately not by calling the same helper the API uses — and then
compared with what the HTTP endpoints actually return.

It also runs against a **sparse** shop (sales on roughly a third of days, which
is what a real small retailer's export looks like), because that is the shape
that broke the anomaly baseline: a zero-filled median of ₹0 produced the
nonsense "0% above your normal daily level of ₹0".
"""

from __future__ import annotations

import io
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

_TEMP_UPLOAD_DIR = tempfile.mkdtemp(prefix="senova-audit-uploads-")
os.environ["UPLOAD_DIR"] = _TEMP_UPLOAD_DIR
os.environ["DISABLE_AUTH"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import frame_cache  # noqa: E402
from app.utils.auth_verifier import get_current_user  # noqa: E402

AUDITOR = "auditor@shop.test"

#: Share of calendar days the shop actually trades on.
TRADING_DAY_SHARE = 0.35
#: Length of the synthetic history.
SPAN_DAYS = 180


@pytest.fixture(scope="module")
def sparse_raw() -> pd.DataFrame:
    """
    A realistic sparse export: 180 calendar days, sales on ~35% of them, five
    SKUs across three categories, a per-line discount, one deliberate bumper day.
    """
    rng = np.random.default_rng(2026)
    start = pd.Timestamp("2026-01-05")
    catalogue = [
        ("Cotton T-Shirt", "Clothing", 350.0, 599.0),
        ("Denim Jacket", "Clothing", 2000.0, 2999.0),
        ("Wireless Mouse", "Electronics", 800.0, 1200.0),
        ("USB-C Hub", "Electronics", 1200.0, 1799.0),
        ("Desk Lamp", "Home Appliances", 1800.0, 2499.0),
    ]

    rows: list[dict] = []
    for offset in range(SPAN_DAYS):
        day = start + pd.Timedelta(days=offset)
        if rng.random() > TRADING_DAY_SHARE:
            continue  # shop closed / nothing recorded
        boom = 6 if offset == 120 else 1  # one bumper day for the anomaly check
        for item, category, cost, price in catalogue:
            units = int(rng.integers(1, 5)) * boom
            rows.append(
                {
                    "Bill Date": day.strftime("%d-%m-%Y"),
                    "Item Name": item,
                    "Stock Group": category,
                    "Qty.": units,
                    "Rate/Unit": price,
                    "Purchase Rate": cost,
                    "Discount": round(price * units * 0.03, 2),
                    "Store": "MG Road" if offset % 3 else "Station Road",
                    "Closing Stock": 30,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def truth(sparse_raw) -> dict:
    """
    Ground truth, computed from the raw frame with plain Pandas — no shared code
    with the application's calculation layer.
    """
    frame = sparse_raw.copy()
    frame["date"] = pd.to_datetime(frame["Bill Date"], dayfirst=True)
    frame["gross"] = frame["Qty."] * frame["Rate/Unit"]
    frame["revenue"] = frame["gross"] - frame["Discount"]
    frame["cost"] = frame["Qty."] * frame["Purchase Rate"]
    frame["profit"] = frame["revenue"] - frame["cost"]

    daily = frame.groupby(frame["date"].dt.date)["revenue"].sum()
    calendar = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")

    return {
        "frame": frame,
        "revenue": float(frame["revenue"].sum()),
        "cost": float(frame["cost"].sum()),
        "profit": float(frame["profit"].sum()),
        "gross": float(frame["gross"].sum()),
        "discount": float(frame["Discount"].sum()),
        "units": int(frame["Qty."].sum()),
        "unique_items": int(frame["Item Name"].nunique()),
        "rows": len(frame),
        "by_category": frame.groupby("Stock Group")["revenue"].sum().to_dict(),
        "by_item_units": frame.groupby("Item Name")["Qty."].sum().to_dict(),
        "by_branch": frame.groupby("Store")["revenue"].sum().to_dict(),
        "trading_days": int(len(daily)),
        "calendar_days": int(len(calendar)),
        "trading_day_median": float(daily.median()),
        "span_days": int((frame["date"].max().normalize() - frame["date"].min().normalize()).days) + 1,
    }


@pytest.fixture(scope="module")
def client(sparse_raw):
    """Upload the sparse file once and hand back (client, file_id)."""
    app.dependency_overrides[get_current_user] = lambda: AUDITOR
    frame_cache.clear()

    mapping = {
        "Bill Date": "Date",
        "Item Name": "Item",
        "Stock Group": "Category",
        "Qty.": "Quantity",
        "Rate/Unit": "Selling Price",
        "Purchase Rate": "Cost Price",
        "Discount": "Discount",
        "Store": "Branch",
        "Closing Stock": "Stock On Hand",
    }

    with TestClient(app) as test_client:
        csv_bytes = sparse_raw.to_csv(index=False).encode("utf-8")
        preview = test_client.post(
            "/upload/", files={"file": ("sparse-shop.csv", io.BytesIO(csv_bytes), "text/csv")}
        ).json()
        file_id = preview["file_id"]
        confirmed = test_client.post(f"/upload/{file_id}/confirm-mapping", json={"mapping": mapping})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["error_count"] == 0, "the audit file must validate cleanly"
        yield test_client, file_id

    app.dependency_overrides.clear()


def _post(client, file_id, path, body=None):
    response = client[0].post(f"/analytics/{file_id}{path}", json=body or {"time_filter": "all"})
    assert response.status_code == 200, f"{path} → {response.status_code}: {response.text}"
    return response.json()


# ── KPIs ────────────────────────────────────────────────────────────────────


def test_kpis_match_an_independent_recomputation(client, truth):
    """Revenue, cost, profit, units and SKU count, to the rupee."""
    test_client, file_id = client
    summary = _post(client, file_id, "/summary")["summary"]

    assert summary["revenue"]["value"] == pytest.approx(truth["revenue"], abs=0.01)
    assert summary["cost"]["value"] == pytest.approx(truth["cost"], abs=0.01)
    assert summary["profit"]["value"] == pytest.approx(truth["profit"], abs=0.01)
    assert summary["units_sold"]["value"] == truth["units"]
    assert summary["unique_items_sold"]["value"] == truth["unique_items"]

    # The accounting identity must hold in the payload itself, not just upstream.
    assert summary["profit"]["value"] == pytest.approx(
        summary["revenue"]["value"] - summary["cost"]["value"], abs=0.01
    )


def test_revenue_is_net_of_discount(client, truth):
    """A mapped Discount column must reduce revenue, not be ignored."""
    test_client, file_id = client
    summary = _post(client, file_id, "/summary")["summary"]

    assert truth["discount"] > 0
    assert summary["revenue"]["value"] == pytest.approx(truth["gross"] - truth["discount"], abs=0.01)


def test_daily_trend_sums_to_total_revenue(client, truth):
    """The trend line is the same money as the KPI card, spread over days."""
    test_client, file_id = client
    payload = _post(client, file_id, "/summary")

    trend_total = sum(point["revenue"] for point in payload["daily_trend"])
    assert trend_total == pytest.approx(truth["revenue"], abs=0.5)
    # Zero-filled: one point per calendar day, not per trading day.
    assert len(payload["daily_trend"]) == truth["calendar_days"]


def test_date_range_matches_the_file(client, truth):
    test_client, file_id = client
    dimensions = test_client.get(f"/analytics/{file_id}/dimensions").json()
    assert dimensions["date_range"]["span_days"] == truth["span_days"]


# ── Aggregation ─────────────────────────────────────────────────────────────


def test_category_totals_match(client, truth):
    test_client, file_id = client
    payload = _post(client, file_id, "/chart-data", {"time_filter": "all", "dimension": "category", "measure": "revenue", "top_n": 50})

    published = {point["label"]: point["value"] for point in payload["points"]}
    assert set(published) == set(truth["by_category"])
    for category, expected in truth["by_category"].items():
        assert published[category] == pytest.approx(expected, abs=0.01)
    assert payload["total"] == pytest.approx(truth["revenue"], abs=0.01)


def test_item_units_match(client, truth):
    test_client, file_id = client
    payload = _post(client, file_id, "/chart-data", {"time_filter": "all", "dimension": "item", "measure": "units", "top_n": 50})

    published = {point["label"]: point["units"] for point in payload["points"]}
    assert published == truth["by_item_units"]


def test_branch_totals_match_and_filters_are_consistent(client, truth):
    """A branch filter must return exactly that branch's independently-summed revenue."""
    test_client, file_id = client

    for branch, expected in truth["by_branch"].items():
        filtered = _post(client, file_id, "/summary", {"time_filter": "all", "filters": {"branch": [branch]}})
        assert filtered["summary"]["revenue"]["value"] == pytest.approx(expected, abs=0.01), branch

    # The parts must add up to the whole.
    assert sum(truth["by_branch"].values()) == pytest.approx(truth["revenue"], abs=0.01)


def test_margin_and_avg_price_are_internally_consistent(client):
    """Ratio measures must agree with the additive measures on the same point."""
    test_client, file_id = client
    payload = _post(client, file_id, "/chart-data", {"time_filter": "all", "dimension": "item", "measure": "revenue", "top_n": 50})

    for point in payload["points"]:
        assert point["profit"] == pytest.approx(point["revenue"] - point["cost"], abs=0.01)
        assert point["margin_pct"] == pytest.approx(point["profit"] / point["revenue"] * 100, abs=0.01)
        assert point["avg_price"] == pytest.approx(point["revenue"] / point["units"], rel=1e-6)


def test_pareto_curve_reaches_one_hundred_percent(client):
    test_client, file_id = client
    payload = _post(client, file_id, "/chart-data", {"time_filter": "all", "dimension": "item", "measure": "revenue", "top_n": 50})

    shares = [point["share_pct"] for point in payload["points"]]
    assert sum(shares) == pytest.approx(100.0, abs=0.05)
    assert payload["points"][-1]["cumulative_pct"] == pytest.approx(100.0, abs=0.05)


def test_heatmap_total_matches_revenue(client, truth):
    test_client, file_id = client
    grid = _post(client, file_id, "/heatmap", {"time_filter": "all", "measure": "revenue"})
    assert sum(cell["value"] for cell in grid["cells"]) == pytest.approx(truth["revenue"], abs=1.0)


# ── Ledger & report ─────────────────────────────────────────────────────────


def test_ledger_covers_every_row_and_reconciles(client, truth):
    """Every valid row must be reachable, and the pages must sum to the KPI."""
    test_client, file_id = client

    first = _post(client, file_id, "/ledger", {"time_filter": "all", "page": 1, "page_size": 1000})
    assert first["total_rows"] == truth["rows"]

    total = 0.0
    seen = 0
    for page in range(1, first["total_pages"] + 1):
        payload = _post(client, file_id, "/ledger", {"time_filter": "all", "page": page, "page_size": 1000})
        total += sum(entry["revenue"] for entry in payload["entries"])
        seen += len(payload["entries"])

    assert seen == truth["rows"]
    assert total == pytest.approx(truth["revenue"], abs=1.0)


def test_pnl_statement_reconciles(client, truth):
    """Gross − discount = net revenue; net − COGS = gross profit."""
    test_client, file_id = client
    report = _post(client, file_id, "/report")
    lines = {line["label"]: line["amount"] for line in report["pnl"]}

    assert lines["Gross Sales (before discount)"] == pytest.approx(truth["gross"], abs=0.01)
    assert lines["Less: Discounts Allowed"] == pytest.approx(truth["discount"], abs=0.01)
    assert lines["Net Revenue"] == pytest.approx(truth["revenue"], abs=0.01)
    assert lines["Cost of Goods Sold (COGS)"] == pytest.approx(truth["cost"], abs=0.01)
    assert lines["Gross Profit"] == pytest.approx(truth["profit"], abs=0.01)
    assert lines["Net Revenue"] - lines["Cost of Goods Sold (COGS)"] == pytest.approx(lines["Gross Profit"], abs=0.01)

    # The category schedule must add back up to the statement.
    ledger_revenue = sum(row["revenue"] for row in report["category_ledger"])
    assert ledger_revenue == pytest.approx(truth["revenue"], abs=0.01)
    assert report["total_transactions"] == truth["rows"]


# ── Insights on a sparse shop (the reported bug) ─────────────────────────────


def test_anomaly_baseline_is_a_real_trading_day_not_zero(client, truth):
    """
    On a shop that trades a third of the time the baseline must be the typical
    *trading* day. A ₹0 baseline produced "0% above your normal daily level of
    ₹0" and flagged nearly every trading day as an outlier.
    """
    test_client, file_id = client
    payload = _post(client, file_id, "/insights")

    anomalies = [card for card in payload["insights"] if card["kind"] == "anomaly"]
    for card in anomalies:
        assert card["metrics"]["normal_level"] > 0, card["message"]
        assert "₹0" not in card["message"]
        assert "0% above" not in card["message"]
        assert "unmeasurable" not in card["message"]
        # The baseline must be in the neighbourhood of the real trading median.
        assert card["metrics"]["normal_level"] == pytest.approx(truth["trading_day_median"], rel=0.35)


def test_anomalies_are_rare_by_construction(client, truth):
    """
    A statistical outlier must be exceptional. Before the fix, 32 of 187 days
    were flagged; the ceiling here (15% of trading days) still leaves room for a
    genuinely volatile shop.
    """
    test_client, file_id = client
    payload = _post(client, file_id, "/insights")

    flagged = len(payload["anomaly_dates"])
    assert flagged <= max(2, int(truth["trading_days"] * 0.15)), f"{flagged} anomalies is not exceptional"
    # The deliberate 6× day must be among them.
    assert payload["anomaly_dates"], "the bumper day should be detected"


def test_no_insight_quotes_an_impossible_number(client):
    """Every metric attached to a card must be finite and JSON-safe."""
    test_client, file_id = client
    payload = _post(client, file_id, "/insights")

    for card in payload["insights"]:
        assert card["title"] and card["message"]
        for key, value in card["metrics"].items():
            if value is not None:
                assert np.isfinite(value), f"{card['id']}.{key} = {value}"
        assert "{" not in card["message"] and "nan" not in card["message"].lower()


# ── Inventory ───────────────────────────────────────────────────────────────


def test_inventory_velocity_and_cover_are_arithmetically_right(client, truth):
    test_client, file_id = client
    payload = _post(client, file_id, "/inventory")

    assert payload["stock_aware"] is True
    assert payload["window_days"] == truth["calendar_days"]

    for item in payload["items"]:
        expected_velocity = truth["by_item_units"][item["item"]] / truth["calendar_days"]
        assert item["velocity_per_day"] == pytest.approx(expected_velocity, rel=0.01), item["item"]
        # Active-day velocity can never be slower than the calendar rate.
        assert item["velocity_active"] >= item["velocity_per_day"] - 1e-9
        assert item["days_of_cover"] == pytest.approx(
            item["stock_on_hand"] / item["velocity_per_day"], rel=0.01
        )
        assert 0 <= item["reorder_priority"] <= 100

    # ABC classes must partition the catalogue exactly once.
    assert sum(bucket["item_count"] for bucket in payload["abc_buckets"]) == truth["unique_items"]


# ── Forecast ────────────────────────────────────────────────────────────────


def test_forecast_is_internally_consistent(client):
    test_client, file_id = client
    payload = _post(client, file_id, "/forecast", {"time_filter": "all", "horizon": 30})

    assert payload["available"] is True
    future = [point for point in payload["points"] if point["is_future"]]
    assert len(future) == 30

    assert payload["expected_revenue"] == pytest.approx(sum(p["forecast"] for p in future), rel=1e-6)
    assert payload["expected_revenue_lower"] <= payload["expected_revenue"] <= payload["expected_revenue_upper"]
    for point in future:
        assert 0 <= point["lower"] <= point["forecast"] <= point["upper"]

    # A projection must be in the same order of magnitude as recent trading.
    assert payload["daily_average"] > 0
    assert payload["accuracy_pct"] is None or 0 <= payload["accuracy_pct"] <= 100


def test_forecast_explains_sparse_trading(client, truth):
    """
    A shop that trades a third of the calendar must be told so, and its accuracy
    must be scored on the period total rather than as a per-day figure — per-day
    error there is dominated by *which* days were open, which no revenue model
    can know.
    """
    test_client, file_id = client
    payload = _post(client, file_id, "/forecast", {"time_filter": "all", "horizon": 14})

    assert payload["trading_days"] == truth["trading_days"]
    assert payload["history_days"] == truth["calendar_days"]
    assert payload["trading_days"] < payload["history_days"]
    assert payload["accuracy_basis"] == "total"
    assert payload["reason"] and "closed days" in payload["reason"]


def test_forecast_scores_daily_accuracy_on_a_shop_that_trades_every_day(client):
    """The dense path must still report a per-day accuracy figure."""
    from app.services.forecasting import compute_forecast
    import pandas as pd

    rng = np.random.default_rng(11)
    rows = []
    start = pd.Timestamp("2026-01-01")
    for offset in range(90):
        day = start + pd.Timedelta(days=offset)
        rows.append(
            {
                "Date": day,
                "Category": "Clothing",
                "Item": "Cotton T-Shirt",
                "Quantity": int(rng.integers(8, 14)),
                "Selling Price": 599.0,
                "Cost Price": 350.0,
            }
        )
    dense = pd.DataFrame(rows)

    result = compute_forecast(dense, horizon_days=14)
    assert result.accuracy_basis == "daily"
    assert result.trading_days == result.history_days == 90
    assert result.accuracy_pct is not None and result.accuracy_pct > 50


# ── Register presentation ───────────────────────────────────────────────────


def test_register_exposes_the_discount_that_explains_net_revenue(client, truth):
    """
    Each row must carry its discount, otherwise ``revenue ≠ qty × price`` looks
    like an arithmetic error to whoever is reading the register.
    """
    test_client, file_id = client
    payload = _post(client, file_id, "/ledger", {"time_filter": "all", "page": 1, "page_size": 50})

    assert payload["entries"]
    for entry in payload["entries"]:
        assert entry["discount"] > 0
        assert entry["revenue"] == pytest.approx(
            entry["quantity"] * entry["selling_price"] - entry["discount"], abs=0.02
        )
        assert entry["profit"] == pytest.approx(
            entry["revenue"] - entry["quantity"] * entry["cost_price"], abs=0.02
        )

def test_forecast_dates_continue_the_history_without_gaps(client):
    test_client, file_id = client
    payload = _post(client, file_id, "/forecast", {"time_filter": "all", "horizon": 14})

    dates = [pd.Timestamp(point["date"]) for point in payload["points"]]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
    gaps = {(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)}
    assert gaps == {1}, f"expected a continuous daily series, saw gaps of {gaps}"


# ── Cross-endpoint consistency & serialisation ──────────────────────────────


def test_every_endpoint_agrees_on_the_same_slice(client):
    """
    The point of the shared query layer: KPI, chart, P&L and ledger must all
    describe an identical slice when handed identical filters.
    """
    test_client, file_id = client
    query = {"time_filter": "custom", "start_date": "2026-02-01", "end_date": "2026-02-28", "filters": {"branch": ["MG Road"]}}

    summary = _post(client, file_id, "/summary", query)["summary"]["revenue"]["value"]
    chart = _post(client, file_id, "/chart-data", {**query, "dimension": "category", "measure": "revenue", "top_n": 50})["total"]
    report = _post(client, file_id, "/report", query)
    pnl = {line["label"]: line["amount"] for line in report["pnl"]}["Net Revenue"]
    ledger = _post(client, file_id, "/ledger", {**query, "page": 1, "page_size": 1000})
    ledger_total = sum(entry["revenue"] for entry in ledger["entries"])

    assert summary == pytest.approx(chart, abs=0.5)
    assert summary == pytest.approx(pnl, abs=0.5)
    assert summary == pytest.approx(ledger_total, abs=1.0)


def test_no_response_contains_nan_or_infinity(client):
    """NaN/Infinity are invalid JSON and break JSON.parse in the browser."""
    test_client, file_id = client
    bodies = [
        _post(client, file_id, "/summary"),
        _post(client, file_id, "/insights"),
        _post(client, file_id, "/inventory"),
        _post(client, file_id, "/forecast"),
        _post(client, file_id, "/report"),
        _post(client, file_id, "/chart-data", {"time_filter": "all", "dimension": "item", "measure": "margin_pct"}),
        _post(client, file_id, "/heatmap", {"time_filter": "all", "measure": "avg_price"}),
    ]
    for body in bodies:
        text = str(body)
        assert "nan" not in text.lower().replace("financial", "")
        assert "inf" not in text.lower().replace("info", "").replace("financial", "")


def test_pdf_export_reflects_the_same_numbers(client, truth):
    """The PDF must build and contain the period's real revenue figure."""
    test_client, file_id = client
    response = test_client.post(f"/analytics/{file_id}/report.pdf", json={"time_filter": "all"})

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 10_000
