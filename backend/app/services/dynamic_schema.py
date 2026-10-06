"""
Dynamic schema — what this particular file can be asked.

Why this exists
---------------
The dashboard was written against a fixed idea of what a sales file contains:
cards for revenue, profit, units, top items, a daily trend. That assumption is
wrong for most of the shops this is built for. A file with no ``Cost Price``
cannot show a profit card. A file with no ``Branch`` cannot break down by store.
A file with ``Stock On Hand`` can show days-of-cover, which another cannot.

Before this module the answer to "what can I show for this file?" lived only in
the shape of the dashboard: a card silently failed to render, or rendered a
zero, and the shopkeeper had no way to tell whether that meant "zero" or "we
can't know that from your file". Missing and zero look identical, which is the
worst possible thing for a number on a business dashboard.

So this module answers the question explicitly and up front. For every card,
chart, dimension and measure it reports **whether it is available and why not
if it isn't**.

The distinction that drives the design
--------------------------------------
Entries are *flagged*, never omitted. An empty list tells the user nothing about
why nothing appeared. ``{"available": false, "reason": "Map Cost Price on the
mapping screen to unlock profit and margin"}`` tells them exactly one action that
would fix it. This is why ``SchemaEntry.available`` defaults to ``False``: a
caller that forgets to set it produces an honest "not available" rather than a
promised card with no data behind it.

This module never computes a business number
--------------------------------------------
It reports *availability*, derived from which columns exist. Every actual figure
still comes from ``sales_calculations`` / ``query_engine`` via the existing
endpoints. Keeping the split sharp means the schema panel cannot disagree with
the dashboard: if the panel says a card is available, the existing endpoint
behind that card has the columns it needs.
"""

from __future__ import annotations

import pandas as pd

from app.services.query_engine import (
    DIMENSIONS,
    MEASURES,
    TIME_DIMENSIONS,
    available_dimensions,
    available_measures,
)
from app.services.sales_calculations import compute_data_date_range
from app.utils.data_validator import REQUIRED_COLUMNS

# ── KPI cards ────────────────────────────────────────────────────────────────
#
# ``requires`` is the set of canonical columns a card cannot be computed without.
# ``dimensions_required`` is an *alternative* set: a card can be computed from
# any one of them, because a sales total doesn't care whether the shop filed it
# under Branch or Store.
#
# ``blocks`` propagates: losing Cost Price doesn't just hide the profit card, it
# also invalidates margin, the P&L and the profit trend. Listing the damage
# explicitly is what lets the UI explain a cascade instead of just hiding things.

_KPI_CARDS: list[dict] = [
    {
        "key": "revenue",
        "label": "Revenue",
        "description": "Gross sales value across the selected period.",
        "requires": set(),
        "formats": ["currency"],
    },
    {
        "key": "profit",
        "label": "Profit",
        "description": "Revenue minus cost of goods sold.",
        "requires": {"Cost Price"},
        "blocks": ["margin_pct", "pnl"],
        "formats": ["currency"],
    },
    {
        "key": "margin_pct",
        "label": "Margin",
        "description": "Profit as a percentage of revenue.",
        "requires": {"Cost Price"},
        "formats": ["percent"],
    },
    {
        "key": "units",
        "label": "Units Sold",
        "description": "Total pieces sold across the period.",
        "requires": {"Quantity"},
        "formats": ["number"],
    },
    {
        "key": "transactions",
        "label": "Transactions",
        "description": "Number of separate lines or bills in the file.",
        "requires": set(),
        "formats": ["number"],
    },
    {
        "key": "discount",
        "label": "Discount Given",
        "description": "Total discount offered. Revenue is reported net of this.",
        "requires": {"Discount"},
        "formats": ["currency"],
    },
    {
        "key": "discount_pct",
        "label": "Discount %",
        "description": "Discount as a percentage of total MRP.",
        "requires": {"MRP"},
        "formats": ["percent"],
    },
    {
        "key": "stock_on_hand",
        "label": "Stock On Hand",
        "description": "Closing stock. Unlocks days-of-cover and reorder alerts.",
        "requires": {"Stock On Hand"},
        "formats": ["number"],
    },
    {
        "key": "days_of_cover",
        "label": "Days of Cover",
        "description": "How many days of selling the current stock lasts.",
        "requires": {"Stock On Hand"},
        "formats": ["number"],
    },
]

# ── Charts ───────────────────────────────────────────────────────────────────
#
# Charts are flagged for a second reason beyond missing columns: a chart needs a
# dimension to be meaningful. A revenue-by-branch chart on a file with one branch
# is a single bar and tells the shopkeeper nothing, so ``min_categories`` exists
# to say so honestly rather than render a lonely rectangle.

