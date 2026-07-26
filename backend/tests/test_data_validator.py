"""
Tests for the column-mapping and validation layer.

Focus areas:
* real-world header aliases resolve to the right canonical field;
* ``Amount``-style columns become ``Line Total`` (the double-counting fix) and
  a unit price is derived from them;
* optional measures/dimensions survive normalisation, and unmapped columns are
  dropped;
* bad cells are reported without taking the whole file down.
"""

import pandas as pd
import pytest

from app.utils.data_validator import (
    OPTIONAL_DIMENSION_COLUMNS,
    available_dimensions,
    available_measures,
    detect_column_mapping,
    guess_canonical_column,
    normalize_dataframe,
)


@pytest.mark.parametrize(
    "header,expected",
    [
        # Tally / Vyapar / Marg / Busy style headers
        ("Voucher Date", "Date"),
        ("Bill Date", "Date"),
        ("Particulars", "Item"),
        ("Stock Group", "Category"),
        ("Qty.", "Quantity"),
        ("Billed Qty", "Quantity"),
        ("Rate/Unit", "Selling Price"),
        ("MRP", "Selling Price"),
        ("Purchase Rate", "Cost Price"),
        ("Landing Cost", "Cost Price"),
        # Line totals must NOT become a unit selling price
        ("Amount", "Line Total"),
        ("Net Amount", "Line Total"),
        ("Taxable Value", "Line Total"),
        ("Revenue", "Line Total"),
        # Optional measures and dimensions
        ("Discount", "Discount"),
        ("GST Amount", "Tax"),
        ("Closing Stock", "Stock On Hand"),
        ("Balance Qty", "Stock On Hand"),
        ("Store Name", "Branch"),
        ("Payment Method", "Payment Mode"),
        ("Salesman", "Salesperson"),
        ("Invoice No", "Invoice No"),
        ("Colour", "Colour"),
        # Marketplace exports
        ("Lineitem quantity", "Quantity"),
        ("quantity-purchased", "Quantity"),
        ("Ordered On", "Date"),
    ],
)
def test_header_aliases_resolve(header, expected):
    """Each real-world header maps to the field a shop owner would expect."""
    canonical, confidence = guess_canonical_column(header)
    assert canonical == expected, f"{header!r} → {canonical!r}, expected {expected!r}"
    assert confidence in ("exact", "fuzzy")


@pytest.mark.parametrize("header", ["Total Qty", "Purchase Qty"])
def test_quantity_wins_over_money_keywords(header):
    """"Total Qty" is a count, not a line total — keyword order must reflect that."""
    assert guess_canonical_column(header)[0] == "Quantity"


def test_discount_is_not_mistaken_for_count():
    """'discount' contains 'count'; the alias order must not turn it into Quantity."""
    assert guess_canonical_column("Discount")[0] == "Discount"


def test_unrelated_columns_get_no_guess():
    """Columns we don't understand are left alone rather than guessed at."""
    assert guess_canonical_column("Remarks")[0] is None
    assert guess_canonical_column("HSN")[0] is None


def test_duplicate_suggestions_are_downgraded():
    """
    When two raw columns look like the same field, only the first keeps the
    suggestion so the user has to choose explicitly.
    """
    frame = pd.DataFrame(columns=["Rate", "MRP", "Item", "Date", "Qty", "Cost"])
    report = {row["raw_column"]: row["suggested_field"] for row in detect_column_mapping(frame)}
    assert report["Rate"] == "Selling Price"
    assert report["MRP"] is None


def test_line_total_derives_unit_price():
    """
    A file with a line total and no unit rate must produce
    ``Selling Price = Amount / Quantity`` — otherwise revenue is multiplied by
    the quantity twice.
    """
    raw = pd.DataFrame(
        {
            "Date": ["01-02-2026", "02-02-2026"],
            "Category": ["Kurta", "Kurta"],
            "Item": ["A", "B"],
            "Qty": [4, 5],
            "Amount": [2000.0, 1000.0],  # line totals
            "Cost": [300.0, 100.0],
        }
    )
    frame, errors = normalize_dataframe(raw)

    assert list(frame["Selling Price"]) == [500.0, 200.0]
    # Revenue must equal the line total, not quantity × line total.
    assert (frame["Quantity"] * frame["Selling Price"]).tolist() == [2000.0, 1000.0]
    assert errors == []


