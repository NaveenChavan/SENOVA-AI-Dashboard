"""
Shared pytest fixtures.

The synthetic shop
------------------
``raw_sales_frame`` builds a believable 90-day garment-shop export: three
categories, six items, a weekend uplift, a deliberate revenue collapse on one
known day, one item priced below cost (a margin leak), one item that stops
selling early (dead stock), and the optional Branch / Payment Mode / Discount /
Stock columns so the optional-field paths get exercised too.

Everything is generated from a fixed seed, so every assertion in the suite is
reproducible rather than "usually true".
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make ``app.*`` importable when pytest is run from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: The day (index from the start of the series) whose revenue is crushed, so the
#: anomaly test has a known target instead of hunting for whatever looks odd.
ANOMALY_DAY_INDEX = 60

#: Item deliberately sold below cost, for the margin-leak test.
LEAK_ITEM = "Clearance Kurta"

#: Item that stops selling after the first two weeks, for the dead-stock test.
DEAD_ITEM = "Winter Shawl"


@pytest.fixture
def raw_sales_frame() -> pd.DataFrame:
    """A raw, un-normalised export using real-world-style column headers."""
    rng = np.random.default_rng(seed=42)
    start = pd.Timestamp("2026-01-01")

    catalogue = [
        # (item, category, cost, price, base units per day)
        ("Cotton Kurta", "Kurta", 300.0, 750.0, 6),
        ("Silk Saree", "Saree", 1800.0, 3200.0, 2),
        ("Formal Shirt", "Shirt", 420.0, 900.0, 4),
        ("Denim Jeans", "Jeans", 700.0, 1500.0, 3),
        (LEAK_ITEM, "Kurta", 800.0, 820.0, 5),
        (DEAD_ITEM, "Shawl", 900.0, 1600.0, 2),
    ]

    rows: list[dict] = []
    for day_offset in range(90):
        day = start + pd.Timedelta(days=day_offset)
        # Weekends sell better — gives the weekday insight something real to find.
        weekend_uplift = 1.6 if day.dayofweek >= 5 else 1.0
        # One catastrophic day, used by the anomaly test.
        shock = 0.05 if day_offset == ANOMALY_DAY_INDEX else 1.0

        for item, category, cost, price, base_units in catalogue:
            # The dead-stock item disappears from the register after two weeks.
            if item == DEAD_ITEM and day_offset > 14:
                continue

            units = int(round(base_units * weekend_uplift * shock * rng.uniform(0.6, 1.4)))
            if units <= 0:
                continue

            rows.append(
                {
                    "Bill Date": day.strftime("%d-%m-%Y"),  # Indian DD-MM-YYYY
                    "Item Name": item,
                    "Stock Group": category,
                    "Qty.": units,
                    "Rate/Unit": price,
                    "Purchase Rate": cost,
                    "Discount": round(price * units * 0.02, 2),
                    "Store": "MG Road" if day_offset % 2 == 0 else "Station Road",
                    "Payment Mode": "UPI" if units % 2 == 0 else "Cash",
                    "Closing Stock": 40,
                    "Remarks": "ignore me",  # unmapped column: must be dropped
                }
            )

    return pd.DataFrame(rows)


@pytest.fixture
def mapping() -> dict[str, str]:
    """The confirmed column mapping a user would produce for that export."""
    return {
        "Bill Date": "Date",
        "Item Name": "Item",
        "Stock Group": "Category",
        "Qty.": "Quantity",
        "Rate/Unit": "Selling Price",
        "Purchase Rate": "Cost Price",
        "Discount": "Discount",
        "Store": "Branch",
        "Payment Mode": "Payment Mode",
        "Closing Stock": "Stock On Hand",
    }


@pytest.fixture
def normalized(raw_sales_frame, mapping) -> pd.DataFrame:
    """The validated frame every calculation module expects as input."""
    from app.utils.data_validator import normalize_dataframe

    frame, _errors = normalize_dataframe(raw_sales_frame, column_mapping=mapping)
    return frame


@pytest.fixture
def short_frame(normalized) -> pd.DataFrame:
    """Only the first 5 days — used to prove the "refuse to guess" paths."""
    cutoff = normalized["Date"].min() + pd.Timedelta(days=4)
    return normalized[normalized["Date"] <= cutoff].copy()
