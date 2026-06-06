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


class SalesSummary(BaseModel):
    """High-level KPIs displayed at the top of the dashboard."""
    total_revenue: float = Field(..., ge=0)
    total_profit: float = Field(...)
    total_cost: float = Field(..., ge=0)
    total_units_sold: int = Field(..., ge=0)
    unique_items_sold: int = Field(..., ge=0)


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
