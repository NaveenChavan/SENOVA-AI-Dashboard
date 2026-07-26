"""
Tests for the insight engine (Feature 1).

These assert the *behaviour a shop owner depends on*: the known bad day is
found, the item priced below cost is called out, the numbers quoted in the text
are the numbers in ``metrics``, and short files produce an honest "not enough
data" instead of invented findings.
"""

import pandas as pd
import pytest

from app.services import query_engine
from app.services.insights_engine import (
    DEAD_STOCK_DAYS,
    MIN_DAYS_FOR_ANOMALY,
    _inr,
    compute_insights,
)
from tests.conftest import ANOMALY_DAY_INDEX, DEAD_ITEM, LEAK_ITEM


@pytest.fixture
def insights(normalized):
    """Insights over the whole synthetic file, with a previous period available."""
    current, previous, window = query_engine.build_slice(normalized, time_filter="all")
    return compute_insights(current, previous, period_label=window.label, max_insights=12)


def test_known_bad_day_is_detected(normalized, insights):
    """The deliberately crushed day must be flagged as an anomaly."""
    expected_day = (normalized["Date"].min() + pd.Timedelta(days=ANOMALY_DAY_INDEX)).date()
    assert str(expected_day) in insights.anomaly_dates

    anomaly_cards = [i for i in insights.insights if i.kind == "anomaly"]
    assert anomaly_cards, "expected at least one anomaly card"
    card = anomaly_cards[0]
    assert card.severity in ("critical", "warning")
    assert card.metrics["value"] < card.metrics["normal_level"]
    assert abs(card.metrics["z_score"]) >= 2.0


def test_margin_leak_finds_the_item_sold_near_cost(insights):
    """The item priced ₹20 above cost must be reported as a margin problem."""
    leaks = [i for i in insights.insights if i.kind == "margin"]
    assert leaks, "expected a margin-leak insight"
    assert LEAK_ITEM in leaks[0].evidence
    assert leaks[0].metrics["margin_pct"] < 10


def test_dead_stock_reports_the_item_that_stopped_selling(insights):
    """The item that vanishes after two weeks must show up as dead stock."""
    dead = [i for i in insights.insights if i.kind == "deadstock"]
    assert dead, "expected a dead-stock insight"
    assert DEAD_ITEM in dead[0].evidence
    assert dead[0].metrics["max_days_idle"] >= DEAD_STOCK_DAYS


def test_weekend_pattern_is_found(normalized):
    """The synthetic data sells 1.6× at weekends, so a weekday card is expected."""
    current, previous, window = query_engine.build_slice(normalized, time_filter="all")
    result = compute_insights(current, previous, period_label=window.label, max_insights=12)

    timing = [i for i in result.insights if i.kind == "timing"]
    assert timing, "expected a weekday-timing insight"
    assert timing[0].evidence[0] in ("Sat", "Sun")


def test_every_card_is_complete_and_sorted(insights):
    """Cards must be self-contained and ordered with the most severe first."""
    severity_rank = {"critical": 0, "warning": 1, "positive": 2, "neutral": 3}
    ranks = [severity_rank[i.severity] for i in insights.insights]

    assert ranks == sorted(ranks)
    for card in insights.insights:
        assert card.id and card.title and card.message
        assert card.severity in severity_rank
        # Numbers quoted in prose are also machine-readable for the UI.
        assert card.metrics
        # No unresolved template placeholders left in the text.
        assert "{" not in card.message and "}" not in card.message


def test_short_history_skips_anomaly_detection_honestly(short_frame):
    """Five days can't establish a 'normal level', so the check must be skipped."""
    result = compute_insights(short_frame, short_frame.iloc[0:0], period_label="Custom")

    assert len(short_frame["Date"].dt.date.unique()) < MIN_DAYS_FOR_ANOMALY
    assert result.anomaly_dates == []
    assert not [i for i in result.insights if i.kind == "anomaly"]
    assert result.note and "anomaly" in result.note.lower()


def test_empty_slice_returns_a_helpful_note(normalized):
    """An over-filtered period must explain itself rather than showing nothing."""
    result = compute_insights(normalized.iloc[0:0], normalized.iloc[0:0])
    assert result.insights == []
    assert result.note


def test_movers_need_a_previous_period(normalized):
    """Without a comparison period there is no such thing as a mover."""
    current, _previous, _window = query_engine.build_slice(normalized, time_filter="all")
    result = compute_insights(current, current.iloc[0:0], max_insights=12)
    assert not [i for i in result.insights if i.kind == "mover"]


def test_mover_card_appears_when_periods_differ(normalized):
    """With a real previous period, the biggest rupee change is reported."""
    current, previous, window = query_engine.build_slice(normalized, time_filter="30days")
    result = compute_insights(current, previous, period_label=window.label, max_insights=12)

    movers = [i for i in result.insights if i.kind == "mover"]
    assert movers
    for mover in movers:
        assert mover.metrics["current"] is not None
        assert mover.metrics["previous"] is not None


@pytest.mark.parametrize(
    "amount,expected",
    [
        (0, "₹0"),
        (999, "₹999"),
        (1240, "₹1,240"),
        (234567, "₹2.35L"),
        (12345678, "₹1.23Cr"),
        (-1500, "-₹1,500"),
    ],
)
def test_indian_number_formatting(amount, expected):
    """Amounts are written the way an Indian shop owner reads them."""
    assert _inr(amount) == expected
