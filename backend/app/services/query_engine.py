"""
Shared query + aggregation layer for every Pro endpoint.

Responsibilities
----------------
1. **Resolve the window** — turn an ``AnalysisQuery`` (preset or custom date
   range) into a concrete current period *and* the equal-length previous
   period used for trend arrows. All presets are anchored to the newest date
   in the file, never the server clock, so a CSV uploaded weeks later still
   produces a sensible "Last 7 Days".
2. **Apply filters safely** — dimension keys are looked up in a fixed
   registry and matched against the columns the file actually has; values are
   applied with ``Series.isin``. Nothing user-supplied is ever interpolated
   into a query string, ``DataFrame.query`` or ``eval``.
3. **Aggregate generically** — one function turns (dimension, measure) into
   chart-ready points with *every* measure pre-computed, which is what lets a
   single request feed bar, line, donut, combo, scatter, Pareto and treemap
   views without a round trip per chart type.
4. **Build the weekday × week heatmap** and the filter panel's dimension
   options.

Keeping all of this in one module is what makes the KPI cards, charts,
insights, inventory table, P&L and PDF agree with each other: they all read
the same slice through the same code path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.models.schemas import (
    ChartDataResponse,
    ChartPoint,
    DataDateRange,
    DimensionOption,
    DimensionsResponse,
    HeatmapCell,
    HeatmapResponse,
)
from app.services.sales_calculations import _prepare, compute_data_date_range
from app.utils.data_validator import available_dimensions, available_measures
from app.utils.safe_json import safe_float, safe_int, safe_percentage

# ── Registries: the only dimensions/measures the API will ever accept ───────
#
# ``column`` is the canonical DataFrame column, or one of the special time
# keys handled in ``_dimension_series``. Anything not in this dict is rejected
# before it can reach Pandas.
DIMENSIONS: dict[str, dict[str, str]] = {
    "category": {"column": "Category", "label": "Category"},
    "item": {"column": "Item", "label": "Item"},
    "day": {"column": "_time_day", "label": "Day"},
    "weekday": {"column": "_time_weekday", "label": "Weekday"},
    "month": {"column": "_time_month", "label": "Month"},
    "branch": {"column": "Branch", "label": "Branch / Store"},
    "payment_mode": {"column": "Payment Mode", "label": "Payment Mode"},
    "customer": {"column": "Customer", "label": "Customer"},
    "salesperson": {"column": "Salesperson", "label": "Salesperson"},
    "brand": {"column": "Brand", "label": "Brand"},
    "size": {"column": "Size", "label": "Size"},
    "colour": {"column": "Colour", "label": "Colour"},
    "invoice_no": {"column": "Invoice No", "label": "Invoice No"},
}

#: Dimensions that are derived from the Date column rather than a real column.
TIME_DIMENSIONS = {"day", "weekday", "month"}

#: ``additive`` measures can be summed and therefore have a meaningful share
#: of total and Pareto curve; ratios (margin %, average price) cannot.
MEASURES: dict[str, dict] = {
    "revenue": {"label": "Revenue", "format": "currency", "additive": True},
    "profit": {"label": "Profit", "format": "currency", "additive": True},
    "cost": {"label": "Cost", "format": "currency", "additive": True},
    "units": {"label": "Units Sold", "format": "number", "additive": True},
    "transactions": {"label": "Transactions", "format": "number", "additive": True},
    "discount": {"label": "Discount Given", "format": "currency", "additive": True},
    "margin_pct": {"label": "Margin %", "format": "percent", "additive": False},
    "avg_price": {"label": "Avg Selling Price", "format": "currency", "additive": False},
}


MEASURE_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "revenue": set(),
    "profit": {"Quantity", "Cost Price"},
    "cost": {"Quantity", "Cost Price"},
    "units": {"Quantity"},
    "transactions": set(),
    "discount": {"Discount"},
    "margin_pct": {"Quantity", "Cost Price"},
    "avg_price": {"Quantity"},
}


def measure_unavailable_reason(df: pd.DataFrame, measure: str) -> str | None:
    """Return a user-facing reason when a built-in chart measure is unsupported.

    Column presence alone is not enough for optional fields: a partly blank
    quantity column must not turn unknown units/cost into a zero-valued chart.
    Extra measures are authorized by the file-specific registry and are handled
    by the route layer before reaching this helper.
    """
    if measure not in MEASURES:
        if measure.startswith("x_meas:") and measure in df.columns:
            return None
        return f"Measure '{measure}' is not available for this file."

    required = MEASURE_REQUIRED_COLUMNS[measure]
    # Discount can be supplied directly, or derived from MRP - Selling Price
    # multiplied by Quantity. An MRP column by itself is not enough to calculate it.
    if measure == "discount" and "Discount" not in df.columns:
        alternative = {"MRP", "Selling Price", "Quantity"}
        missing_alternative = sorted(alternative - set(df.columns))
        if missing_alternative:
            return "Measure 'Discount Given' needs Discount, or MRP + Selling Price + Quantity."
        if not df.empty:
            incomplete = [column for column in sorted(alternative) if df[column].isna().any()]
            if incomplete:
                return "Measure 'Discount Given' is unavailable because some rows have blank " + ", ".join(incomplete) + "."
        return None

    for column in sorted(required):
        if column not in df.columns:
            return f"Measure '{MEASURES[measure]['label']}' needs {column}."
        if not df.empty and df[column].isna().any():
            return f"Measure '{MEASURES[measure]['label']}' is unavailable because some rows have blank {column} values."
    return None

#: Human-readable labels for the preset windows (used in report headers).
PERIOD_LABELS: dict[str, str] = {
    "all": "All Time",
    "today": "Today",
    "week": "Last 7 Days",
    "30days": "Last 30 Days",
    "month": "This Month",
    "custom": "Custom Range",
}

#: Weekday order for the weekday dimension and the heatmap rows.
WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

#: Cap on distinct values returned per dimension for the filter panel. A file
#: can legitimately have thousands of invoice numbers; sending them all would
#: bloat the response and freeze the dropdown.
MAX_DIMENSION_VALUES = 200


@dataclass(frozen=True)
class Window:
    """
    A resolved reporting period plus the comparison period behind it.

    ``end`` is an exclusive upper bound (start of the day after the last
    included day), which keeps timestamp comparisons simple and avoids the
    classic "23:59:59 rows are missing" bug.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    previous_start: pd.Timestamp
    previous_end: pd.Timestamp
    label: str


