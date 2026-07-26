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
        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize() + one_day
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
    return Window(start, end, start - span, start, PERIOD_LABELS.get(time_filter, time_filter))


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
    filtered = apply_filters(df, filters or {})
    window = resolve_window(filtered, time_filter, start_date, end_date)
    current = slice_window(filtered, window.start, window.end)
    previous = (
        slice_window(filtered, window.previous_start, window.previous_end)
        if window.previous_end > window.previous_start
        else filtered.iloc[0:0]
    )
    return current, previous, window


# ── 3. Generic aggregation ──────────────────────────────────────────────────


def _dimension_series(prepped: pd.DataFrame, dimension: str) -> pd.Series:
    """
    Build the grouping key for a dimension: a real column, or a label derived
    from ``Date`` for the three time dimensions.
    """
    spec = DIMENSIONS.get(dimension)
    if spec is None:
        raise QueryError(f"Unknown dimension '{dimension}'.")

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

    Behaviour worth knowing:

    * Every point carries all measures, so the frontend can switch chart type
      (and combo charts can plot revenue bars against a margin-% line)
      without another request.
    * Non-time dimensions are sorted by the requested measure, descending,
      then everything past ``top_n`` is folded into a single "Other" bucket —
      that keeps a donut readable (the design guidance caps a pie at 5–6
      slices) without hiding revenue from the totals.
    * Time dimensions stay in chronological order and are never folded;
      weekdays are ordered Mon→Sun rather than by size.
    * ``cumulative_pct`` is the Pareto curve, and ``pareto_group_count`` is
      how many groups make up the first 80% — the concentration-risk number.
    """
    if measure not in MEASURES:
        raise QueryError(f"Unknown measure '{measure}'.")
    meta = MEASURES[measure]
    dim_meta = DIMENSIONS.get(dimension)
    if dim_meta is None:
        raise QueryError(f"Unknown dimension '{dimension}'.")

    empty = ChartDataResponse(
        dimension=dimension,
        dimension_label=dim_meta["label"],
        measure=measure,
        measure_label=meta["label"],
        measure_format=meta["format"],
        points=[],
        total=0.0,
        group_count=0,
    )
    if df.empty:
        return empty

    prepped = _prepare(df)
    keys = _dimension_series(prepped, dimension)

    grouped = (
        prepped.assign(_group=keys)
        .groupby("_group", as_index=False)
        .agg(
            revenue=("_row_revenue", "sum"),
            cost=("_row_cost", "sum"),
            profit=("_row_profit", "sum"),
            discount=("_row_discount", "sum"),
            units=("Quantity", "sum"),
            transactions=("Quantity", "size"),
        )
    )
    if grouped.empty:
        return empty

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
    additive = bool(meta["additive"])
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
        points.append(_build_point(row, value, total, running if additive else None, additive))

    if tail is not None and not tail.empty:
        folded = tail[["revenue", "cost", "profit", "discount", "units", "transactions"]].sum()
        folded["_group"] = f"Other ({len(tail)})"
        value = _measure_value(folded, measure)
        if additive:
            running += value
        point = _build_point(folded, value, total, running if additive else None, additive)
        points.append(point.model_copy(update={"is_other": True}))

    return ChartDataResponse(
        dimension=dimension,
        dimension_label=dim_meta["label"],
        measure=measure,
        measure_label=meta["label"],
        measure_format=meta["format"],
        points=points,
        total=safe_float(total, default=0.0) or 0.0,
        group_count=group_count,
        pareto_group_count=pareto_count,
    )


def _build_point(row, value: float, total: float, running: float | None, additive: bool) -> ChartPoint:
    """Assemble one ``ChartPoint`` with every measure and its share/cumulative share."""
    revenue = float(row["revenue"])
    units = int(row["units"])
    return ChartPoint(
        label=str(row["_group"]),
        value=safe_float(value, default=0.0) or 0.0,
        revenue=safe_float(revenue, default=0.0) or 0.0,
        cost=safe_float(row["cost"], default=0.0) or 0.0,
        profit=safe_float(row["profit"], default=0.0) or 0.0,
        units=units,
        transactions=safe_int(row["transactions"]),
        discount=safe_float(row["discount"], default=0.0) or 0.0,
        margin_pct=safe_percentage(row["profit"], revenue),
        avg_price=safe_float(revenue / units) if units else None,
        share_pct=safe_percentage(value, total) if additive else None,
        cumulative_pct=safe_percentage(running, total) if (additive and running is not None) else None,
    )


# ── 4. Heatmap (weekday × calendar week) ────────────────────────────────────


def heatmap(df: pd.DataFrame, measure: str = "revenue") -> HeatmapResponse:
    """
    Build the weekday × week intensity grid — "which days of the week actually
    sell, and is that changing?".

    Columns are ISO weeks labelled with their Monday date so the legend can
    show real dates instead of an opaque week number. ``min_value`` /
    ``max_value`` ship with the payload so the UI can render a numeric legend
    rather than relying on colour alone (accessibility guidance).
    """
    meta = MEASURES.get(measure)
    if meta is None:
        raise QueryError(f"Unknown measure '{measure}'.")

    empty = HeatmapResponse(
        rows=WEEKDAY_ORDER,
        columns=[],
        cells=[],
        measure=measure,
        measure_label=meta["label"],
    )
    if df.empty:
        return empty

    prepped = _prepare(df)
    # Monday of each row's week — the stable key for a "week" column.
    week_start = prepped["Date"].dt.to_period("W").dt.start_time
    grouped = (
        prepped.assign(_week=week_start, _weekday=prepped["Date"].dt.strftime("%a"))
        .groupby(["_week", "_weekday"], as_index=False)
        .agg(
            revenue=("_row_revenue", "sum"),
            cost=("_row_cost", "sum"),
            profit=("_row_profit", "sum"),
            discount=("_row_discount", "sum"),
            units=("Quantity", "sum"),
            transactions=("Quantity", "size"),
        )
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
        measure_label=meta["label"],
        min_value=safe_float(min(values), default=0.0) or 0.0,
        max_value=safe_float(max(values), default=0.0) or 0.0,
    )


# ── 5. Filter-panel metadata ────────────────────────────────────────────────


def dimension_options(df: pd.DataFrame) -> DimensionsResponse:
    """
    Describe what this file can be sliced by: every canonical dimension it
    actually contains, with its distinct values (capped), plus which optional
    measures are available and the file's real date span.

    The frontend builds its filter chips and dimension dropdown purely from
    this, which is why a column the user never mapped can never become a
    filterable dimension.
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
                truncated=len(distinct) > MAX_DIMENSION_VALUES,
            )
        )

    return DimensionsResponse(
        dimensions=options,
        optional_measures=available_measures(df),
        date_range=DataDateRange(**compute_data_date_range(df)),
    )
