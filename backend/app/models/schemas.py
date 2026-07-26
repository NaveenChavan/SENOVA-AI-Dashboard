"""
Pydantic response models for the SENOVA AI Dashboard.
Each model maps directly to a Recharts-compatible shape so the frontend
can pass them straight into <BarChart>, <LineChart>, etc. without
any post-processing.
"""

from datetime import date
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RowError(BaseModel):
    """Single row-level validation failure."""
    row: int = Field(..., description="0-based row index from the uploaded file")
    column: str = Field(..., description="Canonical column name that failed validation")
    error: str = Field(..., description="Human-readable description of the type mismatch")


class ColumnGuess(BaseModel):
    """
    Best-guess mapping for a single raw column from the uploaded file.
    Shown to the user on the column-mapping confirmation screen so they can
    fix any wrong guesses before we run analysis — every shop's export
    format is different, so we never assume our guess is correct.
    """
    raw_column: str = Field(..., description="The exact column header as it appears in the uploaded file")
    suggested_field: str | None = Field(
        None,
        description=(
            "Our best guess at which canonical field this maps to "
            "(Date, Category, Item, Quantity, Selling Price, Cost Price), "
            "or null if we have no guess (e.g. an unrelated 'Notes' column)."
        ),
    )
    confidence: str = Field(
        ...,
        description="'exact' (known alias), 'fuzzy' (keyword match, needs confirmation), or 'none' (no match).",
    )


class ColumnMappingPreview(BaseModel):
    """
    Returned immediately after upload, BEFORE any analysis runs. The
    frontend renders this as an editable mapping screen; the user
    confirms or corrects it, then calls POST /upload/{file_id}/confirm-mapping.
    """
    file_id: str
    filename: str
    detected_columns: List[ColumnGuess]
    required_fields: List[str] = Field(
        default_factory=lambda: ["Date", "Category", "Item", "Quantity", "Selling Price", "Cost Price"],
        description="The 6 canonical fields every uploaded file must map to.",
    )
    optional_fields: List[str] = Field(
        default_factory=list,
        description=(
            "Extra fields the user may map if their export has them. Measures "
            "(Line Total, Discount, Tax, Stock On Hand) refine the money maths; "
            "dimensions (Branch, Payment Mode, Customer, Salesperson, Brand, Size, "
            "Colour, Invoice No) become extra chart/filter axes."
        ),
    )
    field_help: dict[str, str] = Field(
        default_factory=dict,
        description="Short explanation per mappable field, shown as helper text on the mapping screen.",
    )
    row_count: int = Field(..., description="Total rows in the raw file (before validation)")
    sample_rows: List[dict] = Field(
        default_factory=list,
        description="First few raw rows (original column names) so the UI can show a live preview.",
    )


class TopItem(BaseModel):
    """Single row for the 'Top 5 Fast-Moving Items' bar chart."""
    name: str = Field(..., description="Item name")
    quantity: int = Field(..., description="Total units sold")
    revenue: float = Field(..., description="Gross revenue generated")


class DailyTrend(BaseModel):
    """Single data-point for the daily sales trend line chart."""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    revenue: float = Field(..., description="Gross revenue on that day")
    profit: float = Field(..., description="Net profit on that day")


class DeadStockItem(BaseModel):
    """Item that has sold zero or very few units over the analysed period."""
    name: str = Field(..., description="Item name")
    total_quantity: int = Field(0, description="Total units sold (usually 0 or very low)")
    days_since_last_sale: int = Field(..., description="Days since the last recorded sale")


class MetricValue(BaseModel):
    """Single KPI metric with total, trend, and sparkline data."""
    value: float = Field(..., description="Total for the selected period")
    trend_percentage: float = Field(0, description="Percentage change vs previous period")
    sparkline_data: list[float] = Field(
        default_factory=list,
        description="Daily totals for the trailing days (sparkline source)",
    )