_CHARTS: list[dict] = [
    {
        "key": "daily_trend",
        "label": "Daily Trend",
        "description": "Revenue and profit by day, with anomaly days marked.",
        "requires": set(),
        "dimension_any_of": {"Date"},
        "min_categories": 2,
    },
    {
        "key": "revenue_by_category",
        "label": "Sales by Category",
        "description": "Revenue split across product groups.",
        "requires": {"Category"},
        "dimension_any_of": set(),
        "min_categories": 2,
    },
    {
        "key": "top_items",
        "label": "Top Items",
        "description": "Fastest-moving items by units and revenue.",
        "requires": {"Item"},
        "dimension_any_of": set(),
        "min_categories": 2,
    },
    {
        "key": "revenue_by_branch",
        "label": "Sales by Branch",
        "description": "Revenue and profit per shop or store.",
        "requires": {"Branch"},
        "dimension_any_of": set(),
        "min_categories": 2,
    },
    {
        "key": "payment_mode_split",
        "label": "Payment Mode Split",
        "description": "How customers paid: cash, UPI, card.",
        "requires": {"Payment Mode"},
        "dimension_any_of": set(),
        "min_categories": 2,
    },
    {
        "key": "weekday_heatmap",
        "label": "Weekday Intensity",
        "description": "Weekday by week grid — finds the shop's busy days.",
        "requires": set(),
        "dimension_any_of": {"Date"},
        "min_categories": 14,
    },
    {
        "key": "pnl",
        "label": "P&L Statement",
        "description": "Revenue, cost, profit and tax for the period.",
        "requires": {"Cost Price"},
        "dimension_any_of": set(),
        "min_categories": 0,
    },
    {
        "key": "discount_vs_margin",
        "label": "Discount vs Margin",
        "description": "Item-wise comparison of discount depth vs profit margin.",
        "requires": {"MRP", "Cost Price"},
        "dimension_any_of": {"Item"},
        "min_categories": 1,
    },
]


#: Canonical columns each API measure cannot be computed without. This is the
#: bridge between ``MEASURES`` (which is keyed for the chart API, not for columns)
#: and the normalised frame. Without it, ``revenue`` would be reported unavailable
#: on a perfectly good file, because "Revenue" is not a column — it is computed.
_MEASURE_REQUIRES: dict[str, set[str]] = {
    "revenue": set(),
    "profit": {"Cost Price"},
    "cost": {"Cost Price"},
    "units": {"Quantity"},
    "transactions": set(),
    "discount": {"Discount"},
    "margin_pct": {"Cost Price"},
    "avg_price": {"Quantity"},
}


#: Why everything is unavailable for a file with columns but no rows. Kept as one
#: constant so the wording cannot drift between cards and charts.
_NO_ROWS_REASON = "This file has no sales rows in it yet."


def _missing(present: set[str], required: set[str]) -> list[str]:
    """Canonical columns in ``required`` that this file does not have."""
    return sorted(required - present)


def _reason_for(missing: list[str], min_categories: int, distinct: int | None) -> str | None:
    """
    One sentence telling the user why something is unavailable, or ``None`` if it is.

    Missing columns come first because that is the actionable case: it names the
    exact field to map. A chart that is available but has too little data gets a
    different sentence, because the fix is different — there is nothing to map,
    the file is just small.
    """
    if missing:
        noun = "field" if len(missing) == 1 else "fields"
        return f"Map {', '.join(missing)} on the column mapping screen to unlock this {noun}."
    if distinct is not None and distinct < min_categories:
        return (
            f"Not enough data in this file yet — it needs at least "
            f"{min_categories} distinct {'values' if min_categories != 1 else 'value'}, "
            f"and has {distinct}."
        )
    return None


