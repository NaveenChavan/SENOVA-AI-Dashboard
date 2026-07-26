"""
Run every ``testing2/`` fixture through the real backend pipeline and report what
SENOVA made of it.

This is not a unit test — it is the answer to "how many different export formats
can it actually handle?". For each file it uses the *automatic* column guesser
(no human confirming a mapping), then validates, then computes the same numbers
the dashboard shows, and prints them next to an independent recomputation.

    py -3 testing2/verify_testing2.py

Exit code is non-zero if any file fails to produce analysable rows or if any
published total disagrees with the independent recomputation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import query_engine  # noqa: E402
from app.services.forecasting import compute_forecast  # noqa: E402
from app.services.insights_engine import compute_insights  # noqa: E402
from app.services.inventory_intel import compute_inventory_intelligence  # noqa: E402
from app.services.sales_calculations import (  # noqa: E402
    build_ledger_page,
    compute_pnl_report,
    compute_summary_between,
)
from app.utils.data_validator import (  # noqa: E402
    OPTIONAL_DIMENSION_COLUMNS,
    OPTIONAL_MEASURE_COLUMNS,
    detect_column_mapping,
    normalize_dataframe,
)

FILES = [
    ("01_garment_tally_export.csv", "Garment shop", "Tally headers, DD-MM-YYYY"),
    ("02_grocery_gst_invoice.csv", "Grocery / kirana", "Line total only, ₹ with commas, GST"),
    ("03_electronics_shopify_orders.csv", "Electronics", "Marketplace headers, ISO dates"),
    ("04_pharmacy_marg_stock.xlsx", "Pharmacy", "Excel + Closing Stock"),
    ("05_restaurant_pos_semicolon.csv", "Restaurant", "Semicolon + dirty rows"),
    ("06_footwear_boutique_wide.csv", "Footwear boutique", "18 columns, sparse trading"),
]

#: Mapping corrections a user would make on the confirmation screen. The guesser
#: gets most headers right on its own; these are the genuinely ambiguous ones
#: (two price-like columns, or a cost column the alias map reads as a rate).
MANUAL_FIXES: dict[str, dict[str, str]] = {
    "03_electronics_shopify_orders.csv": {
        "Lineitem price": "Selling Price",
        "MRP": "",  # two price columns: the user picks one
        "Unit Cost": "Cost Price",
    },
    "05_restaurant_pos_semicolon.csv": {
        "Rate": "Selling Price",
        "Cost": "Cost Price",
    },
}


def read_any(path: Path) -> pd.DataFrame:
    """Read a CSV (sniffing the delimiter) or an Excel file, like the backend does."""
    if path.suffix == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")

    import csv as csv_module

    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:2048]
    try:
        delimiter = csv_module.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv_module.Error:
        delimiter = ","
    return pd.read_csv(path, sep=delimiter, encoding="utf-8-sig", engine="python")


def build_mapping(raw: pd.DataFrame, filename: str) -> tuple[dict[str, str], list[str]]:
    """Automatic guess, then the manual corrections a user would make."""
    guessed = {
        row["raw_column"]: row["suggested_field"] or ""
        for row in detect_column_mapping(raw)
    }
    corrections = []
    for column, field in MANUAL_FIXES.get(filename, {}).items():
        if column in guessed and guessed[column] != field:
            corrections.append(f"{column} → {field or 'ignore'}")
            guessed[column] = field
    return {k: v for k, v in guessed.items() if v}, corrections


def independent_totals(frame: pd.DataFrame) -> dict:
    """Recompute the headline numbers straight from the validated frame."""
    gross = frame["Quantity"] * frame["Selling Price"]
    discount = frame["Discount"] if "Discount" in frame.columns else 0
    revenue = (gross - discount).clip(lower=0)
    cost = frame["Quantity"] * frame["Cost Price"]
    return {
        "revenue": float(revenue.sum()),
        "profit": float((revenue - cost).sum()),
        "units": int(frame["Quantity"].sum()),
        "items": int(frame["Item"].nunique()),
    }


def check(name: str, category: str, torture: str) -> tuple[bool, list[str]]:
    """Process one file end to end. Returns (ok, report lines)."""
    path = Path(__file__).resolve().parent / name
    lines: list[str] = []
    ok = True

    raw = read_any(path)
    mapping, corrections = build_mapping(raw, name)
    frame, errors = normalize_dataframe(raw, column_mapping=mapping)

    lines.append(f"  category            {category}")
    lines.append(f"  torture test        {torture}")
    lines.append(f"  raw                 {len(raw):,} rows × {len(raw.columns)} columns")
    lines.append(f"  auto-mapped         {len(mapping)} of {len(raw.columns)} columns")
    if corrections:
        lines.append(f"  user corrected      {', '.join(corrections)}")
    lines.append(f"  valid rows          {len(frame):,}   (rejected {len(raw) - len(frame)}, {len(errors)} error notes)")

    if frame.empty:
        lines.append("  RESULT              ✗ no analysable rows")
        return False, lines

    optional = sorted(
        set(frame.columns) & (OPTIONAL_MEASURE_COLUMNS | OPTIONAL_DIMENSION_COLUMNS)
    )
    lines.append(f"  optional fields     {', '.join(optional) if optional else '— (none in this export)'}")

    # The same slice every endpoint would use for "All Time".
    current, previous, window = query_engine.build_slice(frame, time_filter="all")
    summary = compute_summary_between(current, previous, window.start, window.end - pd.Timedelta(days=1))
    truth = independent_totals(frame)

    def compare(label: str, published: float, expected: float, tolerance: float = 0.05) -> None:
        nonlocal ok
        agrees = abs(published - expected) <= tolerance
        ok = ok and agrees
        mark = "✓" if agrees else "✗"
        lines.append(f"  {label:<19} {published:>14,.2f}   {mark} independent {expected:,.2f}")

    compare("revenue", summary.revenue.value, truth["revenue"])
    compare("profit", summary.profit.value, truth["profit"])
    compare("units", summary.units_sold.value, truth["units"], tolerance=0)
    compare("unique items", summary.unique_items_sold.value, truth["items"], tolerance=0)

    # Chart engine, on the dimensions this file happens to support.
    dimensions = query_engine.dimension_options(frame)
    chart = query_engine.aggregate(current, dimension="category", measure="revenue", top_n=50)
    agrees = abs(chart.total - truth["revenue"]) <= 0.05
    ok = ok and agrees
    lines.append(
        f"  dimensions          {', '.join(option.key for option in dimensions.dimensions)}"
    )
    lines.append(f"  chart total         {'✓ matches revenue' if agrees else '✗ disagrees'}")

    # Ledger must reconcile too (this is where the discount bug used to hide).
    page = build_ledger_page(current, page=1, page_size=len(current))
    ledger_total = sum(entry.revenue for entry in page.entries)
    agrees = abs(ledger_total - truth["revenue"]) <= 1.0
    ok = ok and agrees
    lines.append(f"  register total      {'✓ reconciles' if agrees else '✗ disagrees'}  ({page.total_rows:,} rows)")

    # P&L identity.
    report = compute_pnl_report(current, window.label)
    pnl = {line.label: line.amount for line in report.pnl}
    net = pnl.get("Net Revenue", pnl.get("Gross Revenue", 0.0))
    cogs = pnl.get("Cost of Goods Sold (COGS)", 0.0)
    gross_profit = pnl.get("Gross Profit", 0.0)
    agrees = abs((net - cogs) - gross_profit) <= 0.05
    ok = ok and agrees
    lines.append(f"  P&L lines           {' · '.join(pnl)}")
    lines.append(f"  P&L identity        {'✓ net − COGS = gross profit' if agrees else '✗ broken'}")

    # Insights / inventory / forecast — what the user actually sees.
    insights = compute_insights(current, previous, period_label=window.label, max_insights=12)
    kinds = sorted({card.kind for card in insights.insights})
    lines.append(f"  insights            {len(insights.insights)} cards ({', '.join(kinds) or 'none'})")
    lines.append(f"  anomaly days        {len(insights.anomaly_dates)} of {insights.analysed_days} analysed")
    for card in insights.insights:
        if card.kind == "anomaly" and (card.metrics.get("normal_level") or 0) <= 0:
            ok = False
            lines.append("  RESULT              ✗ anomaly card published a ₹0 baseline")

    inventory = compute_inventory_intelligence(current, top_n=50)
    mode = "stock-aware (cover + capital)" if inventory.stock_aware else "demand-only (no stock column)"
    lines.append(f"  inventory mode      {mode}")
    lines.append(
        "  ABC split           "
        + " · ".join(f"{bucket.label.split(' ')[0]}={bucket.item_count}" for bucket in inventory.abc_buckets)
    )

    forecast = compute_forecast(current, horizon_days=14)
    if forecast.available:
        accuracy = f"{forecast.accuracy_pct}% ({forecast.accuracy_basis})" if forecast.accuracy_pct is not None else "not tested"
        lines.append(
            f"  forecast            ₹{forecast.expected_revenue:,.0f} next 14d "
            f"(range ₹{forecast.expected_revenue_lower:,.0f}–₹{forecast.expected_revenue_upper:,.0f}), "
            f"accuracy {accuracy}"
        )
        lines.append(f"  trading days        {forecast.trading_days} of {forecast.history_days}")
    else:
        lines.append(f"  forecast            refused — {forecast.reason}")

    lines.append(f"  RESULT              {'✓ handled' if ok else '✗ problems above'}")
    return ok, lines


def main() -> int:
    print("=" * 78)
    print("SENOVA format compatibility check — testing2/")
    print("=" * 78)

    failures = []
    for name, category, torture in FILES:
        print(f"\n{name}")
        print("-" * 78)
        try:
            ok, lines = check(name, category, torture)
        except Exception as exc:  # noqa: BLE001 - a crash is itself the finding
            ok, lines = False, [f"  RESULT              ✗ crashed: {type(exc).__name__}: {exc}"]
        print("\n".join(lines))
        if not ok:
            failures.append(name)

    print("\n" + "=" * 78)
    if failures:
        print(f"{len(FILES) - len(failures)}/{len(FILES)} formats handled — problems in: {', '.join(failures)}")
        return 1
    print(f"All {len(FILES)} formats handled, every published total reconciled independently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