class SalesSummary(BaseModel):
    """High-level KPIs with trend and sparkline data."""
    revenue: MetricValue
    profit: MetricValue
    cost: MetricValue
    units_sold: MetricValue
    unique_items_sold: MetricValue


class CategoryBreakdown(BaseModel):
    """Revenue and quantity grouped by product category."""
    category: str = Field(..., description="Product category name")
    revenue: float = Field(..., description="Gross revenue for this category")
    quantity: int = Field(..., description="Total units sold in this category")

    # Allows construction straight from an object with matching attributes
    # (Pydantic v2 style; the old class-based Config is deprecated).
    model_config = ConfigDict(from_attributes=True)


class AnalyticsResponse(BaseModel):
    """
    The full payload returned by GET /process/{file_id}.
    Every field is a pre-formatted structure Recharts can consume directly.
    Partial success: valid rows are analysed, invalid rows are reported in ``errors``.
    """
    summary: SalesSummary
    top_items: List[TopItem]                    # Top 5 fast-moving items (bar chart data)
    daily_trend: List[DailyTrend]               # Daily revenue & profit trend (line chart data)
    dead_stock: List[DeadStockItem]             # Slow-moving / dead stock items
    categories: List[CategoryBreakdown] = Field(  # Revenue by category (pie chart data)
        default_factory=list,
        description="Revenue grouped by product category for the donut chart.",
    )
    errors: List[RowError] = Field(             # Row-level validation failures
        default_factory=list,
        description="Per-row validation errors. Empty when all rows are clean.",
    )


# ── CA-style (Chartered Accountant) reporting structures ────────────────────
#
# The charts above are great for a quick glance, but a shop owner's
# accountant expects numbers presented the way a Profit & Loss statement
# and a sales ledger look on paper: labelled line items, running totals,
# and a full row-by-row register — not just bars on a graph.


class PnLLineItem(BaseModel):
    """
    Single line in the Profit & Loss statement, e.g. "Gross Revenue",
    "Cost of Goods Sold", "Gross Profit". ``is_subtotal`` lets the frontend
    render subtotal/total rows with a heavier font weight and a top border,
    matching standard accounting statement formatting.
    """
    label: str = Field(..., description="Line item name, e.g. 'Gross Revenue', 'Gross Profit'")
    amount: float = Field(..., description="Amount in INR for this line item")
    percentage_of_revenue: float | None = Field(
        None, description="This line as a % of gross revenue, where meaningful (null for revenue itself)."
    )
    is_subtotal: bool = Field(False, description="True for subtotal/total rows (bold, ruled off in the UI/PDF)")


class CategoryLedgerRow(BaseModel):
    """One row of the category-wise breakdown table in the CA-style report."""
    category: str
    units_sold: int
    revenue: float
    cost: float
    profit: float
    margin_percentage: float = Field(..., description="profit / revenue * 100, rounded to 2dp")


class CAReportSummary(BaseModel):
    """
    The full CA-style summary report: a Profit & Loss statement plus a
    category-wise ledger, for the selected reporting period. This is what
    the "Financial Report" tab and the PDF export render as proper tables
    (rows and columns), not charts.
    """
    period_label: str = Field(..., description="Human-readable period, e.g. 'Last 30 Days', 'This Month'")
    period_start: str = Field(..., description="ISO date (YYYY-MM-DD) of the period start")
    period_end: str = Field(..., description="ISO date (YYYY-MM-DD) of the period end")
    pnl: List[PnLLineItem] = Field(..., description="Profit & Loss statement line items, in display order")
    category_ledger: List[CategoryLedgerRow] = Field(..., description="Category-wise revenue/cost/profit breakdown")
    total_transactions: int = Field(..., description="Number of valid transaction rows in this period")


