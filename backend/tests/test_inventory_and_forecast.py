"""
Tests for inventory & reorder intelligence (Feature 3) and the forecast engine
(Feature 2).

The point of these tests is the *honesty* of both modules as much as the maths:
stock-dependent figures must be ``null`` when no stock column was mapped, and a
forecast must refuse to appear when the history is too short.
"""

import pandas as pd
import pytest

from app.services.forecasting import (
    MIN_DAYS_FOR_FORECAST,
    MIN_DAYS_FOR_SEASONALITY,
    compute_forecast,
)
from app.services.inventory_intel import (
    REORDER_COVER_DAYS,
    compute_inventory_intelligence,
)
from tests.conftest import DEAD_ITEM


# ── Inventory ───────────────────────────────────────────────────────────────


def test_inventory_reports_velocity_and_activity(normalized):
    """Velocity must reconcile with units sold over the window length."""
    result = compute_inventory_intelligence(normalized, top_n=50)

    assert result.window_days == 90
    assert result.items

    by_item = {item.item: item for item in result.items}
    kurta = by_item["Cotton Kurta"]
    assert kurta.velocity_per_day == pytest.approx(kurta.units_sold / 90, rel=0.02)
    # It sold on most days, so active velocity is close to calendar velocity.
    assert kurta.velocity_active >= kurta.velocity_per_day
    assert kurta.active_days > 0
    assert kurta.margin_pct is not None


def test_abc_classification_covers_every_item(normalized):
    """A/B/C buckets must partition the catalogue, with A carrying the revenue."""
    result = compute_inventory_intelligence(normalized, top_n=50)

    total_items = sum(bucket.item_count for bucket in result.abc_buckets)
    assert total_items == normalized["Item"].nunique()

    a_bucket = result.abc_buckets[0]
    assert a_bucket.revenue_share_pct is not None
    assert a_bucket.revenue_share_pct <= 100.0
    assert {item.abc_class for item in result.items} <= {"A", "B", "C"}

    # The biggest earner is always class A, whatever its share.
    top_earner = max(result.items, key=lambda item: item.revenue)
    assert top_earner.abc_class == "A"


def test_a_single_item_shop_is_class_a_not_the_long_tail(normalized):
    """
    One item holding 100% of revenue is the business, not the tail. Testing the
    cumulative share *after* inclusion (1.0 > 0.80) used to label it "C".
    """
    one_item = normalized[normalized["Item"] == "Cotton Kurta"].copy()
    result = compute_inventory_intelligence(one_item, top_n=10)

    assert len(result.items) == 1
    assert result.items[0].abc_class == "A"
    assert result.abc_buckets[0].item_count == 1
    assert result.abc_buckets[0].revenue_share_pct == pytest.approx(100.0, abs=0.01)


def test_ageing_buckets_flag_the_idle_item(normalized):
    """The item that stopped selling 75 days ago must land in 'Dead'."""
    result = compute_inventory_intelligence(normalized, top_n=50)
    by_item = {item.item: item for item in result.items}

    assert by_item[DEAD_ITEM].ageing_bucket == "Dead"
    assert by_item[DEAD_ITEM].days_since_last_sale >= 60
    assert by_item["Cotton Kurta"].ageing_bucket == "Fresh"

    labels = " ".join(bucket.label for bucket in result.ageing_buckets)
    assert "Dead" in labels and "Fresh" in labels


def test_reorder_priority_ranks_movers_above_idle_stock(normalized):
    """A fast, recent seller must outrank an item nobody has bought in months."""
    result = compute_inventory_intelligence(normalized, top_n=50)
    by_item = {item.item: item for item in result.items}

    assert by_item["Cotton Kurta"].reorder_priority > by_item[DEAD_ITEM].reorder_priority
    assert 0.0 <= by_item[DEAD_ITEM].reorder_priority <= 100.0
    # The table is returned already sorted by priority.
    priorities = [item.reorder_priority for item in result.items]
    assert priorities == sorted(priorities, reverse=True)


def test_stock_aware_mode_computes_cover_and_capital(normalized):
    """With a stock column mapped, cover and locked capital become real numbers."""
    result = compute_inventory_intelligence(normalized, top_n=50)

    assert result.stock_aware is True
    assert result.note is None
    assert result.total_capital_locked and result.total_capital_locked > 0

    kurta = next(item for item in result.items if item.item == "Cotton Kurta")
    assert kurta.stock_on_hand == 40
    assert kurta.days_of_cover == pytest.approx(40 / kurta.velocity_per_day, rel=0.02)
    assert kurta.reorder_flag == (kurta.days_of_cover < REORDER_COVER_DAYS)