class QueryError(ValueError):
    """Raised for a query the data can't satisfy (unknown dimension, bad range)."""


# ── 1. Window resolution ────────────────────────────────────────────────────


def resolve_window(df: pd.DataFrame, time_filter: str, start_date: date | None = None, end_date: date | None = None) -> Window:
    """
    Turn a preset name (or an explicit date pair) into a concrete ``Window``.

    The comparison period is always the same length as the selected one and
    sits immediately before it, so "vs previous period" means the same thing
    for a preset and for a hand-picked range. ``all`` has no previous period
    by definition — the whole file *is* the period.
    """
    if df.empty:
        now = pd.Timestamp.now().normalize()
        return Window(now, now, now, now, PERIOD_LABELS.get(time_filter, time_filter))

    max_date = pd.Timestamp(df["Date"].max()).normalize()
    min_date = pd.Timestamp(df["Date"].min()).normalize()
    one_day = timedelta(days=1)

    if time_filter == "custom":
        if not start_date or not end_date:
            raise QueryError("A custom range needs both start_date and end_date.")
        requested_start = pd.Timestamp(start_date).normalize()
        requested_end = pd.Timestamp(end_date).normalize()
        if requested_start > requested_end:
            raise QueryError("From date must be on or before To date.")
        # Custom ranges are always bounded by the actual data span. Keep the
        # behaviour deterministic even when the whole requested range sits
        # outside the file: clamp it to the nearest available day.
        if requested_end < min_date or requested_start > max_date:
            start = requested_start
            end = requested_end + one_day
        else:
            start = max(requested_start, min_date)
            end_day = min(requested_end, max_date)
            end = end_day + one_day
    elif time_filter == "today":
        start, end = max_date, max_date + one_day
    elif time_filter == "week":
        start, end = max_date - timedelta(days=6), max_date + one_day
    elif time_filter == "30days":
        start, end = max_date - timedelta(days=29), max_date + one_day
    elif time_filter == "month":
        start, end = max_date.replace(day=1), max_date + one_day
    else:  # "all"
        start, end = min_date, max_date + one_day
        return Window(start, end, start, start, PERIOD_LABELS["all"])

    span = end - start
    if time_filter == 'today':
        label = f"Latest day ({max_date.day} {max_date.strftime('%b')})"
    else:
        label = PERIOD_LABELS.get(time_filter, time_filter)
    return Window(start, end, start - span, start, label)


