"""
Pydantic response models for the SENOVA AI Dashboard.
Each model maps directly to a Recharts-compatible shape so the frontend
can pass them straight into <BarChart>, <LineChart>, etc. without
any post-processing.
"""

from pydantic import BaseModel, Field
from typing import List


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

    class Config:
        from_attributes = True


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
    revenue: float = Field(..., description="quantity * selling_price")
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
