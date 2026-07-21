"""
Core analytics engine — pure Pandas transformations.

Every public function receives a DataFrame that has already passed through
``normalize_dataframe()``, so columns are guaranteed to exist and have the
correct types.  No re-coercion needed.
"""

from datetime import timedelta
import math
import pandas as pd

from app.models.schemas import (
    AnalyticsResponse,
    CategoryBreakdown,
    CategoryLedgerRow,
    CAReportSummary,
    DailyTrend,
    DeadStockItem,
    LedgerEntry,
    LedgerPage,
    MetricValue,
    PnLLineItem,
    RowError,
    SalesSummary,
    TopItem,
)
from app.utils.data_validator import normalize_dataframe

# ── Public helpers called by the route handler ─────────────────────────────

def _get_expected_range(df: pd.DataFrame, time_filter: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) calendar range for zero-filling sparklines / trend.

    For ``"all"`` it returns the data's actual min/max; for all other filters
    it aligns to the calendar window the user expects to see.
    """
    max_date = df["Date"].max()
    if time_filter == "all":
        return df["Date"].min(), max_date
    if time_filter == "today":
        return max_date.normalize(), max_date
    if time_filter == "30days":
        return max_date - timedelta(days=30), max_date
    if time_filter == "week":
        return max_date - timedelta(days=7), max_date
    if time_filter == "month":
        return max_date.replace(day=1).normalize(), max_date
    return df["Date"].min(), max_date


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
    Add pre-computed per-row derived columns so every groupby below can use
    plain ``.agg()``.
    """
    out = df.copy()
    out["_row_revenue"] = out["Quantity"] * out["Selling Price"]
    out["_row_cost"] = out["Quantity"] * out["Cost Price"]
    out["_row_profit"] = out["_row_revenue"] - out["_row_cost"]
    return out

# ── Time-filter helpers ────────────────────────────────────────────────────

def filter_by_time(df: pd.DataFrame, time_filter: str) -> pd.DataFrame:
    """Slice ``df`` to rows whose ``Date`` falls within the requested window."""
    if time_filter == "all" or df.empty:
        return df

    max_date = df["Date"].max()
    if pd.isna(max_date):
        return df.iloc[0:0]

    if time_filter == "today":
        day_start = max_date.normalize()
        day_end = day_start + timedelta(days=1)
        return df[(df["Date"] >= day_start) & (df["Date"] < day_end)].copy()

    if time_filter == "week":
        cutoff = max_date - timedelta(days=7)
        return df[df["Date"] >= cutoff].copy()

    if time_filter == "30days":
        cutoff = max_date - timedelta(days=30)
        return df[df["Date"] >= cutoff].copy()

    if time_filter == "month":
        cutoff = max_date.replace(day=1).normalize()
        return df[df["Date"] >= cutoff].copy()

    return df

