"""
Degenerate-input tests — the files a real user eventually uploads.

None of these shapes is *wrong*, they're just extreme: one row, one day, a free
giveaway, a shop that only ever sold at a loss, a discount bigger than the line,
fifty rows on the same timestamp, an item that never moves. Each one must produce
a renderable payload rather than a crash, a blank panel or a non-finite number
(which would be invalid JSON and break ``JSON.parse`` in the browser).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from app.services import query_engine
from app.services.forecasting import compute_forecast
from app.services.insights_engine import compute_insights
from app.services.inventory_intel import compute_inventory_intelligence
from app.services.sales_calculations import (
    build_ledger_page,
    compute_pnl_report,
    compute_summary_between,
)
from app.utils.data_validator import normalize_dataframe


def _row(day: str, item: str = "A", category: str = "X", qty: int = 1, price: float = 100.0,
         cost: float = 40.0, **extra) -> dict:
    row = {
        "Date": day,
        "Category": category,
        "Item": item,
        "Quantity": qty,
        "Selling Price": price,
        "Cost Price": cost,
    }
    row.update(extra)
    return row


CASES: dict[str, list[dict]] = {
    "single row": [_row("01-02-2026")],
    "one day many items": [_row("01-02-2026", item=f"I{i}") for i in range(12)],
    "zero revenue giveaway": [_row("01-02-2026", price=0.0, cost=0.0)],
    "only ever sold at a loss": [_row(f"{d:02d}-02-2026", price=50.0, cost=90.0) for d in range(1, 26)],
    "one item, four weeks": [_row(f"2026-03-{d:02d}") for d in range(1, 29)],
    "two years, monthly": [_row(f"01-{m:02d}-{y}") for y in (2025, 2026) for m in range(1, 13)],
    "fifty rows same day": [_row("01-02-2026") for _ in range(50)],
    "absurd magnitudes": [_row("01-02-2026", qty=999_999, price=99_999.0, cost=1.0)],
    "stock with a frozen item": [
        *[_row(f"{d:02d}-02-2026", item="Mover", **{"Stock On Hand": 10}) for d in range(1, 20)],
        _row("01-02-2026", item="Frozen", **{"Stock On Hand": 500}),
    ],
    "discount exceeds the line": [_row("01-02-2026", qty=2, price=100.0, **{"Discount": 500.0})],
}


def _finite(value) -> bool:
    """None is fine (it serialises to null); NaN and ±inf are not."""
    return value is None or (isinstance(value, (int, float)) and math.isfinite(value))


@pytest.mark.parametrize("name", list(CASES))
def test_degenerate_input_produces_a_renderable_payload(name):
    frame, _errors = normalize_dataframe(pd.DataFrame(CASES[name]))
    assert not frame.empty, f"{name} lost every row"

    current, previous, window = query_engine.build_slice(frame, time_filter="all")

    # Every panel the dashboard renders, on this slice.
    summary = compute_summary_between(current, previous, window.start, window.end)
    insights = compute_insights(current, previous, period_label=window.label)
    inventory = compute_inventory_intelligence(current)
    forecast = compute_forecast(current, horizon_days=14)
    report = compute_pnl_report(current, window.label)
    ledger = build_ledger_page(current, page=1, page_size=10)
    chart = query_engine.aggregate(current, dimension="category", measure="margin_pct")
    heatmap = query_engine.heatmap(current, measure="avg_price")

    numbers = [
        summary.revenue.value,
        summary.profit.value,
        summary.cost.value,
        chart.total,
        *(point.value for point in chart.points),
        *(point.margin_pct for point in chart.points),
        *(point.avg_price for point in chart.points),
        *(cell.value for cell in heatmap.cells),
        *(line.amount for line in report.pnl),
        *(entry.revenue for entry in ledger.entries),
        *(item.velocity_per_day for item in inventory.items),
        *(item.days_of_cover for item in inventory.items),
        *(item.reorder_priority for item in inventory.items),
        forecast.expected_revenue,
        forecast.accuracy_pct,
    ]
    for value in numbers:
        assert _finite(value), f"{name} produced a non-finite number: {value!r}"

    # Insight cards must never carry an unresolved template or a NaN in prose.
    for card in insights.insights:
        assert "{" not in card.message
        assert "nan" not in card.message.lower()
        for metric in card.metrics.values():
            assert _finite(metric)

    # The P&L identity has to survive even these inputs.
    lines = {line.label: line.amount for line in report.pnl}
    net = lines.get("Net Revenue", lines.get("Gross Revenue", 0.0))
    assert net - lines["Cost of Goods Sold (COGS)"] == pytest.approx(lines["Gross Profit"], abs=0.01)


def test_short_history_refuses_to_forecast_rather_than_guessing():
    frame, _errors = normalize_dataframe(pd.DataFrame(CASES["one day many items"]))
    forecast = compute_forecast(frame, horizon_days=14)

    assert forecast.available is False
    assert forecast.points == []
    assert forecast.reason


def test_a_frozen_item_reports_no_cover_instead_of_infinity():
    """Stock ÷ zero velocity is not a number a UI can plot; it must be null."""
    frame, _errors = normalize_dataframe(pd.DataFrame(CASES["stock with a frozen item"]))
    # Restrict the window so the frozen item has no sales inside it at all.
    window_start = pd.Timestamp("2026-02-05")
    inventory = compute_inventory_intelligence(frame[frame["Date"] >= window_start])

    assert inventory.stock_aware is True
    assert all(item.days_of_cover is None or math.isfinite(item.days_of_cover) for item in inventory.items)


def test_discount_larger_than_the_line_floors_revenue_at_zero():
    """A data-entry error must not produce negative revenue in the P&L."""
    frame, _errors = normalize_dataframe(pd.DataFrame(CASES["discount exceeds the line"]))
    current, previous, window = query_engine.build_slice(frame, time_filter="all")
    summary = compute_summary_between(current, previous, window.start, window.end)

    assert summary.revenue.value == 0.0
    # Cost still stands, so the period is a real loss — that is the honest answer.
    assert summary.profit.value < 0
