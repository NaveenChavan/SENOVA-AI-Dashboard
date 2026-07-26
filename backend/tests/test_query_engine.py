"""
Tests for the shared query + aggregation layer.

Focus areas:
* windows are anchored to the newest date in the file, and the comparison
  period is the same length immediately before;
* filters only accept known dimensions and are applied by membership;
* aggregation totals reconcile with the raw data, ``top_n`` folding preserves
  the totals, and the Pareto/heatmap outputs are internally consistent.
"""

import pandas as pd
import pytest

from app.services import query_engine
from app.services.query_engine import QueryError


def test_window_is_anchored_to_the_data_not_the_clock(normalized):
    """A file uploaded months later must still produce a sensible 'last 7 days'."""
    window = query_engine.resolve_window(normalized, "week")
    last_day = normalized["Date"].max().normalize()

    assert window.end == last_day + pd.Timedelta(days=1)
    assert window.start == last_day - pd.Timedelta(days=6)
    # Previous period is the same length, immediately before.
    assert window.end - window.start == window.previous_end - window.previous_start
    assert window.previous_end == window.start


def test_all_time_window_has_no_previous_period(normalized):
    """'All Time' is the whole file, so there is nothing before it to compare."""
    window = query_engine.resolve_window(normalized, "all")
    assert window.previous_start == window.previous_end


def test_custom_window_respects_explicit_dates(normalized):
    start = pd.Timestamp("2026-02-01").date()
    end = pd.Timestamp("2026-02-10").date()
    current, previous, window = query_engine.build_slice(
        normalized, time_filter="custom", start_date=start, end_date=end
    )

    assert current["Date"].min() >= pd.Timestamp(start)
    assert current["Date"].max() < pd.Timestamp(end) + pd.Timedelta(days=1)
    # 10-day window → 10-day comparison window directly before it.
    assert window.previous_start == pd.Timestamp("2026-01-22")
    assert not previous.empty


def test_filters_restrict_rows(normalized):
    """A branch filter must be applied to both the current and previous period."""
    current, previous, _window = query_engine.build_slice(
        normalized, time_filter="all", filters={"branch": ["MG Road"]}
    )
    assert set(current["Branch"].unique()) == {"MG Road"}
    assert previous.empty or set(previous["Branch"].unique()) == {"MG Road"}


def test_empty_filter_list_means_no_restriction(normalized):
    """An empty selection is 'show everything', not 'show nothing'."""
    current, _previous, _window = query_engine.build_slice(
        normalized, time_filter="all", filters={"branch": []}
    )
    assert len(current) == len(normalized)


def test_unknown_filter_dimension_is_rejected(normalized):
    """Unknown keys must fail loudly — a silently ignored filter misleads the user."""
    with pytest.raises(QueryError):
        query_engine.apply_filters(normalized, {"__proto__": ["x"]})
    with pytest.raises(QueryError):
        query_engine.apply_filters(normalized, {"salesperson": ["Ravi"]})  # not in this file


def test_time_dimension_cannot_be_used_as_a_filter(normalized):
    with pytest.raises(QueryError):
        query_engine.apply_filters(normalized, {"weekday": ["Mon"]})


def test_aggregate_totals_match_the_raw_data(normalized):
    """Revenue summed over groups must equal revenue computed row by row."""
    response = query_engine.aggregate(normalized, dimension="category", measure="revenue", top_n=50)

    expected = float(
        (normalized["Quantity"] * normalized["Selling Price"] - normalized["Discount"]).clip(lower=0).sum()
    )
    assert response.total == pytest.approx(expected, rel=1e-6)
    assert sum(point.value for point in response.points) == pytest.approx(expected, rel=1e-6)
    assert response.measure_format == "currency"