class LedgerEntry(BaseModel):
    """
    Single row of the detailed transaction ledger — one line per sales
    transaction, exactly how an accountant's day-book / sales register
    looks: date, item, quantity, rate, and computed revenue/profit.
    """
    row: int = Field(..., description="0-based row index from the original uploaded file")
    date: str = Field(..., description="Transaction date, YYYY-MM-DD")
    category: str
    item: str
    quantity: int
    selling_price: float
    cost_price: float
    discount: float = Field(0.0, description="Discount on this line (0 when the file has no discount column)")
    revenue: float = Field(..., description="quantity * selling_price - discount (net, matches the P&L)")
    profit: float = Field(..., description="revenue - (quantity * cost_price)")


class LedgerPage(BaseModel):
    """
    One page of the paginated transaction ledger. Large files (tens of
    thousands of rows) are never sent to the frontend in one response —
    the UI requests pages on demand (see GET /analytics/{file_id}/ledger).
    """
    entries: List[LedgerEntry]
    page: int = Field(..., description="1-based page number")
    page_size: int
    total_rows: int = Field(..., description="Total transaction count across all pages")
    total_pages: int


class DataDateRange(BaseModel):
    """
    The actual date span of the valid rows in an uploaded file. The
    frontend uses this to disable date-filter buttons that can't possibly
    show a different result than a wider filter — e.g. if every row falls
    within a single 4-day window, "Last 7 Days", "This Month", and
    "Last 30 Days" would all return identical totals, which looks like a
    bug to the user if left unexplained.
    """
    min_date: str | None = Field(None, description="Earliest transaction date, YYYY-MM-DD (null if no valid rows)")
    max_date: str | None = Field(None, description="Latest transaction date, YYYY-MM-DD (null if no valid rows)")
    span_days: int = Field(0, description="Whole days between min_date and max_date, inclusive (0 if no valid rows)")


