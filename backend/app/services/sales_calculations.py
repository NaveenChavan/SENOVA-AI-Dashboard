"""
Core analytics engine — pure Pandas transformations.

Every public function receives a DataFrame that has already passed through
``normalize_dataframe()``, so columns are guaranteed to exist and have the
correct types.  No re-coercion needed.
"""

import pandas as pd

from app.models.schemas import (
    AnalyticsResponse,
    CategoryBreakdown,
    DailyTrend,
    DeadStockItem,
    RowError,
    SalesSummary,
    TopItem,
)
from app.utils.data_validator import normalize_dataframe

# ── Public helpers called by the route handler ─────────────────────────────


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add pre-computed per-row derived columns so every groupby below can use
    plain ``.agg()`` instead of the fragile ``groupby().apply(pd.Series({…}))``
    pattern (which silently produced empty result frames on Pandas ≥ 2.x when
    the lambda's Series index names collided with the group key).
    """
    out = df.copy()
    out["_row_revenue"] = out["Quantity"] * out["Selling Price"]
    out["_row_profit"] = (out["Selling Price"] - out["Cost Price"]) * out["Quantity"]
    return out


def compute_summary(df: pd.DataFrame) -> SalesSummary:
    """Aggregate top-level KPIs from the raw data."""
    revenue = float((df["Quantity"] * df["Selling Price"]).sum())
    cost = float((df["Quantity"] * df["Cost Price"]).sum())
    profit = revenue - cost

    return SalesSummary(
        total_revenue=round(revenue, 2),
        total_profit=round(profit, 2),
        total_cost=round(cost, 2),
        total_units_sold=int(df["Quantity"].sum()),
        unique_items_sold=int(df["Item"].nunique()),
    )


def compute_top_items(df: pd.DataFrame, top_n: int = 5) -> list[TopItem]:
    """
    Rank items by total quantity sold descending.
    Returns the top N items pre-formatted for a Recharts <BarChart>.
    """
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


def compute_daily_trend(df: pd.DataFrame) -> list[DailyTrend]:
    """
    Aggregate revenue & profit by date for the line chart.
    ``Date`` is already normalised to datetime by the data validator.
    """
    prepped = _prepare(df)
    daily = (
        prepped.assign(_day=prepped["Date"].dt.date)
        .groupby("_day", as_index=False)
        .agg(revenue=("_row_revenue", "sum"), profit=("_row_profit", "sum"))
        .sort_values("_day")
        .rename(columns={"_day": "Date"})
    )

    return [
        DailyTrend(
            date=str(row["Date"]),
            revenue=round(float(row["revenue"]), 2),
            profit=round(float(row["profit"]), 2),
        )
        for _, row in daily.iterrows()
    ]


def compute_dead_stock(df: pd.DataFrame, threshold_qty: int = 5) -> list[DeadStockItem]:
    """
    Identify items that sold very few units (or zero) over the analysed period.
    Also reports how many days have passed since the last recorded sale.
    """
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


# ── Orchestrator called by the route handler ───────────────────────────────


def run_full_analysis(df: pd.DataFrame) -> AnalyticsResponse:
    """
    1. Normalise & validate the raw DataFrame (row-level isolation).
    2. Run every calculation on valid rows only.
    3. Return the full AnalyticsResponse with per-row errors attached.

    Partial success: rows that fail schema validation are collected into
    ``errors`` while the rest proceed to the analytics engine.
    """
    df, error_dicts = normalize_dataframe(df)
    errors = [RowError(**e) for e in error_dicts]

    if df.empty:
        return AnalyticsResponse(
            summary=SalesSummary(
                total_revenue=0.0,
                total_profit=0.0,
                total_cost=0.0,
                total_units_sold=0,
                unique_items_sold=0,
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


def run_analysis_on_clean_df(df: pd.DataFrame) -> AnalyticsResponse:
    """
    Skip ``normalize_dataframe()`` and run calculations directly on a DataFrame
    that is already known to be clean (canonical column names + correct dtypes).

    Use this when the data source is trusted — e.g. a DataFrame that has
    already passed through ``normalize_dataframe()`` once and only needs its
    dtypes re-asserted. Re-running ``normalize_dataframe()`` on already-clean
    data can corrupt ISO-formatted dates (day-first ambiguity) and add
    unnecessary overhead.
    """
    if df.empty:
        return AnalyticsResponse(
            summary=SalesSummary(
                total_revenue=0.0,
                total_profit=0.0,
                total_cost=0.0,
                total_units_sold=0,
                unique_items_sold=0,
            ),
            top_items=[],
            daily_trend=[],
            dead_stock=[],
            categories=[],
            errors=[],
        )

    return AnalyticsResponse(
        summary=compute_summary(df),
        top_items=compute_top_items(df),
        daily_trend=compute_daily_trend(df),
        dead_stock=compute_dead_stock(df),
        categories=compute_revenue_by_category(df),
        errors=[],
    )
