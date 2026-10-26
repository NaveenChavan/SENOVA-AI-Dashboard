"""
Core analytics engine — pure Pandas transformations.

Every public function receives a DataFrame that has already passed through
``normalize_dataframe()``, so columns are guaranteed to exist and have the
correct types. No re-coercion needed.

Single code path, on purpose
---------------------------
There used to be a second, preset-based set of helpers here (``compute_summary``
by ``time_filter``, ``apply_time_filter``, ``run_full_analysis``). It was dead
once the shared query layer landed, and keeping it around is exactly how the
register ended up reporting gross revenue while the P&L reported net. Slicing
now happens in one place (``query_engine.build_slice``) and every function below
takes the already-sliced frame.
"""

import math

import pandas as pd

from app.models.schemas import (
    CategoryBreakdown,
    CategoryLedgerRow,
    CAReportSummary,
    DailyTrend,
    DeadStockItem,
    LedgerEntry,
    LedgerPage,
    MetricValue,
    PnLLineItem,
    SalesSummary,
    TopItem,
)

# ── Public helpers called by the route handler ─────────────────────────────

def _zero_fill_daily(
    daily_agg: pd.DataFrame,
    start_date,
    end_date,
) -> pd.DataFrame:
    """Generate every calendar day in [start, end] and fill missing rows with 0."""
    all_dates = pd.date_range(start=start_date, end=end_date, freq="D")
    calendar = pd.DataFrame({"_day": [d.date() for d in all_dates]})
    filled = calendar.merge(daily_agg, on="_day", how="left")
    for col in daily_agg.columns:
        if col != "_day":
            filled[col] = filled[col].fillna(0.0)
    return filled.sort_values("_day")


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add the per-row derived columns every aggregation below relies on, so
    each groupby can stay a plain ``.agg()`` call.

    Columns added:

    ``_row_gross_revenue``  Quantity × Selling Price (or Line Total directly)
    ``_row_discount``       the mapped Discount column, or 0 when absent
    ``_row_revenue``        gross revenue **net of discount** (never below 0)
    ``_row_cost``           Quantity × Cost Price (or NaN when cost absent)
    ``_row_profit``         net revenue − cost (or NaN when cost absent)
    ``_row_tax``            the mapped Tax column, or 0 when absent
    """
    out = df.copy()
    has_unit_basis = "Quantity" in out.columns and "Selling Price" in out.columns
    has_line_total = "Line Total" in out.columns
    if has_unit_basis:
        by_unit = out["Quantity"] * out["Selling Price"]
        if has_line_total:
            # A valid line total can rescue a row whose optional quantity/price
            # cells are blank, while complete quantity × price remains preferred.
            fallback = pd.to_numeric(out["Line Total"], errors="coerce")
            out["_row_gross_revenue"] = by_unit.where(by_unit.notna(), fallback)
        else:
            out["_row_gross_revenue"] = by_unit
    elif has_line_total:
        out["_row_gross_revenue"] = pd.to_numeric(out["Line Total"], errors="coerce")
    else:
        # Accepted normalized uploads always have a supported sales basis. Keep
        # unexpected direct calls unavailable rather than inventing zero revenue.
        out["_row_gross_revenue"] = pd.Series(float("nan"), index=out.index)

    if "Discount" in out.columns:
        out["_row_discount"] = out["Discount"].fillna(0.0)
        out["_row_revenue"] = (out["_row_gross_revenue"] - out["_row_discount"]).clip(lower=0.0)
    elif "MRP" in out.columns and "Quantity" in out.columns and "Selling Price" in out.columns:
        mrp_discount = ((out["MRP"] - out["Selling Price"]) * out["Quantity"]).clip(lower=0.0)
        invalid_mrp = out["MRP"].isna() | (out["MRP"] <= 0) | (out["MRP"] < out["Selling Price"])
        out["_row_discount"] = mrp_discount.mask(invalid_mrp, 0.0)
        out["_row_revenue"] = out["_row_gross_revenue"]
    else:
        out["_row_discount"] = 0.0
        out["_row_revenue"] = out["_row_gross_revenue"]

    if "Quantity" in out.columns and "Cost Price" in out.columns:
        out["_row_cost"] = out["Quantity"] * out["Cost Price"]
        out["_row_profit"] = out["_row_revenue"] - out["_row_cost"]
    else:
        # Cost Price is a unit cost. Without quantity we cannot turn it into a
        # transaction cost, so profit must remain unavailable rather than use
        # the unit price as if it were the total cost.
        out["_row_cost"] = pd.Series(float("nan"), index=out.index)
        out["_row_profit"] = pd.Series(float("nan"), index=out.index)

    out["_row_tax"] = out["Tax"].fillna(0.0) if "Tax" in out.columns else 0.0
    return out

# ── KPI computation ────────────────────────────────────────────────────────

def compute_summary_between(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    spark_start=None,
    spark_end=None,
) -> SalesSummary:
    """
    Build the KPI block from two explicit frames: the period being viewed and
    the period immediately before it.

    Splitting this out lets custom date ranges (the Pro filter panel) reuse
    exactly the same KPI maths as the presets — the caller decides what
    "previous" means, this function only aggregates.

    ``spark_start`` / ``spark_end`` bound the sparkline's calendar so days
    with no sales show as zeros instead of being silently skipped, which
    otherwise makes a 7-day and a 30-day sparkline look identical.
    """
    prepped_curr = _prepare(current)
    prepped_prev = _prepare(previous)

    has_quantity = (
        "Quantity" in current.columns
        and (current.empty or current["Quantity"].notna().all())
    )
    has_cost = (
        has_quantity
        and "Cost Price" in current.columns
        and (current.empty or current["Cost Price"].notna().all())
    )
    has_item = (
        "Item" in current.columns
        and (current.empty or current["Item"].astype(str).ne("Unspecified").any())
    )

    def _trend(cur: float, prev: float) -> float:
        """Percentage change, treating "no previous data" as 0% rather than infinity."""
        if prev == 0:
            return 0.0
        return round(((cur - prev) / prev) * 100, 2)

    # Totals for the visible period.
    if not prepped_curr.empty:
        rev = float(prepped_curr["_row_revenue"].sum())
        cost = float(prepped_curr["_row_cost"].dropna().sum()) if has_cost else 0.0
        profit = float(prepped_curr["_row_profit"].dropna().sum()) if has_cost else 0.0
        units = int(prepped_curr["Quantity"].sum()) if has_quantity else 0
        unique = int(prepped_curr.loc[prepped_curr["Item"].astype(str) != "Unspecified", "Item"].nunique()) if has_item else 0
    else:
        rev, cost, profit, units, unique = 0.0, 0.0, 0.0, 0, 0

    # Same totals for the comparison period (drives the trend arrows).
    if not prepped_prev.empty:
        rev_p = float(prepped_prev["_row_revenue"].sum())
        cost_p = float(prepped_prev["_row_cost"].dropna().sum()) if has_cost else 0.0
        profit_p = float(prepped_prev["_row_profit"].dropna().sum()) if has_cost else 0.0
        units_p = int(prepped_prev["Quantity"].sum()) if has_quantity else 0
    else:
        rev_p, cost_p, profit_p, units_p = 0.0, 0.0, 0.0, 0

    # Sparklines: one point per calendar day in the window, zero-filled.
    if prepped_curr.empty:
        spark_rev, spark_profit, spark_cost, spark_units = [], [], [], []
    else:
        agg_map = {"revenue": ("_row_revenue", "sum")}
        if has_cost:
            agg_map["profit"] = ("_row_profit", "sum")
            agg_map["cost"] = ("_row_cost", "sum")
        if has_quantity:
            agg_map["units"] = ("Quantity", "sum")

        daily = (
            prepped_curr.assign(_day=prepped_curr["Date"].dt.date)
            .groupby("_day", as_index=False)
            .agg(**agg_map)
            .sort_values("_day")
        )
        start = spark_start if spark_start is not None else prepped_curr["Date"].min()
        end = spark_end if spark_end is not None else prepped_curr["Date"].max()
        daily_filled = _zero_fill_daily(daily, start, end)
        spark_rev = [round(v, 2) for v in daily_filled["revenue"].tolist()]
        spark_profit = [round(v, 2) for v in daily_filled["profit"].tolist()] if has_cost else []
        spark_cost = [round(v, 2) for v in daily_filled["cost"].tolist()] if has_cost else []
        spark_units = [float(v) for v in daily_filled["units"].tolist()] if has_quantity else []

    profit_metric = (
        MetricValue(
            value=round(profit, 2),
            trend_percentage=_trend(profit, profit_p),
            sparkline_data=spark_profit,
            available=True,
        )
        if has_cost
        else MetricValue(
            value=None,
            trend_percentage=None,
            sparkline_data=[],
            available=False,
            reason=(
                "Not available: needs Quantity and Cost Price"
                if "Cost Price" in current.columns and not has_quantity
                else "Not available: needs Cost Price"
            ),
        )
    )

    cost_metric = (
        MetricValue(
            value=round(cost, 2),
            trend_percentage=_trend(cost, cost_p),
            sparkline_data=spark_cost,
            available=True,
        )
        if has_cost
        else MetricValue(
            value=None,
            trend_percentage=None,
            sparkline_data=[],
            available=False,
            reason=(
                "Not available: needs Quantity and Cost Price"
                if "Cost Price" in current.columns and not has_quantity
                else "Not available: needs Cost Price"
            ),
        )
    )

    units_metric = (
        MetricValue(
            value=units,
            trend_percentage=_trend(float(units), float(units_p)),
            sparkline_data=spark_units,
            available=True,
        )
        if has_quantity
        else MetricValue(
            value=None,
            trend_percentage=None,
            sparkline_data=[],
            available=False,
            reason="Not available: needs Quantity",
        )
    )

    unique_metric = (
        MetricValue(
            value=unique,
            trend_percentage=0.0,
            sparkline_data=[],
            available=True,
        )
        if has_item
        else MetricValue(
            value=None,
            trend_percentage=None,
            sparkline_data=[],
            available=False,
            reason="Not available: needs Item",
        )
    )

    return SalesSummary(
        revenue=MetricValue(
            value=round(rev, 2),
            trend_percentage=_trend(rev, rev_p),
            sparkline_data=spark_rev,
            available=True,
        ),
        profit=profit_metric,
        cost=cost_metric,
        units_sold=units_metric,
        unique_items_sold=unique_metric,
    )

def compute_top_items(df: pd.DataFrame, top_n: int = 5) -> list[TopItem]:
    """Rank items by total quantity sold descending (or revenue if quantity absent)."""
    if df.empty or "Item" not in df.columns:
        return []
    prepped = _prepare(df)
    if "Quantity" in prepped.columns:
        grouped = (
            prepped.groupby("Item", as_index=False)
            .agg(quantity=("Quantity", "sum"), revenue=("_row_revenue", "sum"))
            .sort_values("quantity", ascending=False)
            .head(top_n)
        )
        return [
            TopItem(
                name=str(row["Item"]),
                quantity=int(row["quantity"]),
                revenue=round(float(row["revenue"]), 2),
            )
            for _, row in grouped.iterrows()
        ]
    else:
        grouped = (
            prepped.groupby("Item", as_index=False)
            .agg(revenue=("_row_revenue", "sum"))
            .sort_values("revenue", ascending=False)
            .head(top_n)
        )
        return [
            TopItem(
                name=str(row["Item"]),
                quantity=0,
                revenue=round(float(row["revenue"]), 2),
            )
            for _, row in grouped.iterrows()
        ]

def compute_daily_trend_between(df: pd.DataFrame, start, end) -> list[DailyTrend]:
    """
    Daily revenue & profit for an explicit window, zero-filled day by day.

    The Pro query layer already knows the exact window it sliced (including
    custom date ranges), so it passes the bounds in rather than re-deriving
    them from a preset name. ``end`` is inclusive here — callers holding an
    exclusive bound should pass ``end - 1 day``.
    """
    if df.empty or "Date" not in df.columns:
        return []

    prepped = _prepare(df)
    has_cost = (
        "Quantity" in df.columns
        and "Cost Price" in df.columns
        and df["Quantity"].notna().all()
        and df["Cost Price"].notna().all()
    )
    agg_kwargs = {"revenue": ("_row_revenue", "sum")}
    if has_cost:
        agg_kwargs["profit"] = ("_row_profit", "sum")
    else:
        prepped["_dummy_profit"] = 0.0
        agg_kwargs["profit"] = ("_dummy_profit", "sum")

    daily = (
        prepped.assign(_day=prepped["Date"].dt.date)
        .groupby("_day", as_index=False)
        .agg(**agg_kwargs)
        .sort_values("_day")
    )
    filled = _zero_fill_daily(daily, start, end).rename(columns={"_day": "Date"})

    return [
        DailyTrend(
            date=str(row["Date"]),
            revenue=round(float(row["revenue"]), 2),
            profit=round(float(row["profit"]), 2) if has_cost else None,
        )
        for _, row in filled.iterrows()
    ]


def compute_dead_stock(df: pd.DataFrame, threshold_qty: int = 5) -> list[DeadStockItem]:
    """Identify items that sold very few units (or zero) over the analysed period."""
    if df.empty or "Item" not in df.columns or "Quantity" not in df.columns or "Date" not in df.columns:
        return []
    today = df["Date"].max()

    total_by_item = (
        df.groupby("Item", as_index=False)["Quantity"].sum()
    )
    low_sellers = total_by_item[total_by_item["Quantity"] <= threshold_qty]

    last_sale = (
        df.groupby("Item", as_index=False)["Date"].max()
        .rename(columns={"Date": "last_sale_date"})
    )
    last_sale["days_since_last_sale"] = (
        (today - last_sale["last_sale_date"]).dt.days.fillna(0).astype(int)
    )

    merged = low_sellers.merge(last_sale, on="Item", how="left").fillna(0)

    return [
        DeadStockItem(
            name=str(row["Item"]),
            total_quantity=int(row["Quantity"]),
            days_since_last_sale=int(row["days_since_last_sale"]),
        )
        for _, row in merged.iterrows()
    ]

def compute_data_date_range(df: pd.DataFrame) -> dict:
    """
    Return the actual min/max transaction date and the whole-day span
    between them, for a normalised (already-validated) DataFrame.

    Used right after upload so the frontend can disable date-filter
    buttons that are wider than the data itself — e.g. a 4-day sample file
    makes "Last 7 Days", "This Month", and "Last 30 Days" all identical to
    "All Time", which looks broken if the UI doesn't explain why.
    """
    if df.empty or "Date" not in df.columns:
        return {"min_date": None, "max_date": None, "span_days": 0}

    min_date = df["Date"].min()
    max_date = df["Date"].max()
    if pd.isna(min_date) or pd.isna(max_date):
        return {"min_date": None, "max_date": None, "span_days": 0}

    span_days = (max_date.normalize() - min_date.normalize()).days + 1
    return {
        "min_date": str(min_date.date()),
        "max_date": str(max_date.date()),
        "span_days": int(span_days),
    }


def compute_revenue_by_category(df: pd.DataFrame) -> list[CategoryBreakdown]:
    """Aggregate revenue & quantity by category for the donut chart."""
    if df.empty or "Category" not in df.columns:
        return []
    prepped = _prepare(df)
    has_quantity = "Quantity" in prepped.columns and prepped["Quantity"].notna().all()
    agg_kwargs = {"revenue": ("_row_revenue", "sum")}
    if has_quantity:
        agg_kwargs["quantity"] = ("Quantity", "sum")

    grouped = (
        prepped.groupby("Category", as_index=False, dropna=False)
        .agg(**agg_kwargs)
        .sort_values("revenue", ascending=False)
    )

    return [
        CategoryBreakdown(
            category=str(row["Category"]),
            revenue=round(float(row["revenue"]), 2),
            quantity=(int(row["quantity"]) if has_quantity else None),
        )
        for _, row in grouped.iterrows()
    ]

# ── CA-style (Chartered Accountant) reporting ───────────────────────────────

def compute_pnl_report(df: pd.DataFrame, period_label: str) -> CAReportSummary:
    """
    Build a Profit & Loss statement + category-wise ledger the way an
    accountant presents them on paper: labelled line items with a running
    subtotal/total, not just numbers scattered across chart widgets.

    ``df`` must already be normalised AND time-filtered by the caller —
    this function only aggregates, it doesn't slice by date itself.
    """
    if df.empty or "Date" not in df.columns:
        return CAReportSummary(
            period_label=period_label,
            period_start="",
            period_end="",
            pnl=[],
            category_ledger=[],
            total_transactions=0,
        )

    prepped = _prepare(df)
    gross = float(prepped["_row_gross_revenue"].sum())
    discount = float(prepped["_row_discount"].sum()) if "Discount" in df.columns else 0.0
    tax = float(prepped["_row_tax"].sum()) if "Tax" in df.columns else 0.0
    revenue = float(prepped["_row_revenue"].sum())
    has_quantity = (
        "Quantity" in df.columns
        and (df.empty or df["Quantity"].notna().all())
    )
    has_cost = (
        has_quantity
        and "Cost Price" in df.columns
        and (df.empty or df["Cost Price"].notna().all())
    )
    cost = float(prepped["_row_cost"].sum()) if has_cost else 0.0
    profit = (revenue - cost) if has_cost else 0.0

    def _pct(amount: float) -> float | None:
        """Share of net revenue, or None when there's no revenue to divide by."""
        if revenue == 0:
            return None
        return round((amount / revenue) * 100, 2)

    pnl: list[PnLLineItem] = []
    if discount > 0:
        pnl.append(
            PnLLineItem(label="Gross Sales (before discount)", amount=round(gross, 2), percentage_of_revenue=_pct(gross))
        )
        pnl.append(
            PnLLineItem(label="Less: Discounts Allowed", amount=round(discount, 2), percentage_of_revenue=_pct(discount))
        )
        pnl.append(
            PnLLineItem(label="Net Revenue", amount=round(revenue, 2), percentage_of_revenue=100.0, is_subtotal=True)
        )
    else:
        pnl.append(
            PnLLineItem(label="Gross Revenue", amount=round(revenue, 2), percentage_of_revenue=100.0 if revenue else None)
        )

    if has_cost:
        pnl.append(
            PnLLineItem(label="Cost of Goods Sold (COGS)", amount=round(cost, 2), percentage_of_revenue=_pct(cost))
        )
        pnl.append(
            PnLLineItem(label="Gross Profit", amount=round(profit, 2), percentage_of_revenue=_pct(profit), is_subtotal=True)
        )
    else:
        missing_cost_inputs = []
        if not has_quantity:
            missing_cost_inputs.append("Quantity")
        if "Cost Price" not in df.columns or not df["Cost Price"].notna().all():
            missing_cost_inputs.append("Cost Price")
        reason = "Not available: needs " + " and ".join(missing_cost_inputs or ["Cost Price"])
        pnl.append(
            PnLLineItem(
                label="Cost of Goods Sold (COGS)", amount=None,
                availability_reason=reason,
                percentage_of_revenue=None,
            )
        )
        pnl.append(
            PnLLineItem(
                label="Gross Profit", amount=None,
                availability_reason=reason,
                percentage_of_revenue=None,
                is_subtotal=True,
            )
        )
    if tax > 0:
        pnl.append(
            PnLLineItem(label="GST / Tax Collected (memo)", amount=round(tax, 2), percentage_of_revenue=_pct(tax))
        )

    # Category-wise ledger. Optional fields stay null when they cannot be
    # computed; do not emit zeros for unknown quantity/cost/profit.
    category_ledger = []
    if "Category" in prepped.columns:
        agg_map = {"revenue": ("_row_revenue", "sum")}
        if has_quantity:
            agg_map["units_sold"] = ("Quantity", "sum")
        if has_cost:
            agg_map["cost"] = ("_row_cost", "sum")
            agg_map["profit"] = ("_row_profit", "sum")

        grouped = (
            prepped.groupby("Category", as_index=False, dropna=False)
            .agg(**agg_map)
            .sort_values("revenue", ascending=False)
        )

        category_ledger = [
            CategoryLedgerRow(
                category=str(row["Category"]),
                units_sold=(int(row["units_sold"]) if has_quantity else None),
                revenue=round(float(row["revenue"]), 2),
                cost=(round(float(row["cost"]), 2) if has_cost else None),
                profit=(round(float(row["profit"]), 2) if has_cost else None),
                margin_percentage=(
                    round((float(row["profit"]) / float(row["revenue"]) * 100), 2)
                    if has_cost and row["revenue"] else (0.0 if has_cost else None)
                ),
            )
            for _, row in grouped.iterrows()
        ]

    return CAReportSummary(
        period_label=period_label,
        period_start=str(df["Date"].min().date()),
        period_end=str(df["Date"].max().date()),
        pnl=pnl,
        category_ledger=category_ledger,
        total_transactions=len(df),
    )