def slice_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Rows whose ``Date`` falls in ``[start, end)``."""
    if df.empty:
        return df
    return df[(df["Date"] >= start) & (df["Date"] < end)].copy()


# ── 2. Filtering ────────────────────────────────────────────────────────────


def apply_filters(df: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    """
    Apply ``{dimension_key: [values]}`` using membership tests only.

    A key that isn't a known dimension, or names a column this file doesn't
    have, raises ``QueryError`` (→ HTTP 422) rather than being ignored: a
    silently dropped filter would show the user numbers that don't match the
    filter chips on screen.
    """
    if not filters or df.empty:
        return df

    out = df
    for key, values in filters.items():
        if not values:
            continue  # an empty selection means "no restriction"

        if key.startswith("x_dim:"):
            if key not in out.columns:
                raise QueryError(f"This file has no '{key}' column to filter on.")
            out = out[out[key].astype(str).isin(set(values))]
            continue

        spec = DIMENSIONS.get(key)
        if spec is None:
            raise QueryError(f"Unknown filter dimension '{key}'.")
        column = spec["column"]
        if column.startswith("_time_"):
            raise QueryError(f"Dimension '{key}' cannot be used as a filter.")
        if column not in out.columns:
            raise QueryError(f"This file has no '{spec['label']}' column to filter on.")
        out = out[out[column].astype(str).isin(set(values))]
    return out.copy()


def build_slice(
    df: pd.DataFrame,
    time_filter: str,
    start_date: date | None = None,
    end_date: date | None = None,
    filters: dict[str, list[str]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Window]:
    """
    The one entry point every Pro endpoint uses.

    Returns ``(current_rows, previous_rows, window)`` with dimension filters
    applied to **both** periods, so a trend arrow compares like with like.
    """
    # Resolve the time window against the FULL file before applying dimension
    # filters. This is critical for the "Latest day" rule: a category that had
    # no sale on the file's last day must not silently redefine "latest day".
    window = resolve_window(df, time_filter, start_date, end_date)
    current_window = slice_window(df, window.start, window.end)
    previous_window = (
        slice_window(df, window.previous_start, window.previous_end)
        if window.previous_end > window.previous_start
        else df.iloc[0:0]
    )
    current = apply_filters(current_window, filters or {})
    current.attrs = dict(df.attrs)
    previous = apply_filters(previous_window, filters or {})
    previous.attrs = dict(df.attrs)
    return current, previous, window


# ── 3. Generic aggregation ──────────────────────────────────────────────────


def _dimension_series(prepped: pd.DataFrame, dimension: str) -> pd.Series:
    """
    Build the grouping key for a dimension: a real column, or a label derived
    from ``Date`` for the three time dimensions.
    """
    spec = DIMENSIONS.get(dimension)
    if spec is not None:
        column = spec["column"]
        if column == "_time_day":
            return prepped["Date"].dt.strftime("%Y-%m-%d")
        if column == "_time_weekday":
            return prepped["Date"].dt.strftime("%a")
        if column == "_time_month":
            return prepped["Date"].dt.strftime("%Y-%m")
        if column not in prepped.columns:
            raise QueryError(f"This file has no '{spec['label']}' column.")
        return prepped[column].astype(str)

    if dimension.startswith("x_dim:"):
        if dimension not in prepped.columns:
            raise QueryError(f"This file has no '{dimension}' column.")
        return prepped[dimension].astype(str)

    raise QueryError(f"Unknown dimension '{dimension}'.")


def _measure_value(row: pd.Series, measure: str) -> float:
    """Pick the requested measure out of a fully-aggregated group row."""
    if measure == "revenue":
        return float(row["revenue"])
    if measure == "profit":
        return float(row["profit"])
    if measure == "cost":
        return float(row["cost"])
    if measure == "units":
        return float(row["units"])
    if measure == "transactions":
        return float(row["transactions"])
    if measure == "discount":
        return float(row["discount"])
    if measure == "margin_pct":
        return float(safe_percentage(row["profit"], row["revenue"], default=0.0) or 0.0)
    if measure == "avg_price":
        return float(safe_float(row["revenue"] / row["units"], default=0.0) if row["units"] else 0.0)
    raise QueryError(f"Unknown measure '{measure}'.")


def aggregate(
    df: pd.DataFrame,
    dimension: str = "category",
    measure: str = "revenue",
    top_n: int = 10,
) -> ChartDataResponse:
    """
    Group ``df`` by ``dimension`` and return chart-ready points.

    Supports built-in dimensions/measures and deterministic extra dimensions/measures.
    """
    extra_reg = getattr(df, "attrs", {}).get("extra_registry", {})

    # Resolve dimension metadata
    if dimension in DIMENSIONS:
        dim_label = DIMENSIONS[dimension]["label"]
    elif dimension.startswith("x_dim:") and dimension in df.columns:
        dim_label = extra_reg.get(dimension, {}).get("display_label", dimension)
    else:
        raise QueryError(f"Unknown dimension '{dimension}'.")

    # Resolve measure metadata
    if measure in MEASURES:
        meta = MEASURES[measure]
        meas_label = meta["label"]
        meas_format = meta["format"]
        additive = bool(meta["additive"])
        is_extra_meas = False
        extra_agg = None
    elif measure.startswith("x_meas:") and measure in df.columns:
        meas_info = extra_reg.get(measure, {})
        meas_label = meas_info.get("display_label", measure)
        meas_format = "number"
        extra_agg = meas_info.get("aggregation", "sum")
        additive = (extra_agg not in ("average", "avg"))
        is_extra_meas = True
    else:
        raise QueryError(f"Unknown measure '{measure}'.")

    empty = ChartDataResponse(
        dimension=dimension,
        dimension_label=dim_label,
        measure=measure,
        measure_label=meas_label,
        measure_format=meas_format,
        points=[],
        total=0.0,
        group_count=0,
    )
    if df.empty:
        return empty

    if not is_extra_meas:
        unavailable_reason = measure_unavailable_reason(df, measure)
        if unavailable_reason:
            raise QueryError(unavailable_reason)
    elif df[measure].isna().any():
        missing_count = int(df[measure].isna().sum())
        raise QueryError(
            f"Not available: {meas_label} has {missing_count} blank or non-numeric value(s). "
            "Correct those cells before using this extra measure."
        )

    prepped = _prepare(df)
    keys = _dimension_series(prepped, dimension)

    has_quantity = "Quantity" in prepped.columns and prepped["Quantity"].notna().all()
    has_cost = (
        has_quantity
        and "Cost Price" in prepped.columns
        and prepped["Cost Price"].notna().all()
    )
    has_discount = "Discount" in prepped.columns

    agg_dict = {
        "revenue": ("_row_revenue", "sum"),
    }
    if has_cost:
        agg_dict["cost"] = ("_row_cost", "sum")
        agg_dict["profit"] = ("_row_profit", "sum")
    else:
        prepped["_dummy_cost"] = 0.0
        prepped["_dummy_profit"] = 0.0
        agg_dict["cost"] = ("_dummy_cost", "sum")
        agg_dict["profit"] = ("_dummy_profit", "sum")

    if has_discount:
        agg_dict["discount"] = ("_row_discount", "sum")
    else:
        prepped["_dummy_discount"] = 0.0
        agg_dict["discount"] = ("_dummy_discount", "sum")

    if has_quantity:
        agg_dict["units"] = ("Quantity", "sum")
        agg_dict["transactions"] = ("Quantity", "size")
    else:
        prepped["_dummy_units"] = 0
        agg_dict["units"] = ("_dummy_units", "sum")
        agg_dict["transactions"] = ("_row_revenue", "size")

    if is_extra_meas:
        agg_func = "mean" if extra_agg in ("average", "avg") else "sum"
        agg_dict["_extra_val"] = (measure, agg_func)
        if agg_func == "mean":
            agg_dict["_extra_count"] = (measure, "count")

    grouped = (
        prepped.assign(_group=keys)
        .groupby("_group", as_index=False)
        .agg(**agg_dict)
    )
    if grouped.empty:
        return empty

    if is_extra_meas:
        grouped["_value"] = grouped["_extra_val"]
    else:
        grouped["_value"] = grouped.apply(lambda r: _measure_value(r, measure), axis=1)

    # Ordering: chronological / weekday order for time dimensions, biggest
    # first for everything else.
    if dimension == "weekday":
        grouped["_order"] = grouped["_group"].map({d: i for i, d in enumerate(WEEKDAY_ORDER)})
        grouped = grouped.sort_values("_order").drop(columns="_order")
    elif dimension in TIME_DIMENSIONS:
        grouped = grouped.sort_values("_group")
    else:
        grouped = grouped.sort_values("_value", ascending=False)

    group_count = len(grouped)
    if is_extra_meas:
        if extra_agg in ("average", "avg"):
            total = float(df[measure].mean())
        else:
            total = float(df[measure].sum())
    else:
        total = float(grouped["_value"].sum()) if additive else _measure_value(
            grouped[["revenue", "cost", "profit", "discount", "units", "transactions"]].sum(), measure
        )

    # Pareto / concentration is only meaningful for additive measures and
    # non-time dimensions ("80% of revenue comes from N items").
    pareto_count: int | None = None
    if additive and dimension not in TIME_DIMENSIONS and total > 0:
        running = 0.0
        for value in grouped["_value"]:
            running += float(value)
            pareto_count = (pareto_count or 0) + 1
            if running / total >= 0.80:
                break

    # Fold the long tail so charts stay readable.
    fold = dimension not in TIME_DIMENSIONS and group_count > top_n
    head = grouped.head(top_n) if fold else grouped
    tail = grouped.iloc[top_n:] if fold else None

    points: list[ChartPoint] = []
    running = 0.0
    for _, row in head.iterrows():
        value = float(row["_value"])
        if additive:
            running += value
        points.append(
            _build_point(row, value, total, running if additive else None, additive,
                         has_cost=has_cost, has_quantity=has_quantity)
        )

    if tail is not None and not tail.empty:
        folded_cols = ["revenue", "cost", "profit", "discount", "units", "transactions"]
        if is_extra_meas:
            folded_cols.append("_extra_val")
            if "_extra_count" in tail.columns:
                folded_cols.append("_extra_count")
        folded = tail[folded_cols].sum(numeric_only=True)
        folded["_group"] = f"Other ({len(tail)})"
        if is_extra_meas:
            if extra_agg in ("average", "avg"):
                denominator = float(tail["_extra_count"].sum()) if "_extra_count" in tail else 0.0
                value = (
                    float((tail["_extra_val"] * tail["_extra_count"]).sum() / denominator)
                    if denominator else 0.0
                )
            else:
                value = float(tail["_extra_val"].sum())
        else:
            value = _measure_value(folded, measure)
        if additive:
            running += value
        point = _build_point(
            folded, value, total, running if additive else None, additive,
            has_cost=has_cost, has_quantity=has_quantity
        )
        points.append(point.model_copy(update={"is_other": True}))

    return ChartDataResponse(
        dimension=dimension,
        dimension_label=dim_label,
        measure=measure,
        measure_label=meas_label,
        measure_format=meas_format,
        points=points,
        total=safe_float(total, default=0.0) or 0.0,
        group_count=group_count,
        pareto_group_count=pareto_count,
    )


def _build_point(
    row,
    value: float,
    total: float,
    running: float | None,
    additive: bool,
    *,
    has_cost: bool,
    has_quantity: bool,
) -> ChartPoint:
    """Assemble one ``ChartPoint`` without turning unavailable metrics into zero."""
    revenue = float(row["revenue"])
    units = int(row["units"]) if has_quantity and "units" in row and pd.notna(row["units"]) else None
    cost = float(row["cost"]) if has_cost and "cost" in row and pd.notna(row["cost"]) else None
    profit = float(row["profit"]) if has_cost and "profit" in row and pd.notna(row["profit"]) else None
    transactions = safe_int(row["transactions"]) if "transactions" in row and pd.notna(row["transactions"]) else 0
    discount = float(row["discount"]) if "discount" in row and pd.notna(row["discount"]) else 0.0
    return ChartPoint(
        label=str(row["_group"]),
        value=safe_float(value, default=0.0) or 0.0,
        revenue=safe_float(revenue, default=0.0) or 0.0,
        cost=safe_float(cost) if cost is not None else None,
        profit=safe_float(profit) if profit is not None else None,
        units=units,
        transactions=transactions,
        discount=safe_float(discount, default=0.0) or 0.0,
        margin_pct=safe_percentage(profit, revenue) if profit is not None else None,
        avg_price=safe_float(revenue / units) if units is not None and units else None,
        share_pct=safe_percentage(value, total) if additive else None,
        cumulative_pct=safe_percentage(running, total) if (additive and running is not None) else None,
    )


# ── 4. Heatmap (weekday × calendar week) ────────────────────────────────────


def heatmap(df: pd.DataFrame, measure: str = "revenue") -> HeatmapResponse:
    """
    Build the weekday × week intensity grid — "which days of the week actually
    sell, and is that changing?".
    """
    extra_reg = getattr(df, "attrs", {}).get("extra_registry", {})
    if measure in MEASURES:
        meta = MEASURES[measure]
        measure_label = meta["label"]
        is_extra = False
        extra_agg = None
    elif measure.startswith("x_meas:") and measure in df.columns:
        meas_info = extra_reg.get(measure, {})
        measure_label = meas_info.get("display_label", measure)
        is_extra = True
        extra_agg = meas_info.get("aggregation", "sum")
    else:
        raise QueryError(f"Unknown measure '{measure}'.")

    empty = HeatmapResponse(
        rows=WEEKDAY_ORDER,
        columns=[],
        cells=[],
        measure=measure,
        measure_label=measure_label,
    )
    if df.empty:
        return empty

    if not is_extra:
        unavailable_reason = measure_unavailable_reason(df, measure)
        if unavailable_reason:
            raise QueryError(unavailable_reason)
    elif df[measure].isna().any():
        missing_count = int(df[measure].isna().sum())
        raise QueryError(
            f"Not available: {measure_label} has {missing_count} blank or non-numeric value(s). "
            "Correct those cells before using this extra measure."
        )

    prepped = _prepare(df)
    week_start = prepped["Date"].dt.to_period("W").dt.start_time

    has_quantity = "Quantity" in prepped.columns and prepped["Quantity"].notna().all()
    has_cost = (
        has_quantity
        and "Cost Price" in prepped.columns
        and prepped["Cost Price"].notna().all()
    )
    has_discount = "Discount" in prepped.columns

    agg_dict = {
        "revenue": ("_row_revenue", "sum"),
    }
    if has_cost:
        agg_dict["cost"] = ("_row_cost", "sum")
        agg_dict["profit"] = ("_row_profit", "sum")
    else:
        prepped["_dummy_cost"] = 0.0
        prepped["_dummy_profit"] = 0.0
        agg_dict["cost"] = ("_dummy_cost", "sum")
        agg_dict["profit"] = ("_dummy_profit", "sum")

    if has_discount:
        agg_dict["discount"] = ("_row_discount", "sum")
    else:
        prepped["_dummy_discount"] = 0.0
        agg_dict["discount"] = ("_dummy_discount", "sum")

    if has_quantity:
        agg_dict["units"] = ("Quantity", "sum")
        agg_dict["transactions"] = ("Quantity", "size")
    else:
        prepped["_dummy_units"] = 0
        agg_dict["units"] = ("_dummy_units", "sum")
        agg_dict["transactions"] = ("_row_revenue", "size")

    if is_extra:
        agg_dict["_extra_val"] = (measure, "mean" if extra_agg in ("average", "avg") else "sum")

    grouped = (
        prepped.assign(_week=week_start, _weekday=prepped["Date"].dt.strftime("%a"))
        .groupby(["_week", "_weekday"], as_index=False)
        .agg(**agg_dict)
    )
    if grouped.empty:
        return empty

    weeks = sorted(grouped["_week"].unique())
    columns = [f"W{pd.Timestamp(w).isocalendar().week:02d}" for w in weeks]
    column_dates = [pd.Timestamp(w).strftime("%Y-%m-%d") for w in weeks]
    week_to_column = {w: columns[i] for i, w in enumerate(weeks)}

    cells: list[HeatmapCell] = []
    values: list[float] = []
    for _, row in grouped.iterrows():
        if is_extra:
            value = float(row["_extra_val"])
        else:
            value = _measure_value(row, measure)
        values.append(value)
        cells.append(
            HeatmapCell(
                row=str(row["_weekday"]),
                column=week_to_column[row["_week"]],
                value=safe_float(value, default=0.0) or 0.0,
                transactions=safe_int(row["transactions"]),
            )
        )

    return HeatmapResponse(
        rows=WEEKDAY_ORDER,
        columns=columns,
        column_dates=column_dates,
        cells=cells,
        measure=measure,
        measure_label=measure_label,
        min_value=safe_float(min(values), default=0.0) or 0.0,
        max_value=safe_float(max(values), default=0.0) or 0.0,
    )


# ── 5. Filter-panel metadata ────────────────────────────────────────────────


def dimension_options(df: pd.DataFrame) -> DimensionsResponse:
    """
    Describe what this file can be sliced by: every canonical and extra dimension it
    actually contains, with its distinct values (capped), plus which optional
    and extra measures are available and the file's real date span.
    """
    column_to_key = {spec["column"]: key for key, spec in DIMENSIONS.items()}
    options: list[DimensionOption] = []

    for column in available_dimensions(df):
        key = column_to_key.get(column)
        if key is None:
            continue
        distinct = sorted(df[column].astype(str).unique().tolist())
        options.append(
            DimensionOption(
                key=key,
                label=DIMENSIONS[key]["label"],
                values=distinct[:MAX_DIMENSION_VALUES],
                total=len(distinct),
                selected_count=0,
                truncated=len(distinct) > MAX_DIMENSION_VALUES,
            )
        )

    # Include extra dimensions and extra measures from registry
    extra_reg = getattr(df, "attrs", {}).get("extra_registry", {})
    extra_measures = []
    for key, info in extra_reg.items():
        role = info.get("role")
        if role == "extra_dimension" and key in df.columns:
            distinct = sorted(df[key].astype(str).unique().tolist())
            options.append(
                DimensionOption(
                    key=key,
                    label=info.get("display_label", key),
                    values=distinct[:MAX_DIMENSION_VALUES],
                    total=len(distinct),
                    selected_count=0,
                    truncated=len(distinct) > MAX_DIMENSION_VALUES,
                )
            )
        elif role == "extra_measure" and key in df.columns:
            extra_measures.append(info)

    return DimensionsResponse(
        dimensions=options,
        optional_measures=available_measures(df),
        date_range=DataDateRange(**compute_data_date_range(df)),
        extra_measures=extra_measures,
        extra_registry=extra_reg,
    )


def dimension_option(
    df: pd.DataFrame,
    dimension: str,
    *,
    filters: dict[str, list[str]] | None = None,
    time_filter: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    search: str = "",
    limit: int = MAX_DIMENSION_VALUES,
) -> DimensionOption:
    """Return one dimension's currently valid option list."""
    extra_reg = getattr(df, "attrs", {}).get("extra_registry", {})
    if dimension in DIMENSIONS:
        spec = DIMENSIONS[dimension]
        column = spec["column"]
        label = spec["label"]
        if column.startswith("_time_"):
            raise QueryError(f"Dimension '{dimension}' cannot be used as a filter option.")
    elif dimension.startswith("x_dim:") and dimension in df.columns:
        column = dimension
        label = extra_reg.get(dimension, {}).get("display_label", dimension)
    else:
        raise QueryError(f"Unknown dimension '{dimension}'.")

    if column not in df.columns:
        raise QueryError(f"This file has no '{label}' column.")
    if limit < 1 or limit > 5000:
        raise QueryError("Option limit must be between 1 and 5000.")

    window = resolve_window(df, time_filter, start_date, end_date)
    context = slice_window(df, window.start, window.end)
    context_filters = {
        key: values
        for key, values in (filters or {}).items()
        if key != dimension and values
    }
    context = apply_filters(context, context_filters)

    available = sorted(context[column].astype(str).unique().tolist())
    selected = set((filters or {}).get(dimension, []))
    selected_count = len(selected.intersection(available))

    needle = str(search or "").strip().casefold()
    visible = [value for value in available if not needle or needle in value.casefold()]

    return DimensionOption(
        key=dimension,
        label=label,
        values=visible[:limit],
        total=len(available),
        selected_count=selected_count,
        truncated=len(visible) > limit,
    )