def test_optional_fields_are_kept_and_unmapped_dropped(normalized):
    """Mapped optional columns survive; the 'Remarks' column does not."""
    assert "Branch" in normalized.columns
    assert "Payment Mode" in normalized.columns
    assert "Discount" in normalized.columns
    assert "Stock On Hand" in normalized.columns
    assert "Remarks" not in normalized.columns

    assert "Branch" in available_dimensions(normalized)
    assert "Stock On Hand" in available_measures(normalized)


def test_blank_optional_dimension_becomes_unspecified():
    """A blank branch must not silently drop the row from branch breakdowns."""
    raw = pd.DataFrame(
        {
            "Date": ["01-02-2026", "02-02-2026"],
            "Category": ["Kurta", "Kurta"],
            "Item": ["A", "B"],
            "Quantity": [1, 2],
            "Selling Price": [100.0, 200.0],
            "Cost Price": [50.0, 90.0],
            "Branch": ["MG Road", ""],
        }
    )
    frame, _errors = normalize_dataframe(raw)
    assert sorted(frame["Branch"].tolist()) == ["MG Road", "Unspecified"]
    assert len(frame) == 2


def test_currency_symbols_and_indian_dates_are_parsed():
    """'₹ 1,299.00' and '15-03-2026' are normal values in these exports."""
    raw = pd.DataFrame(
        {
            "Date": ["15-03-2026"],
            "Category": ["Saree"],
            "Item": ["Silk"],
            "Quantity": ["3"],
            "Selling Price": ["₹ 1,299.00"],
            "Cost Price": ["800"],
        }
    )
    frame, errors = normalize_dataframe(raw)
    assert errors == []
    assert frame.iloc[0]["Selling Price"] == 1299.0
    assert frame.iloc[0]["Date"] == pd.Timestamp("2026-03-15")


def test_line_total_with_currency_symbols_still_derives_a_unit_price():
    """
    A GST register writes its line total as "₹ 12,345.00". The derivation has to
    strip the symbol before dividing — cleaning only inside the main coercion
    loop meant such a file produced *zero* analysable rows.
    """
    raw = pd.DataFrame(
        {
            "Bill Date": ["01/02/2026", "02/02/2026"],
            "Item Group": ["Pulses", "Grains"],
            "Item Name": ["Toor Dal 1kg", "Basmati Rice 5kg"],
            "Billed Qty": [10, 4],
            "Taxable Value": ["₹ 1,490.00", "₹ 2,396.00"],
            "Purchase Rate": ["118.00", "460.00"],
        }
    )
    frame, errors = normalize_dataframe(raw)

    assert len(frame) == 2, errors
    assert frame["Selling Price"].tolist() == [149.0, 599.0]
    # Revenue must equal the line totals, not quantity × line total.
    assert (frame["Quantity"] * frame["Selling Price"]).tolist() == [1490.0, 2396.0]


def test_iso_dates_are_not_scrambled_by_dayfirst():
    """
    ``dayfirst=True`` silently rereads an ISO date whose day is ≤ 12, which
    turned a 100-day marketplace export into a 337-day span and made every
    trading day look sparse. ISO must be parsed as ISO.
    """
    raw = pd.DataFrame(
        {
            "Ordered On": ["2026-03-10", "2026-04-05", "2026-05-12", "2026-06-30"],
            "Product type": ["Audio"] * 4,
            "Lineitem name": ["Speaker"] * 4,
            "Lineitem quantity": [1, 2, 3, 4],
            "Lineitem price": [2499.0] * 4,
            "Unit Cost": [1450.0] * 4,
        }
    )
    frame, _errors = normalize_dataframe(
        raw,
        column_mapping={
            "Ordered On": "Date",
            "Product type": "Category",
            "Lineitem name": "Item",
            "Lineitem quantity": "Quantity",
            "Lineitem price": "Selling Price",
            "Unit Cost": "Cost Price",
        },
    )

    assert frame["Date"].tolist() == [
        pd.Timestamp("2026-03-10"),
        pd.Timestamp("2026-04-05"),
        pd.Timestamp("2026-05-12"),
        pd.Timestamp("2026-06-30"),
    ]
    span = (frame["Date"].max() - frame["Date"].min()).days
    assert span == 112, f"ISO dates were re-ordered: span came out as {span} days"