def build_ledger_page(df: pd.DataFrame, page: int, page_size: int) -> LedgerPage:
    """
    Slice ``df`` (already normalised, NOT necessarily time-filtered — the
    ledger view lets the accountant browse every transaction) into a single
    page of ``LedgerEntry`` rows, sorted chronologically like a real sales
    register/day-book.
    """
    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 1
    page = max(1, min(page, total_pages))

    if total_rows == 0:
        return LedgerPage(entries=[], page=page, page_size=page_size, total_rows=0, total_pages=1)

    prepped = _prepare(df)
    ordered = prepped.sort_values("Date", kind="stable").reset_index(drop=False)
    start = (page - 1) * page_size
    chunk = ordered.iloc[start : start + page_size]

    entries = [
        LedgerEntry(
            row=int(r["index"]),
            date=str(r["Date"].date()) if pd.notna(r["Date"]) else "",
            category=str(r["Category"]) if "Category" in r and pd.notna(r["Category"]) else "",
            item=str(r["Item"]) if "Item" in r and pd.notna(r["Item"]) else "",
            quantity=(int(r["Quantity"]) if "Quantity" in r and pd.notna(r["Quantity"]) else None),
            selling_price=(round(float(r["Selling Price"]), 2) if "Selling Price" in r and pd.notna(r["Selling Price"]) else None),
            cost_price=(round(float(r["Cost Price"]), 2) if "Cost Price" in r and pd.notna(r["Cost Price"]) else None),
            discount=round(float(r["_row_discount"]), 2),
            revenue=(round(float(r["_row_revenue"]), 2) if pd.notna(r["_row_revenue"]) else None),
            profit=(round(float(r["_row_profit"]), 2) if pd.notna(r["_row_profit"]) else None),
        )
        for _, r in chunk.iterrows()
    ]

    return LedgerPage(
        entries=entries,
        page=page,
        page_size=page_size,
        total_rows=total_rows,
        total_pages=total_pages,
    )


