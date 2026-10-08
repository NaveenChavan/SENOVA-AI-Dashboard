"""Regression tests for SENOVA's dual PDF export.

These tests are intentionally scoped to the PDF presentation layer so they do
not replace the application's analytics test suite. They use the real fixture
file and the same sales_calculations module used by the dashboard.
"""

from pathlib import Path

import pytest
pypdf = pytest.importorskip("pypdf")
from pypdf import PdfReader

from app.models.schemas import AnalyticsResponse
from app.services.pdf_report import generate_ca_report_pdf, generate_visual_financial_pdf
from app.services.sales_calculations import (
    build_ledger_page,
    compute_daily_financial_summary,
    compute_daily_trend_between,
    compute_dead_stock,
    compute_pnl_report,
    compute_revenue_by_category,
    compute_summary_between,
    compute_top_items,
)


FIXTURE = Path(__file__).resolve().parents[2] / "testing2" / "03_electronics_shopify_orders.csv"
if not FIXTURE.exists():
    FIXTURE = Path(__file__).resolve().parents[2].parent / "testing2" / "03_electronics_shopify_orders.csv"


def _normalized_fixture() -> pd.DataFrame:
    raw = pd.read_csv(FIXTURE)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(raw["Ordered On"]),
            "Category": raw["Product type"],
            "Item": raw["Lineitem name"],
            "Quantity": pd.to_numeric(raw["Lineitem quantity"]),
            "Selling Price": pd.to_numeric(raw["Lineitem price"]),
            "Cost Price": pd.to_numeric(raw["Unit Cost"]),
            "MRP": pd.to_numeric(raw["MRP"]),
        }
    )


def _analytics(df, start, end):
    previous = pd.DataFrame(columns=df.columns)
    return AnalyticsResponse(
        row_count=len(df),
        summary=compute_summary_between(df, previous, start, end),
        top_items=compute_top_items(df),
        daily_trend=compute_daily_trend_between(df, start, end),
        dead_stock=compute_dead_stock(df),
        categories=compute_revenue_by_category(df),
        errors=[],
        discount_metrics=None,
        discount_vs_margin=[],
    )


def test_visual_report_is_exactly_one_page():
    df = _normalized_fixture()
    start = pd.Timestamp("2026-05-19")
    end = pd.Timestamp("2026-06-17")
    analytics = _analytics(df[(df.Date >= start) & (df.Date <= end)], start, end)
    ca = compute_pnl_report(df[(df.Date >= start) & (df.Date <= end)], "Last 30 Days")
    daily = compute_daily_financial_summary(df[(df.Date >= start) & (df.Date <= end)], start, end)
    pdf = generate_visual_financial_pdf(
        filename=FIXTURE.name,
        analytics=analytics,
        ca_report=ca,
        daily_summary=daily,
        insights=None,
        inventory=None,
        forecast=None,
    )
    assert len(PdfReader(__import__("io").BytesIO(pdf)).pages) == 1


def test_detailed_report_contains_all_selected_transaction_rows():
    df = _normalized_fixture()
    start = pd.Timestamp("2026-05-19")
    end = pd.Timestamp("2026-06-17")
    current = df[(df.Date >= start) & (df.Date <= end)]
    analytics = _analytics(current, start, end)
    ca = compute_pnl_report(current, "Last 30 Days")
    daily = compute_daily_financial_summary(current, start, end)
    ledger = build_ledger_page(current, 1, max(1, len(current)))
    pdf = generate_ca_report_pdf(
        filename=FIXTURE.name,
        analytics=analytics,
        ca_report=ca,
        ledger_entries=ledger.entries,
        ledger_total_rows=ledger.total_rows,
        insights=None,
        inventory=None,
        forecast=None,
        daily_summary=daily,
    )
    reader = PdfReader(__import__("io").BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Daily Financial Summary" in text
    assert "Detailed Transaction Ledger" in text
    assert "2026-06-17" in text
    assert ledger.total_rows == len(ledger.entries)


def test_daily_summary_reconciles_to_dashboard_totals():
    df = _normalized_fixture()
    start = pd.Timestamp("2026-05-19")
    end = pd.Timestamp("2026-06-17")
    current = df[(df.Date >= start) & (df.Date <= end)]
    analytics = _analytics(current, start, end)
    daily = compute_daily_financial_summary(current, start, end)
    assert round(sum(row["revenue"] for row in daily), 2) == round(analytics.summary.revenue.value, 2)
    assert round(sum(row["cost"] for row in daily), 2) == round(analytics.summary.cost.value, 2)
    assert round(sum(row["profit"] for row in daily), 2) == round(analytics.summary.profit.value, 2)
    assert sum(row["units_sold"] for row in daily) == int(analytics.summary.units_sold.value)