def test_indian_and_iso_dates_can_coexist_in_one_column():
    """A file assembled from two systems must not lose either half."""
    raw = pd.DataFrame(
        {
            "Date": ["15-03-2026", "2026-03-16", "17/03/2026"],
            "Category": ["Kurta"] * 3,
            "Item": ["Cotton Kurta"] * 3,
            "Quantity": [1, 1, 1],
            "Selling Price": [799.0] * 3,
            "Cost Price": [320.0] * 3,
        }
    )
    frame, errors = normalize_dataframe(raw)

    assert errors == []
    assert frame["Date"].dt.day.tolist() == [15, 16, 17]
    assert frame["Date"].dt.month.tolist() == [3, 3, 3]


@pytest.mark.parametrize("header", ["Section", "Menu Group", "Course", "Kitchen Group"])
def test_food_service_category_headers(header):
    """Restaurant POS exports call the category a section or a menu group."""
    assert guess_canonical_column(header)[0] == "Category"


def test_bad_rows_are_reported_not_fatal():
    """One unusable row must not stop the other rows from being analysed."""
    raw = pd.DataFrame(
        {
            "Date": ["01-02-2026", "not-a-date", "03-02-2026"],
            "Category": ["Kurta", "Kurta", ""],
            "Item": ["A", "B", "C"],
            "Quantity": [2, 3, 1],
            "Selling Price": [100.0, 200.0, 300.0],
            "Cost Price": [50.0, 90.0, 100.0],
        }
    )
    frame, errors = normalize_dataframe(raw)
    assert len(frame) == 1
    columns_with_errors = {e["column"] for e in errors}
    assert "Date" in columns_with_errors
    assert "Category" in columns_with_errors


def test_business_rules_remove_impossible_rows():
    """Zero/negative quantities and negative prices are physically impossible."""
    raw = pd.DataFrame(
        {
            "Date": ["01-02-2026"] * 3,
            "Category": ["Kurta"] * 3,
            "Item": ["A", "B", "C"],
            "Quantity": [0, 2, 1],
            "Selling Price": [100.0, -5.0, 300.0],
            "Cost Price": [50.0, 90.0, 100.0],
        }
    )
    frame, errors = normalize_dataframe(raw)
    assert frame["Item"].tolist() == ["C"]
    assert any("greater than zero" in e["error"] for e in errors)
    assert any("cannot be negative" in e["error"] for e in errors)


def test_selling_below_cost_is_allowed():
    """Clearance sales are legitimate; the margin-leak insight needs those rows."""
    raw = pd.DataFrame(
        {
            "Date": ["01-02-2026"],
            "Category": ["Kurta"],
            "Item": ["Clearance"],
            "Quantity": [1],
            "Selling Price": [100.0],
            "Cost Price": [180.0],
        }
    )
    frame, errors = normalize_dataframe(raw)
    assert len(frame) == 1
    assert errors == []


def test_soft_fail_returns_schema_error_instead_of_raising():
    """The upload endpoint needs a structured answer, never a 500."""
    raw = pd.DataFrame({"Foo": [1], "Bar": [2]})
    frame, errors = normalize_dataframe(raw, soft_fail=True)
    assert frame.empty
    assert errors and errors[0]["column"] == "schema"

    with pytest.raises(ValueError):
        normalize_dataframe(raw, soft_fail=False)


def test_mapping_ignores_unknown_target_fields():
    """A mapping value that isn't a canonical field must be ignored, not trusted."""
    raw = pd.DataFrame(
        {
            "d": ["01-02-2026"],
            "c": ["Kurta"],
            "i": ["A"],
            "q": [1],
            "s": [100.0],
            "k": [40.0],
            "junk": ["x"],
        }
    )
    frame, _errors = normalize_dataframe(
        raw,
        column_mapping={
            "d": "Date",
            "c": "Category",
            "i": "Item",
            "q": "Quantity",
            "s": "Selling Price",
            "k": "Cost Price",
            "junk": "__proto__",
        },
    )
    assert "__proto__" not in frame.columns
    assert len(frame) == 1


def test_all_optional_dimensions_are_recognised():
    """Every optional dimension must have at least one working alias."""
    aliases = {
        "Branch": "Store",
        "Payment Mode": "Payment Mode",
        "Customer": "Party Name",
        "Salesperson": "Salesman",
        "Brand": "Brand",
        "Size": "Size",
        "Colour": "Color",
        "Invoice No": "Bill No",
    }
    assert set(aliases) == OPTIONAL_DIMENSION_COLUMNS
    for field, header in aliases.items():
        assert guess_canonical_column(header)[0] == field