def compute_daily_financial_summary(df: pd.DataFrame, start=None, end=None) -> list[dict]:
    """Return daily report totals without fabricating unavailable measures.

    Revenue and transaction count come from the accepted sales basis. Units are
    emitted only when Quantity is complete, and cost/profit/margin only when
    both Quantity and Cost Price are available for every row in the slice.
    """
    if df.empty and (start is None or end is None):
        return []

    prepped = _prepare(df)
    if start is None:
        start = prepped["Date"].min()
    if end is None:
        end = prepped["Date"].max()
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    if start > end:
        return []

    has_quantity = (
        "Quantity" in df.columns
        and (df.empty or df["Quantity"].notna().all())
    )
    has_cost = (
        has_quantity
        and "Cost Price" in df.columns
        and (df.empty or df["Cost Price"].notna().all())
    )

    if prepped.empty:
        columns = ["_day", "transactions", "revenue"]
        if has_quantity:
            columns.append("units_sold")
        if has_cost:
            columns.extend(["cost", "profit"])
        daily = pd.DataFrame(columns=columns)
    else:
        agg_map = {
            "transactions": ("_row_revenue", "size"),
            "revenue": ("_row_revenue", "sum"),
        }
        if has_quantity:
            agg_map["units_sold"] = ("Quantity", "sum")
        if has_cost:
            agg_map["cost"] = ("_row_cost", "sum")
            agg_map["profit"] = ("_row_profit", "sum")
        daily = (
            prepped.assign(_day=prepped["Date"].dt.normalize())
            .groupby("_day", as_index=False)
            .agg(**agg_map)
        )

    calendar = pd.DataFrame({"_day": pd.date_range(start, end, freq="D")})
    merged = calendar.merge(daily, on="_day", how="left")
    for col in ["transactions", "revenue"]:
        merged[col] = merged[col].fillna(0)
    if has_quantity:
        merged["units_sold"] = merged["units_sold"].fillna(0)
    if has_cost:
        merged["cost"] = merged["cost"].fillna(0)
        merged["profit"] = merged["profit"].fillna(0)

    result = []
    for _, row in merged.iterrows():
        revenue = float(row["revenue"])
        profit = float(row["profit"]) if has_cost else None
        result.append({
            "date": pd.Timestamp(row["_day"]).date().isoformat(),
            "transactions": int(row["transactions"]),
            "units_sold": (int(row["units_sold"]) if has_quantity else None),
            "revenue": round(revenue, 2),
            "cost": (round(float(row["cost"]), 2) if has_cost else None),
            "profit": (round(profit, 2) if profit is not None else None),
            "margin_percentage": (
                round((profit / revenue) * 100, 2) if has_cost and revenue else (0.0 if has_cost else None)
            ),
        })
    return result