def build(frame: pd.DataFrame, mapping: dict[str, str] | None = None) -> dict:
    """
    Describe what ``frame`` supports.

    ``mapping`` is the confirmed ``{raw_column: canonical_field}``. It is used to
    explain *why* a column is missing when the user has mapped it but the data
    did not survive validation — a column can be mapped and still be absent from
    the normalised frame, and without this the UI would tell someone to remap a
    column they had already mapped.

    Returns a plain dict matching ``DynamicSchema``. Never raises: a schema panel
    that breaks the dashboard is worse than one that under-reports.
    """
    present = set(frame.columns)

    # A frame with no rows can produce no business number at all, whatever columns
    # it happens to carry. Cards like revenue need no columns, so a column-presence
    # check alone would report them available and the dashboard would show a
    # confident ₹0 for a file we have actually read nothing from. Absence of rows is
    # therefore its own reason, distinct from absence of columns.
    has_rows = len(frame) > 0

    kpi_cards = [_kpi_entry(card, present) for card in _KPI_CARDS]
    charts = [_chart_entry(chart, frame, present) for chart in _CHARTS]

    # ``available_dimensions`` returns canonical *column* names while ``DIMENSIONS``
    # is keyed by API keys, so availability is resolved through the registry's own
    # ``column`` field rather than by comparing the two namespaces directly.
    present_dimension_columns = set(available_dimensions(frame))

    dimensions = []
    for key, meta in DIMENSIONS.items():
        column = meta["column"]
        # Time dimensions (day/weekday/month) are derived from Date, not columns,
        # so they are available exactly when Date is.
        available = key in TIME_DIMENSIONS or column in present_dimension_columns
        dimensions.append(
            {
                "key": key,
                "label": meta["label"],
                "available": available,
                "column": column,
                "reason": (
                    None
                    if available
                    else f"Map {column} on the column mapping screen to slice by {meta['label'].lower()}."
                ),
            }
        )

    # ``available_measures`` reports canonical *column* names (Discount, Tax, …),
    # while ``MEASURES`` is keyed by API measure keys (discount, margin_pct, …).
    # Translating once here keeps the response in measure keys, which is what the
    # chart studio already speaks — mixing the two would produce a panel where
    # "Discount Given" is available but keyed under a column name no request uses.
    present_measure_columns = set(available_measures(frame))

    measures = []
    for key, meta in MEASURES.items():
        required = _MEASURE_REQUIRES[key]
        missing = _missing(present_measure_columns | present, required)
        
        if key == "discount" and "Discount" in missing:
            if "MRP" in (present_measure_columns | present):
                missing = []
                
        available = not missing
        measures.append(
            {
                "key": key,
                "label": meta["label"],
                "available": available,
                "format": meta["format"],
                "additive": bool(meta["additive"]),
                "reason": None if available else _reason_for(missing, 0, None),
                "blocked_by": [] if available else list(missing),
            }
        )

    missing_required = _missing(present, REQUIRED_COLUMNS)

    date_range: dict = {}
    if "Date" in present:
        try:
            date_range = compute_data_date_range(frame)
        except Exception:  # a bad date column must not blank the whole panel
            date_range = {}

    return {
        "kpi_cards": _sorted_by_availability(_kpi_entry(c, present, has_rows) for c in _KPI_CARDS),
        # Sorted so the panel reads as: what works now, then what could work.
        # A shopkeeper opening this is asking "what can I do?", and an unsorted
        # list of mostly-unavailable entries buries the answer.
        "charts": _sorted_by_availability(_chart_entry(c, frame, present, has_rows) for c in _CHARTS),
        "dimensions": _sorted_by_availability(dimensions),
        "measures": _sorted_by_availability(measures),
        "mapped_columns": dict(mapping or {}),
        "present_columns": sorted(present),
        "missing_required_columns": missing_required,
        "date_range": date_range,
    }


def _sorted_by_availability(entries) -> list[dict]:
    """
    Stable-sort entries so available ones come first, preserving registry order
    within each group.

    ``sorted`` is stable, so this does not reshuffle the curated order the
    registry defines — a file with everything available still sees the panels in
    the order a shopkeeper would expect to read them.
    """
    return sorted(entries, key=lambda entry: not entry["available"])


def _kpi_entry(card: dict, present: set[str], has_rows: bool = True) -> dict:
    """One KPI card, flagged available or not, with the reason when it isn't."""
    missing = _missing(present, card["requires"])
    
    if card["key"] == "discount" and "Discount" in missing:
        if "MRP" in present:
            missing = []
            
    available = not missing and has_rows
    reason = None
    if not available:
        # Rows first: "this file has no sales in it" is the fact, and telling
        # someone to map a column they already mapped would send them in circles.
        reason = (
            _NO_ROWS_REASON
            if not has_rows
            else _reason_for(missing, 0, None)
        )
    return {
        "key": card["key"],
        "label": card["label"],
        "description": card["description"],
        "available": available,
        "reason": reason,
        "formats": list(card["formats"]),
        "blocked_by": [] if available else list(missing),
        # A card that needs Cost Price also takes margin, the profit trend and the
        # P&L down with it. Listing the cascade explicitly lets the UI explain
        # why several things went missing at once, instead of hiding them silently.
        "blocks": list(card.get("blocks", [])) if not available else [],
    }


def _chart_entry(chart: dict, frame: pd.DataFrame, present: set[str], has_rows: bool = True) -> dict:
    """
    One chart, flagged available or not.

    Availability has three independent failure modes — a missing column, too few
    distinct values to make a chart worth drawing, and no rows at all — so each is
    checked and reported separately rather than collapsed into one flag.
    """
    required = set(chart["requires"]) | set(chart.get("dimension_any_of", set()))
    missing = _missing(present, required)

    distinct: int | None = None
    candidates = chart.get("dimension_any_of") or chart["requires"]
    for candidate in sorted(candidates):
        if candidate in present:
            distinct = int(frame[candidate].nunique())
            break

    reason = _reason_for(missing, chart.get("min_categories", 0), distinct)
    if reason is None and not has_rows:
        reason = _NO_ROWS_REASON
    available = reason is None

    return {
        "key": chart["key"],
        "label": chart["label"],
        "description": chart["description"],
        "available": available,
        "reason": reason,
        "distinct_values": distinct,
        "min_categories": chart.get("min_categories", 0),
    }
