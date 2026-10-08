"""C2 filter-window and cascading regression tests."""

from pathlib import Path

import pandas as pd
import pytest

from app.services import query_engine


FIXTURE = Path(__file__).resolve().parents[2] / "testing2" / "03_electronics_shopify_orders.csv"


@pytest.fixture(scope="module")
def electronics():
    raw = pd.read_csv(FIXTURE)
    frame = raw.rename(
        columns={
            "Ordered On": "Date",
            "Product type": "Category",
            "Lineitem name": "Item",
            "Lineitem quantity": "Quantity",
            "Lineitem price": "Selling Price",
            "Unit Cost": "Cost Price",
            "Payment Method": "Payment Mode",
            "Order ID": "Invoice No",
        }
    ).copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame["Discount"] = 0.0
    return frame


def money_totals(rows):
    revenue = float((rows["Quantity"] * rows["Selling Price"] - rows["Discount"]).sum())
    cost = float((rows["Quantity"] * rows["Cost Price"]).sum())
    profit = revenue - cost
    return len(rows), revenue, cost, profit, int(rows["Quantity"].sum())


def test_latest_day_uses_file_max_date(electronics):
    current, _previous, window = query_engine.build_slice(electronics, "today")
    assert window.end == pd.Timestamp("2026-06-18")
    assert money_totals(current) == (7, 49180.0, 29430.0, 19750.0, 20)


def test_latest_day_plus_category_power(electronics):
    current, _previous, _window = query_engine.build_slice(
        electronics, "today", filters={"category": ["Power"]}
    )
    assert money_totals(current) == (2, 13893.0, 8340.0, 5553.0, 7)


def test_custom_power_range_keeps_exact_expected_numbers(electronics):
    current, _previous, window = query_engine.build_slice(
        electronics,
        "custom",
        start_date=pd.Timestamp("2026-03-19").date(),
        end_date=pd.Timestamp("2026-04-17").date(),
        filters={"category": ["Power"]},
    )
    assert window.start == pd.Timestamp("2026-03-19")
    assert window.end == pd.Timestamp("2026-04-18")
    assert money_totals(current) == (60, 510327.0, 301950.0, 208377.0, 273)


def test_custom_range_clamps_to_file_span(electronics):
    current, _previous, window = query_engine.build_slice(
        electronics,
        "custom",
        start_date=pd.Timestamp("2026-02-01").date(),
        end_date=pd.Timestamp("2026-07-31").date(),
    )
    assert window.start == pd.Timestamp("2026-03-10")
    assert window.end == pd.Timestamp("2026-06-18")
    assert len(current) == len(electronics)


def test_custom_range_rejects_reversed_dates(electronics):
    with pytest.raises(query_engine.QueryError, match="on or before"):
        query_engine.build_slice(
            electronics,
            "custom",
            start_date=pd.Timestamp("2026-04-17").date(),
            end_date=pd.Timestamp("2026-03-19").date(),
        )


def test_item_options_cascade_from_category(electronics):
    power_items = query_engine.dimension_option(
        electronics,
        "item",
        filters={"category": ["Power"]},
        time_filter="all",
    )
    assert set(power_items.values) == {
        value for value in electronics.loc[electronics["Category"] == "Power", "Item"].astype(str).unique()
    }


def test_category_options_cascade_from_item(electronics):
    item = str(electronics.iloc[0]["Item"])
    categories = query_engine.dimension_option(
        electronics,
        "category",
        filters={"item": [item]},
        time_filter="all",
    )
    assert categories.values == sorted(electronics.loc[electronics["Item"].astype(str) == item, "Category"].astype(str).unique().tolist())


def test_invoice_search_is_case_insensitive_and_server_side(electronics):
    result = query_engine.dimension_option(
        electronics,
        "invoice_no",
        filters={},
        time_filter="all",
        search="90002",
        limit=10,
    )
    assert result.values == ["#90002"]
    assert result.total == electronics["Invoice No"].astype(str).nunique()
