"""
Feature 3 — inventory & reorder intelligence.

An honest limitation, handled explicitly
----------------------------------------
An uploaded sales register says what *left* the shop; it says nothing about
what is still on the shelf. So true days-of-cover and "capital locked in dead
stock" are only computable when the file maps a stock column (``Stock``,
``Closing Stock``, ``Balance Qty``, ``On Hand``…).

This module therefore has two modes and never blurs them:

* **Demand mode** (default) — velocity, trend, ABC class, ageing and a
  reorder-priority score. All of it derived from sales alone; ``days_of_cover``
  and ``capital_locked`` come back as ``null`` instead of a guess.
* **Stock-aware mode** — when a stock column exists, the same table plus real
  days of cover, reorder alerts and working capital tied up per item.

What each number means
----------------------
``velocity_per_day``   units ÷ every calendar day in the window (planning rate)
``velocity_active``    units ÷ days it actually sold on — separates a steady
                       seller from one bulk order that flattered the average
``trend_factor``       late-window velocity ÷ early-window velocity;
                       >1 accelerating, <1 slowing
``abc_class``          A = the items making the first 80% of revenue,
                       B = the next 15%, C = the long tail
``ageing_bucket``      how long since the last sale (Fresh/Slow/Stale/Dead)
``reorder_priority``   0–100 blend of velocity, trend and recency
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.schemas import InventoryBucket, InventoryItem, InventoryResponse
from app.services.sales_calculations import _prepare
from app.utils.safe_json import safe_float, safe_int, safe_percentage

# ── Tuning constants ────────────────────────────────────────────────────────

#: Revenue share boundaries for ABC classification.
ABC_A_THRESHOLD = 0.80
ABC_B_THRESHOLD = 0.95

#: Days since the last sale that define each ageing bucket.
AGEING_FRESH_DAYS = 15
AGEING_SLOW_DAYS = 30
AGEING_STALE_DAYS = 60

#: Weights of the reorder-priority score. They sum to 1.0; adjust freely.
WEIGHT_VELOCITY = 0.50
WEIGHT_TREND = 0.30
WEIGHT_RECENCY = 0.20

#: A trend factor is clamped to this range so one freak day can't dominate.
TREND_CLAMP = (0.25, 4.0)
#: Recency contribution decays to zero over this many idle days.
RECENCY_HORIZON_DAYS = 60

#: Stock-aware mode: fewer than this many days of cover raises a reorder flag.
REORDER_COVER_DAYS = 7

#: Never return more than this many rows (the UI pages/sorts client-side).
MAX_ITEMS_RETURNED = 200


def compute_inventory_intelligence(df: pd.DataFrame, top_n: int = 50) -> InventoryResponse:
    """
    Build the inventory panel for an already-filtered slice.

    ``top_n`` bounds the returned table (highest reorder priority first) so a
    file with 10 000 SKUs can't produce a 10 000-row JSON payload.
    """
    if df.empty:
        return InventoryResponse(
            stock_aware=False,
            window_days=0,
            items=[],
            note="No transactions in this period, so there is no demand to measure.",
        )

    prepped = _prepare(df)
    window_start = prepped["Date"].min().normalize()
    window_end = prepped["Date"].max().normalize()
    window_days = int((window_end - window_start).days) + 1
    stock_aware = "Stock On Hand" in df.columns

    per_item = _aggregate_items(prepped, stock_aware)
    per_item["days_since_last_sale"] = (window_end - per_item["last_sale"].dt.normalize()).dt.days
    per_item["velocity_per_day"] = per_item["units"] / max(window_days, 1)
    per_item["velocity_active"] = np.where(
        per_item["active_days"] > 0, per_item["units"] / per_item["active_days"], 0.0
    )
    per_item["trend_factor"] = (
        per_item["Item"].map(_trend_factors(prepped, window_start, window_end)).fillna(1.0)
    )
    per_item = _classify_abc(per_item)
    per_item["ageing_bucket"] = per_item["days_since_last_sale"].apply(_ageing_bucket)
    per_item["reorder_priority"] = _priority_scores(per_item)

    if stock_aware:
        # Cover in days, and the money sitting in that stock. Velocity of 0
        # would mean "infinite cover", which is not a number the UI can plot —
        # it is reported as null and the item shows as dead stock instead.
        per_item["days_of_cover"] = np.where(
            per_item["velocity_per_day"] > 0,
            per_item["stock_on_hand"] / per_item["velocity_per_day"],
            np.nan,
        )
        per_item["capital_locked"] = per_item["stock_on_hand"] * per_item["avg_cost"]
        per_item["reorder_flag"] = per_item["days_of_cover"] < REORDER_COVER_DAYS
    else:
        per_item["days_of_cover"] = np.nan
        per_item["capital_locked"] = np.nan
        per_item["reorder_flag"] = False

    ranked = per_item.sort_values("reorder_priority", ascending=False)
    limit = min(max(top_n, 1), MAX_ITEMS_RETURNED)

    items = [_to_schema(row, stock_aware) for _, row in ranked.head(limit).iterrows()]

    return InventoryResponse(
        stock_aware=stock_aware,
        window_days=window_days,
        items=items,
        abc_buckets=_abc_buckets(per_item, stock_aware),
        ageing_buckets=_ageing_buckets(per_item, stock_aware),
        reorder_count=int(per_item["reorder_flag"].sum()),
        total_capital_locked=(
            safe_float(per_item["capital_locked"].sum()) if stock_aware else None
        ),
        note=(
            None
            if stock_aware
            else (
                "This file is a sales register only, so days-of-cover and locked capital "
                "can't be calculated. Map a stock column (Stock / Closing Stock / Balance Qty) "
                "on the column screen to unlock real reorder alerts."
            )
        ),
    )


# ── Aggregation ─────────────────────────────────────────────────────────────


def _aggregate_items(prepped: pd.DataFrame, stock_aware: bool) -> pd.DataFrame:
    """
    One row per item: totals, activity, average cost, and — in stock-aware
    mode — the most recently reported stock level.
    """
    aggregated = prepped.groupby("Item", as_index=False).agg(
        category=("Category", "first"),
        units=("Quantity", "sum"),
        revenue=("_row_revenue", "sum"),
        cost=("_row_cost", "sum"),
        profit=("_row_profit", "sum"),
        last_sale=("Date", "max"),
        active_days=("Date", lambda s: s.dt.date.nunique()),
        avg_cost=("Cost Price", "mean"),
    )

    if stock_aware:
        # Take the stock value from each item's newest row: an export usually
        # repeats the current stock on every line, and the latest row is the
        # closest thing to "now".
        latest = (
            prepped.sort_values("Date")
            .groupby("Item", as_index=False)
            .agg(stock_on_hand=("Stock On Hand", "last"))
        )
        aggregated = aggregated.merge(latest, on="Item", how="left")
        aggregated["stock_on_hand"] = aggregated["stock_on_hand"].fillna(0.0)

    return aggregated


def _trend_factors(prepped: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """
    Per-item late-window velocity ÷ early-window velocity.

    The window is split into thirds and the first third is compared with the
    last third; the middle is ignored deliberately, which makes the signal less
    twitchy on short windows. Items with no early sales but recent ones get the
    upper clamp (clearly accelerating); the reverse gets the lower clamp.
    """
    span_days = max(int((end - start).days) + 1, 1)
    third = max(span_days // 3, 1)
    early_end = start + pd.Timedelta(days=third)
    late_start = end - pd.Timedelta(days=third) + pd.Timedelta(days=1)

    early = prepped[prepped["Date"] < early_end].groupby("Item")["Quantity"].sum()
    late = prepped[prepped["Date"] >= late_start].groupby("Item")["Quantity"].sum()

    items = prepped.groupby("Item")["Quantity"].sum().index
    early_rate = (early.reindex(items).fillna(0.0) / third).astype(float)
    late_rate = (late.reindex(items).fillna(0.0) / third).astype(float)

    factors = pd.Series(1.0, index=items, dtype=float)
    both = (early_rate > 0) & (late_rate > 0)
    factors[both] = late_rate[both] / early_rate[both]
    factors[(early_rate == 0) & (late_rate > 0)] = TREND_CLAMP[1]
    factors[(early_rate > 0) & (late_rate == 0)] = TREND_CLAMP[0]
    # Returned keyed by item name so the caller aligns with ``.map`` rather
    # than relying on both frames happening to be in the same row order.
    return factors.clip(*TREND_CLAMP)


def _classify_abc(per_item: pd.DataFrame) -> pd.DataFrame:
    """
    Attach an A/B/C class by cumulative revenue share (Pareto classification —
    the standard way retailers decide what deserves attention).
    """
    out = per_item.sort_values("revenue", ascending=False).copy()
    total = float(out["revenue"].sum())
    if total <= 0:
        out["abc_class"] = "C"
        return out

    cumulative = out["revenue"].cumsum() / total
    out["abc_class"] = np.where(
        cumulative <= ABC_A_THRESHOLD, "A", np.where(cumulative <= ABC_B_THRESHOLD, "B", "C")
    )
    return out


def _ageing_bucket(days_idle: float) -> str:
    """Map days-since-last-sale onto a named bucket."""
    if pd.isna(days_idle):
        return "Dead"
    days = float(days_idle)
    if days < AGEING_FRESH_DAYS:
        return "Fresh"
    if days < AGEING_SLOW_DAYS:
        return "Slow"
    if days < AGEING_STALE_DAYS:
        return "Stale"
    return "Dead"


def _priority_scores(per_item: pd.DataFrame) -> pd.Series:
    """
    Blend velocity, trend and recency into a 0–100 reorder-priority score.

    Velocity is scaled against the fastest-moving item in the window, so the
    score answers "what should I buy first?" rather than being an absolute
    figure that only makes sense to a statistician.
    """
    velocity = per_item["velocity_per_day"].astype(float)
    max_velocity = float(velocity.max()) if len(velocity) else 0.0
    velocity_norm = velocity / max_velocity if max_velocity > 0 else velocity * 0.0

    # A trend factor of 1 (flat) sits mid-scale; the clamp keeps it in 0–1.
    trend_norm = ((per_item["trend_factor"].astype(float) - TREND_CLAMP[0]) /
                  (TREND_CLAMP[1] - TREND_CLAMP[0])).clip(0.0, 1.0)

    recency_norm = (
        1.0 - (per_item["days_since_last_sale"].astype(float) / RECENCY_HORIZON_DAYS)
    ).clip(0.0, 1.0)

    score = (
        WEIGHT_VELOCITY * velocity_norm
        + WEIGHT_TREND * trend_norm
        + WEIGHT_RECENCY * recency_norm
    ) * 100.0
    return score.round(1)


# ── Bucket summaries ────────────────────────────────────────────────────────


def _abc_buckets(per_item: pd.DataFrame, stock_aware: bool) -> list[InventoryBucket]:
    """Summarise the A/B/C classes for the three KPI tiles above the table."""
    total_revenue = float(per_item["revenue"].sum())
    buckets: list[InventoryBucket] = []
    labels = {
        "A": "A — top 80% of revenue",
        "B": "B — next 15%",
        "C": "C — long tail",
    }
    for cls in ("A", "B", "C"):
        rows = per_item[per_item["abc_class"] == cls]
        buckets.append(
            InventoryBucket(
                label=labels[cls],
                item_count=int(len(rows)),
                units=safe_int(rows["units"].sum()),
                revenue=safe_float(rows["revenue"].sum(), default=0.0) or 0.0,
                revenue_share_pct=safe_percentage(rows["revenue"].sum(), total_revenue),
                capital_locked=safe_float(rows["capital_locked"].sum()) if stock_aware else None,
            )
        )
    return buckets


def _ageing_buckets(per_item: pd.DataFrame, stock_aware: bool) -> list[InventoryBucket]:
    """Summarise the ageing buckets, newest first, skipping empty ones."""
    total_revenue = float(per_item["revenue"].sum())
    order = [
        ("Fresh", f"Fresh — sold within {AGEING_FRESH_DAYS} days"),
        ("Slow", f"Slow — {AGEING_FRESH_DAYS}–{AGEING_SLOW_DAYS - 1} days idle"),
        ("Stale", f"Stale — {AGEING_SLOW_DAYS}–{AGEING_STALE_DAYS - 1} days idle"),
        ("Dead", f"Dead — {AGEING_STALE_DAYS}+ days idle"),
    ]
    buckets: list[InventoryBucket] = []
    for key, label in order:
        rows = per_item[per_item["ageing_bucket"] == key]
        if rows.empty:
            continue
        buckets.append(
            InventoryBucket(
                label=label,
                item_count=int(len(rows)),
                units=safe_int(rows["units"].sum()),
                revenue=safe_float(rows["revenue"].sum(), default=0.0) or 0.0,
                revenue_share_pct=safe_percentage(rows["revenue"].sum(), total_revenue),
                capital_locked=safe_float(rows["capital_locked"].sum()) if stock_aware else None,
            )
        )
    return buckets


def _to_schema(row: pd.Series, stock_aware: bool) -> InventoryItem:
    """Convert one aggregated row into its JSON-safe response model."""
    return InventoryItem(
        item=str(row["Item"]),
        category=str(row["category"]),
        units_sold=safe_int(row["units"]),
        revenue=safe_float(row["revenue"], default=0.0) or 0.0,
        profit=safe_float(row["profit"], default=0.0) or 0.0,
        margin_pct=safe_percentage(row["profit"], row["revenue"]),
        velocity_per_day=safe_float(row["velocity_per_day"], digits=3, default=0.0) or 0.0,
        velocity_active=safe_float(row["velocity_active"], digits=3, default=0.0) or 0.0,
        active_days=safe_int(row["active_days"]),
        days_since_last_sale=safe_int(row["days_since_last_sale"]),
        trend_factor=safe_float(row["trend_factor"], default=1.0) or 1.0,
        abc_class=str(row["abc_class"]),
        ageing_bucket=str(row["ageing_bucket"]),
        reorder_priority=safe_float(row["reorder_priority"], digits=1, default=0.0) or 0.0,
        stock_on_hand=safe_float(row["stock_on_hand"]) if stock_aware else None,
        days_of_cover=safe_float(row["days_of_cover"], digits=1) if stock_aware else None,
        reorder_flag=bool(row["reorder_flag"]),
        capital_locked=safe_float(row["capital_locked"]) if stock_aware else None,
    )