def test_every_point_carries_all_measures(normalized):
    """One request must be enough to draw combo, scatter and Pareto views."""
    response = query_engine.aggregate(normalized, dimension="item", measure="revenue", top_n=10)
    point = response.points[0]

    assert point.units > 0
    assert point.transactions > 0
    assert point.margin_pct is not None
    assert point.avg_price is not None
    assert point.share_pct is not None
    assert point.cumulative_pct is not None
    # Profit must reconcile with revenue and cost on the same point.
    assert point.profit == pytest.approx(point.revenue - point.cost, rel=1e-6)


def test_top_n_folds_the_tail_without_losing_money(normalized):
    """The 'Other' bucket keeps the totals honest when the long tail is folded."""
    full = query_engine.aggregate(normalized, dimension="item", measure="revenue", top_n=50)
    folded = query_engine.aggregate(normalized, dimension="item", measure="revenue", top_n=2)

    assert len(folded.points) == 3  # 2 items + Other
    assert folded.points[-1].is_other is True
    assert sum(p.value for p in folded.points) == pytest.approx(full.total, rel=1e-6)
    # The final cumulative share must reach 100%.
    assert folded.points[-1].cumulative_pct == pytest.approx(100.0, abs=0.01)


def test_time_dimensions_stay_in_order_and_are_never_folded(normalized):
    """Chronology matters more than size for a time axis."""
    by_day = query_engine.aggregate(normalized, dimension="day", measure="revenue", top_n=5)
    labels = [p.label for p in by_day.points]
    assert labels == sorted(labels)
    assert len(labels) > 5  # top_n must not truncate a time series
    assert all(p.is_other is False for p in by_day.points)

    by_weekday = query_engine.aggregate(normalized, dimension="weekday", measure="revenue")
    assert [p.label for p in by_weekday.points] == [
        d for d in query_engine.WEEKDAY_ORDER if d in {p.label for p in by_weekday.points}
    ]


def test_ratio_measures_have_no_share_or_cumulative(normalized):
    """Margin % can't be summed, so a share of total would be nonsense."""
    response = query_engine.aggregate(normalized, dimension="category", measure="margin_pct")
    assert response.measure_format == "percent"
    assert all(point.share_pct is None for point in response.points)
    assert all(point.cumulative_pct is None for point in response.points)


def test_pareto_group_count_is_reported(normalized):
    """The concentration number must be within the number of groups."""
    response = query_engine.aggregate(normalized, dimension="item", measure="revenue", top_n=50)
    assert response.pareto_group_count is not None
    assert 1 <= response.pareto_group_count <= response.group_count


def test_unknown_dimension_or_measure_is_rejected(normalized):
    with pytest.raises(QueryError):
        query_engine.aggregate(normalized, dimension="nope", measure="revenue")
    with pytest.raises(QueryError):
        query_engine.aggregate(normalized, dimension="category", measure="nope")


def test_aggregate_handles_an_empty_slice(normalized):
    """An over-restrictive filter must produce an empty chart, not a crash."""
    response = query_engine.aggregate(normalized.iloc[0:0], dimension="category", measure="revenue")
    assert response.points == []
    assert response.total == 0.0


def test_heatmap_grid_is_consistent(normalized):
    """Cells must reference declared rows/columns and carry a numeric legend."""
    grid = query_engine.heatmap(normalized, measure="revenue")

    assert grid.rows == query_engine.WEEKDAY_ORDER
    assert len(grid.columns) == len(grid.column_dates)
    assert grid.cells
    for cell in grid.cells:
        assert cell.row in grid.rows
        assert cell.column in grid.columns
    assert grid.max_value >= grid.min_value


def test_dimension_options_only_expose_present_columns(normalized):
    """A column the user never mapped can never become a filter."""
    options = query_engine.dimension_options(normalized)
    keys = {option.key for option in options.dimensions}

    assert {"category", "item", "branch", "payment_mode"} <= keys
    assert "salesperson" not in keys  # not in this file
    assert "Stock On Hand" in options.optional_measures
    assert options.date_range.span_days == 90