def test_demand_mode_never_guesses_stock(normalized):
    """Without a stock column, cover/capital must be null and explained."""
    sales_only = normalized.drop(columns=["Stock On Hand"])
    result = compute_inventory_intelligence(sales_only, top_n=50)

    assert result.stock_aware is False
    assert result.total_capital_locked is None
    assert all(item.days_of_cover is None for item in result.items)
    assert all(item.capital_locked is None for item in result.items)
    assert all(item.reorder_flag is False for item in result.items)
    assert result.note and "stock column" in result.note


def test_inventory_handles_an_empty_slice(normalized):
    result = compute_inventory_intelligence(normalized.iloc[0:0])
    assert result.items == []
    assert result.note


# ── Forecast ────────────────────────────────────────────────────────────────


def test_forecast_refuses_short_history(short_frame):
    """Five days of data must produce a refusal, not a confident-looking line."""
    result = compute_forecast(short_frame, horizon_days=14)

    assert result.available is False
    assert result.points == []
    assert result.reason and str(MIN_DAYS_FOR_FORECAST) in result.reason


def test_forecast_projects_the_requested_horizon(normalized):
    """History plus horizon must both be present, and the band must bracket it."""
    result = compute_forecast(normalized, horizon_days=14)

    assert result.available is True
    assert result.horizon_days == 14

    future = [point for point in result.points if point.is_future]
    history = [point for point in result.points if not point.is_future]
    assert len(future) == 14
    assert len(history) == 90

    # Dates continue day by day with no gap or repeat.
    dates = [pd.Timestamp(point.date) for point in result.points]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)

    for point in future:
        assert point.forecast is not None
        assert point.lower <= point.forecast <= point.upper
        assert point.forecast >= 0  # revenue can never be negative
        assert point.lower >= 0

    # The band widens with distance from the last observed day.
    assert (future[-1].upper - future[-1].lower) >= (future[0].upper - future[0].lower)


def test_forecast_totals_match_the_daily_points(normalized):
    """The headline expected revenue must be the sum of the plotted days."""
    result = compute_forecast(normalized, horizon_days=7)
    future = [point for point in result.points if point.is_future]

    assert result.expected_revenue == pytest.approx(sum(p.forecast for p in future), rel=1e-6)
    assert result.expected_revenue_lower <= result.expected_revenue <= result.expected_revenue_upper


def test_forecast_reports_seasonality_and_accuracy(normalized):
    """90 days is enough for weekday seasonality and a 7-day backtest."""
    result = compute_forecast(normalized, horizon_days=14)

    assert result.seasonality_applied is True
    assert set(result.weekday_indices) <= {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    # Weekends sell 1.6× in the fixture, so their index must exceed a weekday's.
    assert result.weekday_indices["Sat"] > result.weekday_indices["Tue"]

    assert result.accuracy_pct is not None
    assert 0.0 <= result.accuracy_pct <= 100.0
    assert result.trend_direction in ("rising", "flat", "falling")


def test_forecast_without_enough_history_for_seasonality(normalized):
    """Between 14 and 21 days the trend is used alone, and that is stated."""
    cutoff = normalized["Date"].min() + pd.Timedelta(days=15)
    medium = normalized[normalized["Date"] <= cutoff]

    result = compute_forecast(medium, horizon_days=7)
    assert result.available is True
    assert result.seasonality_applied is False
    assert result.reason and str(MIN_DAYS_FOR_SEASONALITY) in result.reason


def test_item_forecasts_are_bounded_and_useful(normalized):
    """Per-item demand feeds the reorder table, so it must be present and sane."""
    result = compute_forecast(normalized, horizon_days=30)

    assert result.item_forecasts
    assert len(result.item_forecasts) <= 20
    for item in result.item_forecasts:
        assert item.expected_units >= 0
        assert item.velocity_per_day >= 0
        assert 0.25 <= item.trend_factor <= 4.0


def test_forecast_horizon_is_capped(normalized):
    """A caller asking for 5 years gets the documented 90-day maximum."""
    result = compute_forecast(normalized, horizon_days=5000)
    assert result.horizon_days == 90
    assert len([p for p in result.points if p.is_future]) == 90
