"""
Feature 1 — the insight engine behind the AI cards on the dashboard.

What it does
------------
Runs six statistical checks over the selected slice and writes each finding as
a plain-language card: *what* happened, *how big* it is in rupees, and *what
to do about it*.

Why there is no language model here
-----------------------------------
Every sentence is a template filled with numbers this module computed itself.
That means a card can never invent a figure, costs nothing per request, works
with no internet connection, and — importantly for a shop's sales data —
nothing ever leaves the server. The card also carries a machine-readable
``metrics`` dict so the UI formats the numbers itself.

The six checks
--------------
1. **Revenue anomaly** — robust z-score on the zero-filled daily series:
   ``z = 0.6745 × (x − median) / MAD``. The median absolute deviation is used
   instead of the standard deviation because a single freak day inflates a
   std-dev enough to hide itself; MAD does not move. Falls back to std-dev
   when MAD is 0 (a series with many identical days).
2. **Movers** — biggest gainer/decliner vs the previous period, ranked by
   absolute rupee change, not percentage, so a 300% jump on a ₹50 item can't
   outrank a ₹40 000 collapse.
3. **Margin leak** — high-revenue items whose margin sits far below their own
   category's median (or is negative).
4. **Concentration** — the Pareto check: how few items make 80% of revenue.
5. **Timing** — best vs worst weekday, only when each weekday has enough
   observations to mean anything.
6. **Dead stock** — items with no sale for a long time, and what that ties up.

Every check is skipped (rather than guessed) when the slice is too small for
it to be honest — see the ``MIN_*`` constants.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.schemas import Insight, InsightsResponse
from app.services.sales_calculations import _prepare, _zero_fill_daily
from app.utils.safe_json import safe_float, safe_percentage

# ── Tuning constants (all in one place so they're easy to adjust) ────────────

#: |z| at or above this is reported as critical; the 3-sigma convention.
ANOMALY_Z_CRITICAL = 3.0
#: |z| at or above this is reported as a warning.
ANOMALY_Z_WARNING = 2.0
#: Below this many days a "normal level" is meaningless, so no anomaly check.
MIN_DAYS_FOR_ANOMALY = 7
#: Constant that scales MAD to be comparable with a standard deviation.
MAD_TO_SIGMA = 0.6745
#: Report at most this many anomalous days (the worst ones).
MAX_ANOMALY_CARDS = 2

#: Many shops don't sell every day. Once more than this share of the calendar is
#: a zero, the zero-filled series stops describing the business: its median
#: collapses to ₹0 and MAD to 0, which made *every* trading day look like an
#: outlier and printed the nonsense "0% above your normal daily level of ₹0".
#: Past this threshold the check runs on **trading days only** — a closed shop
#: is not an anomaly.
SPARSE_ZERO_DAY_SHARE = 0.25
#: A trading-day series still needs this many observations to judge an outlier.
MIN_TRADING_DAYS_FOR_ANOMALY = 7

#: An item must beat this share of total revenue before a margin problem on it
#: is worth the owner's attention.
MARGIN_LEAK_MIN_REVENUE_SHARE = 0.03
#: How many margin points below its category median counts as a leak.
MARGIN_LEAK_GAP_POINTS = 10.0
#: Need at least this many items in a category for its median to mean anything.
MIN_ITEMS_FOR_CATEGORY_MEDIAN = 3

#: Flag concentration risk when 80% of revenue comes from this share of items.
CONCENTRATION_ITEM_SHARE = 0.20
#: Concentration is only interesting once the shop sells a reasonable variety.
MIN_ITEMS_FOR_CONCENTRATION = 8

#: Weekday comparison needs this many observations of each weekday.
MIN_OBS_PER_WEEKDAY = 2
#: Only report a weekday gap this large (best ÷ worst) to avoid noise.
MIN_WEEKDAY_RATIO = 1.3

#: No sale for this many days → dead stock.
DEAD_STOCK_DAYS = 30
#: A mover must move at least this many rupees to be worth a card.
MIN_MOVER_AMOUNT = 1.0

#: Order used when sorting cards for display.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "positive": 2, "neutral": 3}


# ── Number formatting (Indian conventions) ──────────────────────────────────


def _inr(value: float | None) -> str:
    """
    Format an amount the way an Indian shop owner reads it: lakh/crore for big
    numbers, and 2,34,567-style grouping (not 234,567) for the rest.
    """
    if value is None:
        return "₹0"
    amount = float(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    if amount >= 1e7:
        return f"{sign}₹{amount / 1e7:.2f}Cr"
    if amount >= 1e5:
        return f"{sign}₹{amount / 1e5:.2f}L"

    whole = f"{int(round(amount)):d}"
    if len(whole) <= 3:
        return f"{sign}₹{whole}"
    # Last three digits, then groups of two — the Indian numbering system.
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups)},{tail}"


def _pct_text(value: float | None) -> str:
    """
    Format a percentage for prose, e.g. ``71%``.

    Returns ``"an unmeasurable amount"`` for ``None`` — which is what a division
    by a zero baseline yields — rather than printing a confident "0%".
    """
    if value is None:
        return "an unmeasurable amount"
    return f"{abs(float(value)):.0f}%"


def _date_text(value) -> str:
    """Format a date the way it reads in a sentence, e.g. ``14 Jul``."""
    stamp = pd.Timestamp(value)
    return f"{stamp.day} {stamp.strftime('%b')}"


# ── Main entry point ────────────────────────────────────────────────────────


def compute_insights(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    period_label: str = "the selected period",
    max_insights: int = 6,
) -> InsightsResponse:
    """
    Run every check over ``current`` (with ``previous`` for comparisons) and
    return the strongest findings, most severe first.

    ``current`` and ``previous`` are already-normalised, already-filtered
    frames from ``query_engine.build_slice`` — this module never slices data
    itself, so a card can't disagree with the charts above it.
    """
    if current.empty:
        return InsightsResponse(
            insights=[],
            anomaly_dates=[],
            analysed_days=0,
            note="No transactions in this period, so there is nothing to analyse yet.",
        )

    prepped = _prepare(current)
    daily = _daily_revenue(prepped)
    analysed_days = len(daily)

    insights: list[Insight] = []
    anomaly_dates: list[str] = []
    skipped: list[str] = []

    # 1. Anomalies
    anomaly_cards, anomaly_dates = _anomaly_insights(daily)
    if anomaly_cards is None:
        skipped.append("day-level anomaly detection needs at least a week of data")
    else:
        insights.extend(anomaly_cards)

    # 2. Movers vs the previous period
    insights.extend(_mover_insights(prepped, previous, period_label))

    # 3. Margin leaks
    insights.extend(_margin_leak_insights(prepped))

    # 4. Revenue concentration
    concentration = _concentration_insight(prepped)
    if concentration:
        insights.append(concentration)

    # 5. Weekday timing
    timing = _weekday_insight(prepped)
    if timing:
        insights.append(timing)

    # 6. Dead stock
    dead = _dead_stock_insight(prepped)
    if dead:
        insights.append(dead)

    # Most severe first, then biggest rupee impact within a severity.
    insights.sort(
        key=lambda i: (
            _SEVERITY_RANK.get(i.severity, 9),
            -abs(i.metrics.get("impact") or 0.0),
        )
    )

    note_parts: list[str] = []
    if not insights:
        note_parts.append(
            "Not enough data yet for reliable insights — upload at least two weeks "
            "of sales so trends and outliers can be measured."
        )
    if skipped:
        note_parts.append("Some checks were skipped: " + "; ".join(skipped) + ".")

    return InsightsResponse(
        insights=insights[:max_insights],
        anomaly_dates=anomaly_dates,
        analysed_days=analysed_days,
        note=" ".join(note_parts) or None,
    )


# ── Shared helpers ──────────────────────────────────────────────────────────


def _daily_revenue(prepped: pd.DataFrame) -> pd.DataFrame:
    """
    Daily revenue/profit/units for the slice, zero-filled across every
    calendar day. Zero-filling matters: a closed Sunday is real information,
    and dropping it would make the series look smoother than the shop is.
    """
    daily = (
        prepped.assign(_day=prepped["Date"].dt.date)
        .groupby("_day", as_index=False)
        .agg(
            revenue=("_row_revenue", "sum"),
            profit=("_row_profit", "sum"),
            units=("Quantity", "sum"),
        )
        .sort_values("_day")
    )
    return _zero_fill_daily(daily, prepped["Date"].min(), prepped["Date"].max())


def _item_totals(prepped: pd.DataFrame) -> pd.DataFrame:
    """Revenue / cost / profit / units per item, with margin % attached."""
    totals = prepped.groupby("Item", as_index=False).agg(
        revenue=("_row_revenue", "sum"),
        cost=("_row_cost", "sum"),
        profit=("_row_profit", "sum"),
        units=("Quantity", "sum"),
        category=("Category", "first"),
        last_sale=("Date", "max"),
    )
    totals["margin_pct"] = np.where(
        totals["revenue"] > 0, totals["profit"] / totals["revenue"] * 100, np.nan
    )
    return totals


# ── Check 1: revenue anomalies ──────────────────────────────────────────────


def _anomaly_insights(daily: pd.DataFrame) -> tuple[list[Insight] | None, list[str]]:
    """
    Flag days whose revenue is a statistical outlier.

    Two modes, chosen from the data:

    * **Dense** (the shop sells most days) — judge every calendar day, so a
      closed day *is* the finding.
    * **Sparse** (more than ``SPARSE_ZERO_DAY_SHARE`` of days have no sales) —
      judge trading days only. On a shop that opens three days a week the
      zero-filled median is ₹0 and MAD is 0, which makes every trading day
      score as an outlier and produces a meaningless "normal level of ₹0".

    Returns ``(None, [])`` when the series is too short to judge — the caller
    turns that into an honest "skipped" note instead of a fabricated finding.
    """
    if len(daily) < MIN_DAYS_FOR_ANOMALY:
        return None, []

    all_values = daily["revenue"].astype(float).to_numpy()
    zero_share = float((all_values <= 0).mean())
    sparse = zero_share > SPARSE_ZERO_DAY_SHARE

    if sparse:
        trading = daily[daily["revenue"] > 0]
        if len(trading) < MIN_TRADING_DAYS_FOR_ANOMALY:
            return None, []
        frame = trading
    else:
        frame = daily

    values = frame["revenue"].astype(float).to_numpy()
    days = frame["_day"].tolist()

    median = float(np.median(values))
    # MAD: median of absolute deviations from the median.
    mad = float(np.median(np.abs(values - median)))

    if mad > 0:
        scores = MAD_TO_SIGMA * (values - median) / mad
    else:
        # Every day is nearly identical; fall back to a plain z-score.
        std = float(np.std(values))
        if std == 0:
            return [], []
        scores = (values - median) / std

    # A baseline of 0 makes every comparison meaningless, so don't publish one.
    if median <= 0:
        return [], []

    day_word = "trading day" if sparse else "day"
    flagged: list[Insight] = []
    dates: list[str] = []

    # Worst first, so if we only show two cards they're the two that matter.
    for index in np.argsort(-np.abs(scores)):
        score = float(scores[index])
        if abs(score) < ANOMALY_Z_WARNING:
            break
        day = days[index]
        value = float(values[index])
        gap = value - median
        dates.append(str(day))

        if len(flagged) >= MAX_ANOMALY_CARDS:
            continue

        is_drop = gap < 0
        severity = "critical" if abs(score) >= ANOMALY_Z_CRITICAL else ("warning" if is_drop else "positive")
        direction = "below" if is_drop else "above"
        flagged.append(
            Insight(
                id=f"anomaly-{'drop' if is_drop else 'spike'}-{day}",
                kind="anomaly",
                severity=severity,
                title=f"Revenue {'dropped sharply' if is_drop else 'spiked'} on {_date_text(day)}",
                message=(
                    f"{_date_text(day)} took {_inr(value)} — "
                    f"{_pct_text(safe_percentage(abs(gap), median))} {direction} your typical {day_word} "
                    f"of {_inr(median)}. That single day moved the period total by {_inr(gap)}."
                ),
                action=(
                    "Check whether the shop was closed, staff were short, or sales simply "
                    "weren't recorded that day."
                    if is_drop
                    else "Find out what drove the spike (festival, promotion, bulk order) and repeat it."
                ),
                metrics={
                    "value": safe_float(value),
                    "normal_level": safe_float(median),
                    "difference": safe_float(gap),
                    "z_score": safe_float(score),
                    "impact": safe_float(abs(gap)),
                },
                evidence=[str(day)],
            )
        )

    return flagged, dates


# ── Check 2: movers vs the previous period ──────────────────────────────────


def _mover_insights(prepped: pd.DataFrame, previous: pd.DataFrame, period_label: str) -> list[Insight]:
    """
    Biggest riser and biggest decliner by rupee change.

    Only items present in *both* periods are compared: a brand-new item has no
    "previous" to grow from, and reporting it as +100% would be noise.
    """
    if previous is None or previous.empty:
        return []

    prev_prepped = _prepare(previous)
    now = prepped.groupby("Item")["_row_revenue"].sum()
    before = prev_prepped.groupby("Item")["_row_revenue"].sum()
    shared = now.index.intersection(before.index)
    if len(shared) == 0:
        return []

    delta = (now[shared] - before[shared]).sort_values()
    cards: list[Insight] = []

    def _card(item: str, change: float, rising: bool) -> Insight:
        old = float(before[item])
        new = float(now[item])
        return Insight(
            id=f"mover-{'up' if rising else 'down'}",
            kind="mover",
            severity="positive" if rising else "warning",
            title=f"'{item}' {'is growing fast' if rising else 'is losing sales'}",
            message=(
                f"'{item}' brought in {_inr(new)} this period versus {_inr(old)} before — "
                f"{'up' if rising else 'down'} {_inr(abs(change))} "
                f"({_pct_text(safe_percentage(change, old))}). "
                f"It is the biggest single {'gain' if rising else 'drop'} in {period_label}."
            ),
            action=(
                "Keep stock deep on this one and give it prime shelf space."
                if rising
                else "Check price, stock availability and display position before the slide continues."
            ),
            metrics={
                "current": safe_float(new),
                "previous": safe_float(old),
                "change": safe_float(change),
                "change_pct": safe_percentage(change, old),
                "impact": safe_float(abs(change)),
            },
            evidence=[item],
        )

    worst_item = delta.index[0]
    if float(delta.iloc[0]) < -MIN_MOVER_AMOUNT:
        cards.append(_card(str(worst_item), float(delta.iloc[0]), rising=False))

    best_item = delta.index[-1]
    if float(delta.iloc[-1]) > MIN_MOVER_AMOUNT and best_item != worst_item:
        cards.append(_card(str(best_item), float(delta.iloc[-1]), rising=True))

    return cards


# ── Check 3: margin leaks ───────────────────────────────────────────────────


def _margin_leak_insights(prepped: pd.DataFrame) -> list[Insight]:
    """
    Find an item that sells well but earns little: either a negative margin,
    or a margin far below the median of its own category (comparing within the
    category avoids flagging a whole low-margin product line as broken).
    """
    totals = _item_totals(prepped)
    total_revenue = float(totals["revenue"].sum())
    if total_revenue <= 0 or totals.empty:
        return []

    # Only items that matter to the top line.
    significant = totals[totals["revenue"] >= total_revenue * MARGIN_LEAK_MIN_REVENUE_SHARE]
    if significant.empty:
        return []

    # Category medians, but only where a category holds enough items for a
    # median to mean something. Small categories fall back to the shop-wide
    # median, which is still a fair yardstick and stops a two-item category
    # from hiding a real problem.
    counts = totals.groupby("category")["Item"].count()
    medians = totals.groupby("category")["margin_pct"].median()
    reliable = set(counts[counts >= MIN_ITEMS_FOR_CATEGORY_MEDIAN].index)
    overall_median = float(totals["margin_pct"].median()) if totals["margin_pct"].notna().any() else None

    def _benchmark(category: str) -> tuple[float | None, bool]:
        """Return (median margin to compare against, whether it is category-specific)."""
        if category in reliable and pd.notna(medians.get(category)):
            return float(medians[category]), True
        return overall_median, False

    worst_row = None
    worst_gap = 0.0
    worst_benchmark: float | None = None
    worst_is_category = False
    for _, row in significant.iterrows():
        margin = float(row["margin_pct"]) if pd.notna(row["margin_pct"]) else 0.0
        benchmark, is_category = _benchmark(str(row["category"]))
        if margin < 0:
            # Selling below cost always outranks a mere gap to the median.
            gap = abs(margin) + 100.0
        elif benchmark is None:
            continue
        else:
            gap = benchmark - margin
        if gap > worst_gap and gap >= MARGIN_LEAK_GAP_POINTS:
            worst_gap, worst_row = gap, row
            worst_benchmark, worst_is_category = benchmark, is_category

    if worst_row is None:
        return []

    margin = float(worst_row["margin_pct"]) if pd.notna(worst_row["margin_pct"]) else 0.0
    category = str(worst_row["category"])
    peer_median = worst_benchmark
    peer_label = category if worst_is_category else "your shop overall"
    negative = margin < 0

    return [
        Insight(
            id="margin-leak",
            kind="margin",
            severity="critical" if negative else "warning",
            title=f"'{worst_row['Item']}' sells well but earns little",
            message=(
                f"'{worst_row['Item']}' generated {_inr(worst_row['revenue'])} in revenue but only "
                f"{_inr(worst_row['profit'])} in profit ({margin:.1f}% margin"
                + (
                    f", against {peer_median:.1f}% typical for {peer_label})."
                    if peer_median is not None
                    else ")."
                )
                + (" You are selling it below cost." if negative else "")
            ),
            action="Re-check its cost price entry, trim the discount on it, or raise the price.",
            metrics={
                "revenue": safe_float(worst_row["revenue"]),
                "profit": safe_float(worst_row["profit"]),
                "margin_pct": safe_float(margin),
                "benchmark_margin_pct": safe_float(peer_median),
                "impact": safe_float(worst_row["revenue"]),
            },
            evidence=[str(worst_row["Item"])],
        )
    ]


# ── Check 4: revenue concentration (Pareto) ─────────────────────────────────


def _concentration_insight(prepped: pd.DataFrame) -> Insight | None:
    """
    How many items make up 80% of revenue. A very small number is a real
    operational risk: one stockout in that handful hits the whole shop.
    """
    totals = _item_totals(prepped).sort_values("revenue", ascending=False)
    item_count = len(totals)
    total_revenue = float(totals["revenue"].sum())
    if item_count < MIN_ITEMS_FOR_CONCENTRATION or total_revenue <= 0:
        return None

    cumulative = totals["revenue"].cumsum() / total_revenue
    # +1 because the position where the curve first crosses 80% is inclusive.
    top_count = int((cumulative < 0.80).sum()) + 1
    share = top_count / item_count
    if share > CONCENTRATION_ITEM_SHARE:
        return None

    leaders = [str(name) for name in totals["Item"].head(min(top_count, 5)).tolist()]
    return Insight(
        id="concentration",
        kind="concentration",
        severity="neutral",
        title=f"{top_count} of {item_count} items make 80% of your revenue",
        message=(
            f"Just {top_count} item(s) — {_pct_text(share * 100)} of your range — produce 80% of "
            f"revenue ({_inr(total_revenue * 0.8)}). A stockout in any of them hits the whole shop."
        ),
        action="Never let these run out; keep buffer stock and track them daily.",
        metrics={
            "top_items": float(top_count),
            "total_items": float(item_count),
            "item_share_pct": safe_float(share * 100),
            "impact": safe_float(total_revenue * 0.8),
        },
        evidence=leaders,
    )


# ── Check 5: weekday timing ─────────────────────────────────────────────────


def _weekday_insight(prepped: pd.DataFrame) -> Insight | None:
    """
    Best vs worst weekday by average revenue per occurrence.

    Requires every weekday present to have been observed at least
    ``MIN_OBS_PER_WEEKDAY`` times, otherwise one exceptional Saturday would
    "prove" that Saturdays are best.
    """
    per_day = (
        prepped.assign(_day=prepped["Date"].dt.date, _weekday=prepped["Date"].dt.strftime("%a"))
        .groupby(["_weekday", "_day"], as_index=False)["_row_revenue"]
        .sum()
    )
    if per_day.empty:
        return None

    stats = per_day.groupby("_weekday")["_row_revenue"].agg(["mean", "count"])
    stats = stats[stats["count"] >= MIN_OBS_PER_WEEKDAY]
    if len(stats) < 2:
        return None

    best = stats["mean"].idxmax()
    worst = stats["mean"].idxmin()
    best_value = float(stats.loc[best, "mean"])
    worst_value = float(stats.loc[worst, "mean"])
    if worst_value <= 0 or best_value / worst_value < MIN_WEEKDAY_RATIO:
        return None

    return Insight(
        id="weekday-timing",
        kind="timing",
        severity="neutral",
        title=f"{best} is your strongest day, {worst} the weakest",
        message=(
            f"{best} averages {_inr(best_value)} per day against {_inr(worst_value)} on {worst} — "
            f"{best_value / worst_value:.1f}× the takings."
        ),
        action=f"Staff and stock up for {best}; try a promotion or shorter hours on {worst}.",
        metrics={
            "best_average": safe_float(best_value),
            "worst_average": safe_float(worst_value),
            "ratio": safe_float(best_value / worst_value),
            "impact": safe_float(best_value - worst_value),
        },
        evidence=[str(best), str(worst)],
    )


# ── Check 6: dead stock ─────────────────────────────────────────────────────


def _dead_stock_insight(prepped: pd.DataFrame) -> Insight | None:
    """Items with no sale for ``DEAD_STOCK_DAYS``, and what they earned when they did sell."""
    totals = _item_totals(prepped)
    if totals.empty:
        return None

    latest = prepped["Date"].max()
    totals["days_idle"] = (latest - totals["last_sale"]).dt.days
    stale = totals[totals["days_idle"] >= DEAD_STOCK_DAYS].sort_values("days_idle", ascending=False)
    if stale.empty:
        return None

    worst = stale.iloc[0]
    return Insight(
        id="dead-stock",
        kind="deadstock",
        severity="warning",
        title=f"{len(stale)} item(s) haven't sold in over {DEAD_STOCK_DAYS} days",
        message=(
            f"{len(stale)} item(s) have had no sale for {DEAD_STOCK_DAYS}+ days — the longest is "
            f"'{worst['Item']}' at {int(worst['days_idle'])} days idle. Together they earned only "
            f"{_inr(stale['revenue'].sum())} in this period."
        ),
        action="Discount, bundle or return them — they are occupying shelf space and working capital.",
        metrics={
            "item_count": float(len(stale)),
            "max_days_idle": float(worst["days_idle"]),
            "revenue": safe_float(stale["revenue"].sum()),
            "impact": safe_float(stale["revenue"].sum()),
        },
        evidence=[str(name) for name in stale["Item"].head(5).tolist()],
    )