class UploadResponse(BaseModel):
    """Returned immediately after a file upload."""
    file_id: str
    filename: str
    message: str = "File uploaded successfully."
    valid_count: int = Field(0, description="Number of valid rows inserted into the database")
    error_count: int = Field(0, description="Number of invalid rows found during validation")
    errors: List[RowError] = Field(
        default_factory=list,
        description="Row-level schema / business-rule validation errors.",
    )
    date_range: DataDateRange = Field(
        default_factory=DataDateRange,
        description="Actual date span of the valid data — drives which date filters make sense to show as active.",
    )
    optional_fields: List[str] = Field(
        default_factory=list,
        description=(
            "Optional canonical fields this file actually provided (e.g. Branch, "
            "Payment Mode, Discount, Stock On Hand). Each one unlocks extra "
            "dimensions/measures in the dashboard, so the UI can advertise them."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  PRO layer — shared query model, chart engine, insights, inventory, forecast
# ═══════════════════════════════════════════════════════════════════════════
#
# Every Pro endpoint takes the same ``AnalysisQuery`` body so the numbers on
# the KPI cards, the charts, the insight cards, the inventory table, the P&L
# and the PDF are always computed from an identical slice of data. One filter
# model = no chance of two widgets disagreeing.


TimeFilter = Literal["all", "today", "week", "30days", "month", "custom"]

#: Dimensions the client may group or filter by. Requests naming anything
#: outside this list are rejected (422) — the value is never used to build a
#: query string or touch ``DataFrame.query``/``eval``.
DimensionKey = Literal[
    "category",
    "item",
    "day",
    "weekday",
    "month",
    "branch",
    "payment_mode",
    "customer",
    "salesperson",
    "brand",
    "size",
    "colour",
    "invoice_no",
]

#: Measures the client may plot. Same closed-set rule as dimensions.
MeasureKey = Literal[
    "revenue",
    "profit",
    "cost",
    "units",
    "margin_pct",
    "transactions",
    "discount",
    "avg_price",
]

#: Hard caps that keep one request from turning into a server-wide slowdown.
MAX_FILTER_KEYS = 8
MAX_FILTER_VALUES = 50
MAX_FILTER_VALUE_LENGTH = 200


class AnalysisQuery(BaseModel):
    """
    The slice of data every Pro endpoint operates on.

    ``time_filter`` uses the same presets as the classic GET endpoints, all
    anchored to the newest date **in the file** (not the server clock), so a
    CSV uploaded months later still gives a sensible "Last 7 Days".
    ``time_filter="custom"`` switches to the explicit ``start_date`` /
    ``end_date`` pair.

    ``filters`` is ``{dimension_key: [allowed values]}`` and is applied with
    ``Series.isin`` after the key has been checked against the dimensions the
    uploaded file actually has. Sizes are capped so a hostile client can't
    send a million filter values.
    """

    time_filter: TimeFilter = Field("all", description="Preset date window, or 'custom' to use start/end dates.")
    start_date: date | None = Field(None, description="Inclusive start date, only used when time_filter='custom'.")
    end_date: date | None = Field(None, description="Inclusive end date, only used when time_filter='custom'.")
    filters: dict[str, List[str]] = Field(
        default_factory=dict,
        description="Dimension filters, e.g. {'category': ['Kurta'], 'branch': ['MG Road']}.",
    )

    @field_validator("filters")
    @classmethod
    def _bound_filters(cls, value: dict[str, List[str]]) -> dict[str, List[str]]:
        """Reject oversized filter payloads instead of letting them reach Pandas."""
        if len(value) > MAX_FILTER_KEYS:
            raise ValueError(f"Too many filter keys (max {MAX_FILTER_KEYS}).")
        cleaned: dict[str, List[str]] = {}
        for key, values in value.items():
            if len(values) > MAX_FILTER_VALUES:
                raise ValueError(f"Too many values for filter '{key}' (max {MAX_FILTER_VALUES}).")
            cleaned[str(key)[:64]] = [str(v)[:MAX_FILTER_VALUE_LENGTH] for v in values]
        return cleaned

    @model_validator(mode="after")
    def _check_custom_range(self) -> "AnalysisQuery":
        """A custom window needs both ends, in the right order."""
        if self.time_filter == "custom":
            if not self.start_date or not self.end_date:
                raise ValueError("time_filter='custom' requires both start_date and end_date.")
            if self.start_date > self.end_date:
                raise ValueError("start_date must be on or before end_date.")
        return self


class ChartQuery(AnalysisQuery):
    """An ``AnalysisQuery`` plus what to group by, what to plot, and how many bars."""

    dimension: DimensionKey = Field("category", description="What to group rows by.")
    measure: MeasureKey = Field("revenue", description="Which number to plot per group.")
    top_n: int = Field(10, ge=1, le=50, description="Keep only the N biggest groups (rest folded into 'Other').")


class LedgerQuery(AnalysisQuery):
    """An ``AnalysisQuery`` plus pagination for the transaction register."""

    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=1000)


class ForecastQuery(AnalysisQuery):
    """An ``AnalysisQuery`` plus how far ahead to project."""

    horizon: int = Field(14, ge=1, le=90, description="Days to forecast ahead (max 90).")


class ChartPoint(BaseModel):
    """
    One group (bar / slice / bubble / treemap tile) with **every** measure
    pre-computed, so switching chart type or measure in the UI never needs a
    new request — and combo/Pareto/scatter charts get all their axes at once.
    """

    label: str = Field(..., description="Group name, e.g. 'Kurta', 'Mon', '2026-07-14'")
    value: float = Field(..., description="The requested measure — what the chart plots")
    revenue: float
    cost: float
    profit: float
    units: int
    transactions: int
    discount: float = 0.0
    margin_pct: float | None = Field(None, description="profit / revenue * 100 (null when revenue is 0)")
    avg_price: float | None = Field(None, description="Average realised unit price for this group")
    share_pct: float | None = Field(None, description="This group's share of the total of the requested measure")
    cumulative_pct: float | None = Field(
        None, description="Running share when sorted descending — the Pareto (80/20) curve"
    )
    is_other: bool = Field(False, description="True for the folded 'Other' bucket beyond top_n")


class ChartDataResponse(BaseModel):
    """Everything the chart studio needs to draw any of its chart types."""

    dimension: str
    dimension_label: str = Field(..., description="Human-readable dimension name for the axis title")
    measure: str
    measure_label: str = Field(..., description="Human-readable measure name for the axis/legend")
    measure_format: Literal["currency", "number", "percent"] = "currency"
    points: List[ChartPoint]
    total: float = Field(0.0, description="Total of the requested measure across all groups (before top_n folding)")
    group_count: int = Field(0, description="Number of distinct groups before top_n folding")
    pareto_group_count: int | None = Field(
        None, description="How many groups make up the first 80% of the measure (concentration)"
    )


class HeatmapCell(BaseModel):
    """One cell of the weekday × week intensity grid."""

    row: str = Field(..., description="Weekday label, Mon–Sun")
    column: str = Field(..., description="Week label, e.g. 'W28' with its start date")
    value: float
    transactions: int


class HeatmapResponse(BaseModel):
    """
    Weekday × calendar-week intensity grid — shows *when* the shop actually
    sells. Ships a numeric legend range because colour alone must never be
    the only carrier of meaning (accessibility).
    """

    rows: List[str]
    columns: List[str]
    column_dates: List[str] = Field(default_factory=list, description="ISO start date of each week column")
    cells: List[HeatmapCell]
    measure: str
    measure_label: str
    min_value: float = 0.0
    max_value: float = 0.0


class DimensionOption(BaseModel):
    """One filterable dimension and its distinct values, for the filter panel."""

    key: str
    label: str
    values: List[str]
    truncated: bool = Field(
        False, description="True when the file has more distinct values than were returned"
    )


class DimensionsResponse(BaseModel):
    """
    Which dimensions this particular file supports, plus their values.
    The filter panel and the chart studio's dimension dropdown are built
    from this — an unmapped column can never become a filter.
    """

    dimensions: List[DimensionOption]
    optional_measures: List[str] = Field(
        default_factory=list,
        description="Optional numeric fields present in this file (Discount, Tax, Stock On Hand, Line Total).",
    )
    date_range: DataDateRange = Field(default_factory=DataDateRange)


# ── Feature 1: AI insight cards ─────────────────────────────────────────────


class Insight(BaseModel):
    """
    One automatically-detected finding, written as plain text from a template
    filled with computed numbers (no language model involved, so a figure can
    never be invented).
    """

    id: str = Field(..., description="Stable id, e.g. 'anomaly-drop', 'margin-leak'")
    kind: str = Field(..., description="Family: anomaly | mover | margin | concentration | timing | deadstock | forecast")
    severity: Literal["critical", "warning", "positive", "neutral"] = "neutral"
    title: str = Field(..., description="Short headline, e.g. 'Revenue dropped sharply on 14 Jul'")
    message: str = Field(..., description="One or two sentences of plain-language explanation with numbers")
    action: str | None = Field(None, description="Suggested next step for the shop owner")
    metrics: dict[str, float | None] = Field(
        default_factory=dict,
        description="Machine-readable figures behind the text, so the UI can format them itself",
    )
    evidence: List[str] = Field(
        default_factory=list, description="Dates / item names the finding is based on"
    )


class InsightsResponse(BaseModel):
    """All insights for the selected slice, most severe first."""

    insights: List[Insight]
    anomaly_dates: List[str] = Field(
        default_factory=list,
        description="Dates flagged as statistical outliers — the trend chart marks these in red.",
    )
    analysed_days: int = Field(0, description="Number of calendar days examined")
    note: str | None = Field(
        None, description="Set when the data was too small/sparse for some checks to run"
    )


# ── Feature 3: inventory & reorder intelligence ─────────────────────────────


class InventoryItem(BaseModel):
    """Per-item demand and (when stock is known) cover/reorder figures."""

    item: str
    category: str
    units_sold: int
    revenue: float
    profit: float
    margin_pct: float | None = None
    velocity_per_day: float = Field(..., description="Units sold ÷ days in the window")
    velocity_active: float = Field(..., description="Units sold ÷ days on which it actually sold")
    active_days: int = Field(..., description="Distinct days with at least one sale")
    days_since_last_sale: int
    trend_factor: float = Field(
        1.0, description=">1 accelerating, <1 slowing (late-window velocity ÷ early-window velocity)"
    )
    abc_class: Literal["A", "B", "C"] = Field(..., description="A = first 80% of revenue, B = next 15%, C = rest")
    ageing_bucket: Literal["Fresh", "Slow", "Stale", "Dead"]
    reorder_priority: float = Field(..., description="0–100 composite demand-priority score")
    stock_on_hand: float | None = Field(None, description="Only when the file maps a stock column")
    days_of_cover: float | None = Field(None, description="stock ÷ velocity — only when stock is known")
    reorder_flag: bool = Field(False, description="True when days of cover is below the alert threshold")
    capital_locked: float | None = Field(
        None, description="stock × cost price — only when stock is known"
    )


class InventoryBucket(BaseModel):
    """A named group of items with its size and revenue/value contribution."""

    label: str
    item_count: int
    units: int = 0
    revenue: float = 0.0
    revenue_share_pct: float | None = None
    capital_locked: float | None = None


class InventoryResponse(BaseModel):
    """
    Demand-side inventory intelligence.

    ``stock_aware`` is false for the common case where the uploaded file is a
    pure sales register: days-of-cover and capital-locked are then reported as
    ``null`` rather than guessed, and the UI explains that mapping a stock
    column unlocks them.
    """

    stock_aware: bool = False
    window_days: int = 0
    items: List[InventoryItem]
    abc_buckets: List[InventoryBucket] = Field(default_factory=list)
    ageing_buckets: List[InventoryBucket] = Field(default_factory=list)
    reorder_count: int = 0
    total_capital_locked: float | None = None
    note: str | None = None


# ── Feature 2: forecasting ──────────────────────────────────────────────────


class ForecastPoint(BaseModel):
    """
    One day on the forecast chart. Historical days carry ``actual``; future
    days carry ``forecast`` plus an 80% confidence band.
    """

    date: str
    actual: float | None = None
    forecast: float | None = None
    lower: float | None = None
    upper: float | None = None
    is_future: bool = False


class ItemForecast(BaseModel):
    """Expected demand for one item over the requested horizon."""

    item: str
    expected_units: float
    velocity_per_day: float
    trend_factor: float


class ForecastResponse(BaseModel):
    """
    Revenue projection for the next ``horizon`` days.

    ``available`` is false — with a plain-language ``reason`` — when the file
    simply doesn't hold enough history to project honestly (under two weeks).
    A confident-looking forecast drawn from four days of data would be worse
    than no forecast at all.
    """

    available: bool = False
    reason: str | None = None
    horizon_days: int = 0
    points: List[ForecastPoint] = Field(default_factory=list)
    expected_revenue: float = 0.0
    expected_revenue_lower: float = 0.0
    expected_revenue_upper: float = 0.0
    daily_average: float = 0.0
    trend_per_day: float = Field(0.0, description="Slope of the fitted trend, ₹ per day")
    trend_direction: Literal["rising", "flat", "falling"] = "flat"
    accuracy_pct: float | None = Field(
        None, description="100 − MAPE from a 7-day holdout backtest (null when history is too short)"
    )
    accuracy_basis: Literal["daily", "total"] | None = Field(
        None,
        description=(
            "What the accuracy figure scores: 'daily' = average per-day error, "
            "'total' = error on the held-out 7-day total (used when the shop only "
            "trades some days, where per-day error is dominated by which days were open)."
        ),
    )
    trading_days: int = Field(0, description="Days in the history that actually recorded a sale")
    history_days: int = Field(0, description="Calendar days of history the model was fitted on")
    seasonality_applied: bool = False
    weekday_indices: dict[str, float] = Field(
        default_factory=dict, description="Weekday multipliers, 1.0 = an average day"
    )
    item_forecasts: List[ItemForecast] = Field(default_factory=list)