def _split_periods(df: pd.DataFrame, time_filter: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the full DataFrame into *current* and *previous* periods."""
    if df.empty:
        return df, df

    max_date = df["Date"].max()

    # CRITICAL FIX: "All Time" means the ENTIRE dataset. No previous period.
    if time_filter == "all":
        return df, df.iloc[0:0]

    if time_filter == "today":
        day_start = max_date.normalize()
        day_end = day_start + timedelta(days=1)
        prev_start = day_start - timedelta(days=1)
        current = df[(df["Date"] >= day_start) & (df["Date"] < day_end)]
        previous = df[(df["Date"] >= prev_start) & (df["Date"] < day_start)]
        return current, previous

    if time_filter == "30days":
        curr_start = max_date - timedelta(days=30)
        prev_end = curr_start
        prev_start = prev_end - timedelta(days=30)
        current = df[df["Date"] >= curr_start]
        previous = df[(df["Date"] >= prev_start) & (df["Date"] < prev_end)]
        return current, previous

    if time_filter == "week":
        curr_start = max_date - timedelta(days=7)
        prev_end = curr_start
        prev_start = prev_end - timedelta(days=7)
        current = df[df["Date"] >= curr_start]
        previous = df[(df["Date"] >= prev_start) & (df["Date"] < prev_end)]
        return current, previous

    if time_filter == "month":
        curr_start = max_date.replace(day=1).normalize()
        prev_end = curr_start
        prev_start = (prev_end - timedelta(days=1)).replace(day=1).normalize()
        current = df[df["Date"] >= curr_start]
        previous = df[(df["Date"] >= prev_start) & (df["Date"] < prev_end)]
        return current, previous

    return df, df.iloc[0:0]

# ── KPI computation ────────────────────────────────────────────────────────

def compute_summary(df: pd.DataFrame, time_filter: str = "all") -> SalesSummary:
    """Aggregate top-level KPIs. Uses the full raw DataFrame to properly split."""
    current, previous = _split_periods(df, time_filter)

    prepped_curr = _prepare(current)
    prepped_prev = _prepare(previous)

    def _trend(cur: float, prev: float) -> float:
        if prev == 0:
            return 0.0
        return round(((cur - prev) / prev) * 100, 2)

    # Calculate exact totals based ONLY on the isolated period dataframe
    if not prepped_curr.empty:
        rev = float(prepped_curr["_row_revenue"].sum())
        cost = float(prepped_curr["_row_cost"].sum())
        profit = float(prepped_curr["_row_profit"].sum())
        units = int(prepped_curr["Quantity"].sum())
        unique = int(prepped_curr["Item"].nunique())
    else:
        rev, cost, profit, units, unique = 0.0, 0.0, 0.0, 0, 0

    if not prepped_prev.empty:
        rev_p = float(prepped_prev["_row_revenue"].sum())
        cost_p = float(prepped_prev["_row_cost"].sum())
        profit_p = float(prepped_prev["_row_profit"].sum())
        units_p = int(prepped_prev["Quantity"].sum())
    else:
        rev_p, cost_p, profit_p, units_p = 0.0, 0.0, 0.0, 0

    # Sparkline daily grouping — zero-fill calendar gaps so week vs month
    # always produce visually distinct sparklines even when data has gaps.
    if prepped_curr.empty:
        spark_rev, spark_profit, spark_cost, spark_units = [], [], [], []
    else:
        daily = (
            prepped_curr.assign(_day=prepped_curr["Date"].dt.date)
            .groupby("_day", as_index=False)
            .agg(
                revenue=("_row_revenue", "sum"),
                profit=("_row_profit", "sum"),
                cost=("_row_cost", "sum"),
                units=("Quantity", "sum"),
            )
            .sort_values("_day")
        )
        spark_start, spark_end = _get_expected_range(df, time_filter)
        daily_filled = _zero_fill_daily(daily, spark_start, spark_end)
        spark_rev = [round(v, 2) for v in daily_filled["revenue"].tolist()]
        spark_profit = [round(v, 2) for v in daily_filled["profit"].tolist()]
        spark_cost = [round(v, 2) for v in daily_filled["cost"].tolist()]
        spark_units = [float(v) for v in daily_filled["units"].tolist()]

    return SalesSummary(
        revenue=MetricValue(
            value=round(rev, 2),
            trend_percentage=_trend(rev, rev_p),
            sparkline_data=spark_rev,
        ),
        profit=MetricValue(
            value=round(profit, 2),
            trend_percentage=_trend(profit, profit_p),
            sparkline_data=spark_profit,
        ),
        cost=MetricValue(
            value=round(cost, 2),
            trend_percentage=_trend(cost, cost_p),
            sparkline_data=spark_cost,
        ),
        units_sold=MetricValue(
            value=units,
            trend_percentage=_trend(float(units), float(units_p)),
            sparkline_data=spark_units,
        ),
        unique_items_sold=MetricValue(value=unique, trend_percentage=0.0, sparkline_data=[]),
    )

def compute_top_items(df: pd.DataFrame, top_n: int = 5) -> list[TopItem]:
    """Rank items by total quantity sold descending."""
    prepped = _prepare(df)
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

def compute_daily_trend(df: pd.DataFrame, time_filter: str = "all") -> list[DailyTrend]:
    """Aggregate revenue & profit by date for the line chart.

    Zero-fills missing calendar days so the chart area always reflects the
    selected window (7 days for week, current month for month, etc.).
    """
    if df.empty:
        return []

    prepped = _prepare(df)
    daily = (
        prepped.assign(_day=prepped["Date"].dt.date)
        .groupby("_day", as_index=False)
        .agg(revenue=("_row_revenue", "sum"), profit=("_row_profit", "sum"))
        .sort_values("_day")
    )
    start, end = _get_expected_range(df, time_filter)
    daily_filled = _zero_fill_daily(daily, start, end).rename(columns={"_day": "Date"})

    return [
        DailyTrend(
            date=str(row["Date"]),
            revenue=round(float(row["revenue"]), 2),
            profit=round(float(row["profit"]), 2),
        )
        for _, row in daily_filled.iterrows()
    ]

def compute_dead_stock(df: pd.DataFrame, threshold_qty: int = 5) -> list[DeadStockItem]:
    """Identify items that sold very few units (or zero) over the analysed period."""
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
    prepped = _prepare(df)
    grouped = (
        prepped.groupby("Category", as_index=False)
        .agg(revenue=("_row_revenue", "sum"), quantity=("Quantity", "sum"))
        .sort_values("revenue", ascending=False)
    )

    return [
        CategoryBreakdown(
            category=str(row["Category"]),
            revenue=round(float(row["revenue"]), 2),
            quantity=int(row["quantity"]),
        )
        for _, row in grouped.iterrows()
    ]

# ── CA-style (Chartered Accountant) reporting ───────────────────────────────

def compute_pnl_report(df: pd.DataFrame, time_filter: str, period_label: str) -> CAReportSummary:
    """
    Build a Profit & Loss statement + category-wise ledger the way an
    accountant presents them on paper: labelled line items with a running
    subtotal/total, not just numbers scattered across chart widgets.

    ``df`` must already be normalised AND time-filtered by the caller —
    this function only aggregates, it doesn't slice by date itself.
    """
    if df.empty:
        return CAReportSummary(
            period_label=period_label,
            period_start="",
            period_end="",
            pnl=[],
            category_ledger=[],
            total_transactions=0,
        )

    prepped = _prepare(df)
    revenue = float(prepped["_row_revenue"].sum())
    cost = float(prepped["_row_cost"].sum())
    profit = revenue - cost

    def _pct(amount: float) -> float | None:
        if revenue == 0:
            return None
        return round((amount / revenue) * 100, 2)

    # Standard P&L presentation: Revenue, then COGS as a deduction,
    # then Gross Profit as the ruled-off subtotal, then margin as an
    # informational line beneath it.
    pnl = [
        PnLLineItem(label="Gross Revenue", amount=round(revenue, 2), percentage_of_revenue=100.0 if revenue else None),
        PnLLineItem(label="Cost of Goods Sold (COGS)", amount=round(cost, 2), percentage_of_revenue=_pct(cost)),
        PnLLineItem(label="Gross Profit", amount=round(profit, 2), percentage_of_revenue=_pct(profit), is_subtotal=True),
    ]

    # Category-wise ledger — same shape a CA would use for a "sales by
    # segment" schedule attached to the P&L.
    grouped = (
        prepped.groupby("Category", as_index=False)
        .agg(
            units_sold=("Quantity", "sum"),
            revenue=("_row_revenue", "sum"),
            cost=("_row_cost", "sum"),
            profit=("_row_profit", "sum"),
        )
        .sort_values("revenue", ascending=False)
    )

    category_ledger = [
        CategoryLedgerRow(
            category=str(row["category"]) if "category" in row else str(row["Category"]),
            units_sold=int(row["units_sold"]),
            revenue=round(float(row["revenue"]), 2),
            cost=round(float(row["cost"]), 2),
            profit=round(float(row["profit"]), 2),
            margin_percentage=round((row["profit"] / row["revenue"] * 100), 2) if row["revenue"] else 0.0,
        )
        for _, row in grouped.rename(columns={"Category": "category"}).iterrows()
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

    Never materialises the whole dataset into a JSON response at once —
    files with tens of thousands of rows (verified with 50k-row test
    files) would otherwise produce a multi-megabyte payload on every
    request.
    """
    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 1
    page = max(1, min(page, total_pages))

    if total_rows == 0:
        return LedgerPage(entries=[], page=page, page_size=page_size, total_rows=0, total_pages=1)

    ordered = df.sort_values("Date", kind="stable").reset_index(drop=False)
    start = (page - 1) * page_size
    chunk = ordered.iloc[start : start + page_size]

    entries = [
        LedgerEntry(
            row=int(r["index"]),
            date=str(r["Date"].date()),
            category=str(r["Category"]),
            item=str(r["Item"]),
            quantity=int(r["Quantity"]),
            selling_price=round(float(r["Selling Price"]), 2),
            cost_price=round(float(r["Cost Price"]), 2),
            revenue=round(float(r["Quantity"]) * float(r["Selling Price"]), 2),
            profit=round(
                float(r["Quantity"]) * float(r["Selling Price"])
                - float(r["Quantity"]) * float(r["Cost Price"]),
                2,
            ),
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


# ── Orchestrator called by the route handler ───────────────────────────────
def apply_time_filter(df: pd.DataFrame, time_filter: str) -> pd.DataFrame:
    """
    Slice the DataFrame to the selected time window.
    Reference point = max date in the data (NOT system clock),
    so older CSV uploads still give correct 'Last 7 Days' / 'This Month' slices.
    """
    if time_filter == "all" or df.empty:
        return df

    dates = pd.to_datetime(df["Date"], errors="coerce")
    max_date = dates.max()
    if pd.isna(max_date):
        return df.iloc[0:0]

    if time_filter == "today":
        day_start = max_date.normalize()
        day_end = day_start + timedelta(days=1)
        return df[(dates >= day_start) & (dates < day_end)].copy()
    elif time_filter == "week":
        cutoff = max_date - timedelta(days=7)
    elif time_filter == "month":
        cutoff = max_date.replace(day=1).normalize()
    elif time_filter == "30days":
        cutoff = max_date - timedelta(days=30)
    else:
        return df

    return df[dates >= cutoff].copy()


def run_full_analysis(
    df: pd.DataFrame,
    time_filter: str = "all",
    column_mapping: dict[str, str] | None = None,
) -> AnalyticsResponse:
    """
    1. Normalise & validate raw DataFrame (using the user-confirmed column
       mapping when available — see the /upload/{file_id}/confirm-mapping
       flow — so we never silently re-guess a different mapping here).
    2. Apply time filter AFTER validation (so date column is clean).
    3. Run analytics on filtered rows only.
    """
    df, error_dicts = normalize_dataframe(df, column_mapping=column_mapping)
    errors = [RowError(**e) for e in error_dicts]

    df = apply_time_filter(df, time_filter)

    if df.empty:
        return AnalyticsResponse(
            summary=SalesSummary(
                revenue=MetricValue(value=0.0),
                profit=MetricValue(value=0.0),
                cost=MetricValue(value=0.0),
                units_sold=MetricValue(value=0),
                unique_items_sold=MetricValue(value=0),
            ),
            top_items=[],
            daily_trend=[],
            dead_stock=[],
            categories=[],
            errors=errors,
        )

    return AnalyticsResponse(
        summary=compute_summary(df),
        top_items=compute_top_items(df),
        daily_trend=compute_daily_trend(df),
        dead_stock=compute_dead_stock(df),
        categories=compute_revenue_by_category(df),
        errors=errors,
    )


