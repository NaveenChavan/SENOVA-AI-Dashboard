"""
Module 2.1 — Deterministic Evidence Rules Engine tests.

Coverage
--------
Every rule family in ambiguity_engine.py is exercised:

  1. Percentage columns (GST slab detection, discount %, non-numeric)
  2. Amount / Total columns (invoice-repeat guard, Qty×SP≈Total, no-context fallback)
  3. Rate / Price columns (Qty×Rate≈Total, invoice-repeat, GST slab, fallback)
  4. Name-column disambiguation (customer context, item context, both, neither)
  5. Auxiliary date columns (stored-only verdict)
  6. evaluate_batch() accumulation semantics
  7. Edge cases (empty series, too-few rows, engine never raises)
  8. Integration smoke test via column_understanding.analyse()

Phase 1 regression guard
------------------------
The existing Phase 1 upload paths (Path A: Date+LineTotal, Path B: Date+Qty+SP)
are NOT broken by the engine.  Both paths produce zero needs_review rows that the
engine incorrectly alters, and every financial calculation remains identical.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
import pytest

from app.services.ambiguity_engine import (
    EvidenceResult,
    GST_SLAB_COVERAGE,
    INVOICE_REPEAT_THRESHOLD,
    MIN_ROWS_FOR_EVIDENCE,
    UNIT_PRICE_MATCH_THRESHOLD,
    _check_invoice_repeat,
    _check_product_match,
    _is_amount_like,
    _is_auxiliary_date_like,
    _is_name_like,
    _is_rate_like,
    evaluate,
    evaluate_batch,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _series(*values, name: str = "col") -> pd.Series:
    return pd.Series(list(values), name=name, dtype=object)


def _df(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def _auto(result: EvidenceResult) -> None:
    assert result.decision == "auto", (
        f"Expected decision='auto', got {result.decision!r}: {result.reason}"
    )


def _ask(result: EvidenceResult) -> None:
    assert result.decision in {"ask", "conflict"}, (
        f"Expected decision='ask'|'conflict', got {result.decision!r}: {result.reason}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rule family 1: Percentage / rate columns
# ─────────────────────────────────────────────────────────────────────────────

class TestPercentageColumns:
    """Rule family 1 — columns whose header contains %, pct, gst, etc."""

    def _run(self, header: str, values: list, **extra_cols) -> EvidenceResult:
        series = _series(*values, name=header)
        df = _df(**{header: values, **extra_cols})
        return evaluate(header, series, df, set())

    def test_gst_18_pct_resolved_as_tax(self):
        """Pure 18% GST column → canonical=Tax, decision=auto."""
        result = self._run("GST %", [18, 18, 12, 18, 18, 5, 18, 18, 18, 12])
        _auto(result)
        assert result.canonical == "Tax"
        assert result.semantic == "tax"
        assert result.confidence >= GST_SLAB_COVERAGE

    def test_gst_decimal_form_resolved_as_tax(self):
        """GST stored as decimal fractions (0.18, 0.12, …) → canonical=Tax."""
        result = self._run("Tax Rate", [0.18] * 8 + [0.12, 0.05])
        _auto(result)
        assert result.canonical == "Tax"

    def test_gst_mixed_slabs_still_resolves(self):
        """All values from the slab set, across multiple slabs → Tax."""
        result = self._run("GST", [0, 5, 12, 18, 28, 5, 12, 18, 0, 5])
        _auto(result)
        assert result.canonical == "Tax"

    def test_non_slab_percentage_asks(self):
        """Values in 0–100 but not slab-shaped → ask with Discount/Tax candidates."""
        result = self._run("Discount %", [10.5, 7.2, 15.0, 9.0, 8.0, 12.5, 11.0, 6.0, 14.0, 10.0])
        _ask(result)
        assert "Discount" in result.candidates or "Tax" in result.candidates

    def test_non_numeric_pct_header_asks(self):
        """Non-numeric values under a %-labelled header → ask."""
        result = self._run("Rate %", ["High", "Low", "Medium", "High", "High", "Low", "Medium", "High", "Low", "High"])
        _ask(result)

    def test_vat_column_resolved_as_tax(self):
        """Header 'VAT' with slab values → Tax."""
        result = self._run("VAT", [12, 12, 5, 18, 12, 12, 5, 18, 12, 12])
        _auto(result)
        assert result.canonical == "Tax"

    def test_evidence_listed_in_result(self):
        """Auto-resolved tax columns should list evidence bullets."""
        result = self._run("GST %", [18] * 10)
        _auto(result)
        assert len(result.evidence) >= 1

    def test_too_few_rows_asks(self):
        """Fewer than MIN_ROWS_FOR_EVIDENCE rows → always ask."""
        result = self._run("GST %", [18, 12])   # only 2 rows
        assert result.decision in {"ask", "conflict"}


# ─────────────────────────────────────────────────────────────────────────────
# Rule family 2: Amount / Total / Value columns
# ─────────────────────────────────────────────────────────────────────────────

class TestAmountColumns:
    """Rule family 2 — Amount, Total, Value headers."""

    def test_qty_times_sp_matches_amount_resolves_as_line_total(self):
        """Qty × SP ≈ Amount in 95% of rows → Line Total."""
        qty = [2, 3, 1, 5, 4, 2, 3, 1, 4, 2]
        sp  = [100, 200, 300, 150, 250, 100, 200, 300, 150, 250]
        amt = [q * p for q, p in zip(qty, sp)]
        df = _df(Quantity=qty, **{"Selling Price": sp}, Amount=amt)
        result = evaluate("Amount", df["Amount"], df, {"Quantity", "Selling Price"})
        _auto(result)
        assert result.canonical == "Line Total"

    def test_invoice_repeat_detected_as_invoice_total(self):
        """Same total repeated for all line items in each invoice → invoice-level field."""
        inv  = ["INV001"] * 3 + ["INV002"] * 3 + ["INV003"] * 4
        total = [5000] * 3 + [3200] * 3 + [8900] * 4
        df = _df(**{"Invoice No": inv, "Order Total": total})
        result = evaluate("Order Total", df["Order Total"], df, {"Invoice No"})
        _auto(result)
        assert result.semantic == "invoice_total"
        assert result.canonical is None  # never summed row-by-row

    def test_line_level_amount_not_confused_with_invoice_total(self):
        """Different amount per row within same invoice → NOT invoice total."""
        inv = ["INV001"] * 5 + ["INV001"] * 5
        amt = [100, 200, 300, 400, 500, 150, 250, 350, 450, 550]
        df = _df(**{"Invoice No": inv, "Line Amount": amt})
        result = evaluate("Line Amount", df["Line Amount"], df, {"Invoice No"})
        # Should NOT be auto-resolved as invoice_total
        if result.decision == "auto":
            assert result.semantic != "invoice_total"

    def test_no_context_cols_asks(self):
        """No Qty/SP/InvoiceNo context → ask with Line Total as candidate."""
        amt = [1000, 2000, 3000, 4000, 5000, 1500, 2500, 3500, 4500, 5500]
        df = _df(Amount=amt)
        result = evaluate("Amount", df["Amount"], df, set())
        _ask(result)
        assert "Line Total" in result.candidates

    def test_total_header_with_qty_sp_match(self):
        """Header 'Total' + Qty×SP match → auto=Line Total."""
        qty = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        sp  = [500] * 10
        tot = [q * p for q, p in zip(qty, sp)]
        df = _df(Quantity=qty, **{"Selling Price": sp}, Total=tot)
        result = evaluate("Total", df["Total"], df, {"Quantity", "Selling Price"})
        _auto(result)
        assert result.canonical == "Line Total"

    def test_line_total_already_mapped_asks_to_prevent_duplicate(self):
        """When Line Total is already mapped to another column, ask to prevent duplicate."""
        qty = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        sp  = [500] * 10
        tot = [q * p for q, p in zip(qty, sp)]
        df = _df(Quantity=qty, **{"Selling Price": sp}, LineTotal=tot, Total=tot)
        # Line Total already claimed by 'LineTotal'
        result = evaluate("Total", df["Total"], df, {"Quantity", "Selling Price", "Line Total"})
        _ask(result)
        assert "Line Total is already mapped" in result.reason or "Line Total is already mapped" in " ".join(result.evidence)


# ─────────────────────────────────────────────────────────────────────────────
# Rule family 3: Rate / Price columns
# ─────────────────────────────────────────────────────────────────────────────

class TestRateColumns:
    """Rule family 3 — Rate, Price, Unit Price, MRP headers."""

    def test_rate_times_qty_matches_line_total_resolves_as_sp(self):
        """Rate × Quantity ≈ Line Total → Selling Price."""
        qty   = [2, 3, 1, 4, 2, 5, 1, 2, 3, 4]
        rate  = [100, 200, 300, 150, 250, 100, 200, 300, 150, 250]
        total = [q * r for q, r in zip(qty, rate)]
        df = _df(Quantity=qty, Rate=rate, **{"Line Total": total})
        result = evaluate("Rate", df["Rate"], df, {"Quantity", "Line Total"})
        _auto(result)
        assert result.canonical == "Selling Price"

    def test_rate_constant_per_invoice_asks(self):
        """Rate constant within each invoice → ask (likely MRP or fixed fee)."""
        inv  = ["INV001"] * 5 + ["INV002"] * 5
        rate = [250.0] * 5 + [500.0] * 5   # per-invoice constant
        df = pd.DataFrame({"Invoice No": inv, "Rate": rate})
        result = evaluate("Rate", df["Rate"], df, {"Invoice No"})
        _ask(result)

    def test_gst_slab_in_rate_column_resolves_as_tax(self):
        """Rate column containing only GST slabs → Tax."""
        rate = [18, 12, 18, 5, 18, 12, 18, 18, 5, 12]
        df = _df(Rate=rate)
        result = evaluate("Rate", df["Rate"], df, set())
        _auto(result)
        assert result.canonical == "Tax"

    def test_price_column_no_context_asks_with_candidates(self):
        """Price header, no matching cross-check → ask with SP/MRP/CP candidates."""
        prices = [750, 800, 1200, 950, 600, 750, 800, 1200, 950, 600]
        df = _df(Price=prices)
        result = evaluate("Price", df["Price"], df, set())
        _ask(result)
        assert len(result.candidates) > 0

    def test_unit_price_label_with_qty_match(self):
        """'Unit Price' header + Qty×UnitPrice≈LineTotal → Selling Price."""
        qty  = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        up   = [100, 100, 100, 100, 100, 200, 200, 200, 200, 200]
        lt   = [q * p for q, p in zip(qty, up)]
        df = _df(Quantity=qty, **{"Unit Price": up, "Line Total": lt})
        result = evaluate("Unit Price", df["Unit Price"], df, {"Quantity", "Line Total"})
        _auto(result)
        assert result.canonical == "Selling Price"

    def test_selling_price_already_mapped_asks_to_prevent_duplicate(self):
        """When Selling Price is already mapped to 'Rate', Price1 must ask, not duplicate."""
        qty    = [10, 5, 2, 1, 20, 4, 3, 5]
        rate   = [5.0, 10.0, 20.0, 5.0, 2.0, 15.0, 10.0, 20.0]
        price1 = [5.0, 10.0, 20.0, 5.0, 2.0, 15.0, 10.0, 20.0]
        total  = [q * r for q, r in zip(qty, rate)]
        df = _df(Qty=qty, Rate=rate, Price1=price1, Amt=total)
        # Rate is already mapped to Selling Price
        result = evaluate("Price1", df["Price1"], df, {"Rate": "Selling Price", "Qty": "Quantity", "Amt": "Line Total"})
        _ask(result)
        assert "Selling Price is already mapped to 'Rate'" in result.reason or "already mapped" in " ".join(result.evidence)

    def test_selling_price_requires_minimum_rows_for_evidence(self):
        """Fewer than MIN_ROWS_FOR_EVIDENCE matching rows must not auto-resolve."""
        qty    = [10, 5, 2]  # only 3 rows (< 5)
        price1 = [5.0, 10.0, 20.0]
        total  = [50.0, 50.0, 40.0]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _ask(result)

    def test_selling_price_fewer_than_5_eligible_rows_asks(self):
        """Fewer than 5 eligible rows must return ask even if 100% match."""
        qty    = [10, 5, 2, 4]  # 4 rows (< MIN_ROWS_FOR_EVIDENCE=5)
        price1 = [5.0, 10.0, 20.0, 15.0]
        total  = [50.0, 50.0, 40.0, 60.0]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _ask(result)

    def test_selling_price_missing_values_drops_below_minimum_rows(self):
        """Null values in qty, price, or total dropping eligible rows below 5 must return ask."""
        qty    = [10, None, 2, 4, None, 5, 2, None, 3, 1]
        price1 = [5.0, 10.0, None, 15.0, 20.0, 10.0, None, 5.0, 10.0, 20.0]
        total  = [50.0, 100.0, 40.0, 60.0, 100.0, None, 40.0, 50.0, None, 20.0]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _ask(result)

    def test_selling_price_zero_and_invalid_quantities_not_eligible(self):
        """Rows with zero, negative, or non-numeric qty do not count as eligible evidence."""
        qty    = [0, 0, "N/A", 5, 2, 4]  # only 3 eligible positive rows
        price1 = [10.0, 20.0, 15.0, 10.0, 20.0, 15.0]
        total  = [0.0, 0.0, 0.0, 50.0, 40.0, 60.0]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _ask(result)

    def test_selling_price_rounding_differences_resolves(self):
        """1% rounding differences (e.g. GST back-calculations) resolve cleanly to Selling Price."""
        qty    = [3, 7, 3, 6, 3, 7, 3, 6, 3, 7]
        price1 = [33.33, 14.28, 33.33, 16.66, 33.33, 14.28, 33.33, 16.66, 33.33, 14.28]
        total  = [100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _auto(result)
        assert result.canonical == "Selling Price"

    def test_selling_price_exactly_90_percent_matches_resolves(self):
        """Exactly 90% (9 of 10) row match satisfies UNIT_PRICE_MATCH_THRESHOLD."""
        qty    = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        price1 = [100.0] * 10
        # 9 match, 1 row has total=999 (mismatch)
        total  = [100, 200, 300, 400, 500, 100, 200, 300, 400, 999]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _auto(result)
        assert result.canonical == "Selling Price"

    def test_selling_price_below_90_percent_matches_asks(self):
        """80% (8 of 10) row match falls below 90% threshold and asks."""
        qty    = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        price1 = [100.0] * 10
        # 8 match, 2 rows mismatch
        total  = [100, 200, 300, 400, 500, 100, 200, 300, 999, 999]
        df = _df(Quantity=qty, Price1=price1, **{"Line Total": total})
        result = evaluate("Price1", df["Price1"], df, {"Quantity", "Line Total"})
        _ask(result)

    def test_selling_price_multiple_candidate_price_columns_in_batch(self):
        """In batch evaluation with Price1 and Price2, first claims Selling Price and second asks."""
        qty    = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
        price1 = [100.0] * 10
        price2 = [100.0] * 10
        total  = [100, 200, 300, 400, 500, 100, 200, 300, 400, 500]
        df = _df(Quantity=qty, Price1=price1, Price2=price2, **{"Line Total": total})
        results = evaluate_batch(["Price1", "Price2"], df, {"Quantity", "Line Total"})
        _auto(results["Price1"])
        assert results["Price1"].canonical == "Selling Price"
        _ask(results["Price2"])
        assert "Selling Price is already mapped to 'Price1'" in results["Price2"].reason


# ─────────────────────────────────────────────────────────────────────────────
# Rule family 4: Name-column disambiguation
# ─────────────────────────────────────────────────────────────────────────────

class TestNameColumnDisambiguation:
    """Rule family 4 — columns headed 'Name' or '*Name'."""

    def test_phone_neighbour_resolves_to_customer(self):
        """'Name' column next to 'Phone' → Customer."""
        df = _df(
            Name=["Alice", "Bob", "Carol", "Dave", "Eve"],
            Phone=["9876543210", "9876543211", "9876543212", "9876543213", "9876543214"],
        )
        result = evaluate("Name", df["Name"], df, set())
        _auto(result)
        assert result.canonical == "Customer"

    def test_email_neighbour_resolves_to_customer(self):
        """'Name' next to 'Email' → Customer."""
        df = _df(
            Name=["Alice", "Bob", "Carol", "Dave", "Eve"],
            Email=["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com"],
        )
        result = evaluate("Name", df["Name"], df, set())
        _auto(result)
        assert result.canonical == "Customer"

    def test_sku_neighbour_resolves_to_item(self):
        """'Name' next to 'SKU' → Item."""
        df = _df(
            Name=["Cotton Kurta", "Silk Saree", "Denim Jeans", "Formal Shirt", "Winter Shawl"],
            SKU=["SKU001", "SKU002", "SKU003", "SKU004", "SKU005"],
        )
        result = evaluate("Name", df["Name"], df, set())
        _auto(result)
        assert result.canonical == "Item"

    def test_hsn_neighbour_resolves_to_item(self):
        """'Name' next to 'HSN' → Item."""
        df = _df(
            Name=["Paracetamol", "Ibuprofen", "Aspirin", "Vitamin C", "Zinc"],
            HSN=["30049099", "30049023", "30049011", "21069099", "30049099"],
        )
        result = evaluate("Name", df["Name"], df, set())
        _auto(result)
        assert result.canonical == "Item"

    def test_both_customer_and_item_context_asks(self):
        """'Name' with both Phone AND SKU neighbours → ask."""
        df = _df(
            Name=["Alice", "Bob", "Carol", "Dave", "Eve"],
            Phone=["9876543210"] * 5,
            SKU=["SKU001"] * 5,
        )
        result = evaluate("Name", df["Name"], df, set())
        _ask(result)
        assert "Customer" in result.candidates
        assert "Item" in result.candidates

    def test_no_context_asks(self):
        """'Name' with no disambiguating neighbours → ask."""
        df = _df(
            Name=["Alice", "Bob", "Carol", "Dave", "Eve"],
            Amount=[1000, 2000, 3000, 4000, 5000],
        )
        result = evaluate("Name", df["Name"], df, set())
        _ask(result)
        assert "Customer" in result.candidates
        assert "Item" in result.candidates

    def test_product_name_header_not_matched_as_name(self):
        """'Product Name' has a product qualifier — should NOT match the Name rule."""
        # The rule explicitly excludes headers with product/item qualifiers.
        from app.services.ambiguity_engine import _is_name_like, _norm
        import re
        norm = _norm("Product Name")
        tokens = set(re.split(r"[^a-z0-9]+", norm))
        assert not _is_name_like(norm, tokens), \
            "'Product Name' should not be classified as a plain Name column"


# ─────────────────────────────────────────────────────────────────────────────
# Rule family 5: Auxiliary date columns
# ─────────────────────────────────────────────────────────────────────────────

class TestAuxiliaryDateColumns:
    """Rule family 5 — secondary date columns that should be stored-only."""

    def test_delivery_date_stored_only(self):
        """'Delivery Date' → stored-only, decision=auto, canonical=None."""
        from app.services.ambiguity_engine import _is_auxiliary_date_like, _norm
        import re
        norm = _norm("Delivery Date")
        tokens = set(re.split(r"[^a-z0-9]+", norm))
        assert _is_auxiliary_date_like(norm, tokens)

    def test_due_date_stored_only(self):
        from app.services.ambiguity_engine import _is_auxiliary_date_like, _norm
        import re
        assert _is_auxiliary_date_like(_norm("Due Date"),
                                        set(re.split(r"[^a-z0-9]+", _norm("Due Date"))))

    def test_supplier_eta_stored_only(self):
        from app.services.ambiguity_engine import _is_auxiliary_date_like, _norm
        import re
        assert _is_auxiliary_date_like(_norm("Supplier ETA"),
                                        set(re.split(r"[^a-z0-9]+", _norm("Supplier ETA"))))

    def test_expiry_date_stored_only(self):
        from app.services.ambiguity_engine import _is_auxiliary_date_like, _norm
        import re
        assert _is_auxiliary_date_like(_norm("Expiry Date"),
                                        set(re.split(r"[^a-z0-9]+", _norm("Expiry Date"))))

    def test_primary_transaction_date_not_auxiliary(self):
        """'Date', 'Sale Date', 'Invoice Date' must NOT match auxiliary rule."""
        from app.services.ambiguity_engine import _is_auxiliary_date_like, _norm
        import re
        for header in ("Date", "Sale Date", "Invoice Date", "Order Date", "Bill Date"):
            norm = _norm(header)
            tokens = set(re.split(r"[^a-z0-9]+", norm))
            assert not _is_auxiliary_date_like(norm, tokens), \
                f"'{header}' should NOT be auxiliary — it's a primary transaction date"

    def test_auxiliary_date_evaluate_returns_auto_stored_only(self):
        """evaluate() on a Delivery Date column returns auto with canonical=None."""
        dates = ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05"]
        df = _df(**{"Delivery Date": dates})
        result = evaluate("Delivery Date", df["Delivery Date"], df, set())
        _auto(result)
        assert result.canonical is None
        assert result.semantic == "date_like"


# ─────────────────────────────────────────────────────────────────────────────
# Statistical helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestStatisticalHelpers:
    """Unit tests for the pure statistical functions."""

    def test_check_product_match_perfect(self):
        """Qty × Price == Total in 100% of rows."""
        qty   = pd.Series([2, 3, 1, 4, 5])
        price = pd.Series([100.0, 200.0, 300.0, 150.0, 250.0])
        total = qty * price
        result = _check_product_match(qty, price, total)
        assert result["match_ratio"] >= 0.99

    def test_check_product_match_with_rounding(self):
        """Allows small rounding differences (1% tolerance)."""
        qty   = pd.Series([3] * 10)
        price = pd.Series([333.33] * 10)   # 3 × 333.33 = 999.99, not 1000
        total = pd.Series([1000.0] * 10)
        result = _check_product_match(qty, price, total)
        # 1% of 1000 = 10; |999.99 - 1000| = 0.01 < 10 → matches
        assert result["match_ratio"] >= 0.90

    def test_check_product_match_mismatch(self):
        """Completely unrelated series → low match ratio."""
        qty   = pd.Series([1, 2, 3, 4, 5])
        price = pd.Series([100.0, 200.0, 300.0, 400.0, 500.0])
        total = pd.Series([9999.0] * 5)  # wildly different
        result = _check_product_match(qty, price, total)
        assert result["match_ratio"] < 0.10

    def test_check_invoice_repeat_constant_groups(self):
        """All values constant within each invoice → is_repeating=True."""
        inv   = pd.Series(["A"] * 5 + ["B"] * 5)
        total = pd.Series([5000.0] * 5 + [3200.0] * 5)
        result = _check_invoice_repeat(total, inv)
        assert result["is_repeating"]
        assert result["repeat_ratio"] >= INVOICE_REPEAT_THRESHOLD

    def test_check_invoice_repeat_varying_groups(self):
        """Values differ within invoice groups → is_repeating=False."""
        inv   = pd.Series(["A"] * 5 + ["B"] * 5)
        total = pd.Series([100.0, 200.0, 300.0, 400.0, 500.0,
                           150.0, 250.0, 350.0, 450.0, 550.0])
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]

    def test_check_invoice_repeat_single_invoice_skipped(self):
        """Single invoice group → not enough evidence (groups < 2)."""
        inv   = pd.Series(["A"] * 5)
        total = pd.Series([5000.0] * 5)
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]

    def test_check_product_match_currency_strings(self):
        """Currency-formatted strings (₹1,200.00) should still match."""
        qty   = pd.Series([2, 3, 4, 5, 1])
        price = pd.Series(["₹500.00", "₹500.00", "₹500.00", "₹500.00", "₹500.00"])
        total = pd.Series([1000, 1500, 2000, 2500, 500])
        result = _check_product_match(qty, price, total)
        assert result["match_ratio"] >= UNIT_PRICE_MATCH_THRESHOLD

    def test_check_invoice_repeat_only_single_row_invoices(self):
        """Dataset with only single-row invoices has zero multi-row groups tested and does not repeat."""
        inv   = pd.Series([f"INV{i:03d}" for i in range(10)])
        total = pd.Series([100.0 * (i + 1) for i in range(10)])
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]
        assert result["groups_tested"] == 0

    def test_check_invoice_repeat_one_multi_row_invoice_insufficient(self):
        """Only one multi-row invoice is insufficient evidence (groups_tested=1 < 2)."""
        inv   = pd.Series(["INV001", "INV001", "INV001"] + [f"SINGLE_{i}" for i in range(5)])
        total = pd.Series([5000.0, 5000.0, 5000.0] + [100.0 * (i + 1) for i in range(5)])
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]
        assert result["groups_tested"] == 1

    def test_check_invoice_repeat_at_least_two_multi_row_invoices(self):
        """At least two multi-row invoices with constant values satisfy repeat evidence."""
        inv   = pd.Series(["INV001", "INV001"] + ["INV002", "INV002", "INV002"])
        total = pd.Series([5000.0, 5000.0] + [3200.0, 3200.0, 3200.0])
        result = _check_invoice_repeat(total, inv)
        assert result["is_repeating"]
        assert result["groups_tested"] == 2
        assert result["repeat_ratio"] == 1.0

    def test_check_invoice_repeat_mixed_single_and_multi_row_invoices(self):
        """Mixed single-row and multi-row invoices isolates the multi-row groups correctly."""
        inv = pd.Series(
            ["S1", "S2", "S3", "S4", "S5"]
            + ["M1", "M1"]
            + ["M2", "M2", "M2"]
            + ["M3", "M3"]
        )
        total = pd.Series(
            [10, 20, 30, 40, 50]
            + [100.0, 100.0]
            + [250.0, 250.0, 250.0]
            + [400.0, 400.0]
        )
        result = _check_invoice_repeat(total, inv)
        assert result["is_repeating"]
        assert result["groups_tested"] == 3
        assert result["repeat_ratio"] == 1.0

    def test_check_invoice_repeat_repeated_totals_vs_varying_line_totals(self):
        """Repeated totals within invoice groups repeat, whereas varying line totals do not."""
        inv = pd.Series(["INV01", "INV01"] + ["INV02", "INV02"])
        repeated_totals = pd.Series([5000.0, 5000.0, 3200.0, 3200.0])
        varying_line_totals = pd.Series([1000.0, 4000.0, 1200.0, 2000.0])

        res_rep = _check_invoice_repeat(repeated_totals, inv)
        res_var = _check_invoice_repeat(varying_line_totals, inv)

        assert res_rep["is_repeating"]
        assert res_rep["repeat_ratio"] == 1.0
        assert not res_var["is_repeating"]
        assert res_var["repeat_ratio"] == 0.0

    def test_check_invoice_repeat_null_and_nan_invoices_never_grouped(self):
        """Multiple rows with None or NaN invoice IDs are dropped and never grouped as an invoice."""
        # 4 rows with None/NaN having identical values + only 1 valid multi-row invoice (2 rows)
        inv = pd.Series([None, None, float("nan"), np.nan, "INV01", "INV01"])
        total = pd.Series([5000.0, 5000.0, 5000.0, 5000.0, 3200.0, 3200.0])
        result = _check_invoice_repeat(total, inv)
        # Without fix, the 4 null rows would form a fake group and cause groups_tested=2 -> repeating!
        # With fix, null rows are dropped, leaving only 1 valid group (groups_tested=1 < 2)
        assert not result["is_repeating"]
        assert result["groups_tested"] == 1

    def test_check_invoice_repeat_blank_and_whitespace_invoices_dropped(self):
        """Blank '' and whitespace '   ' invoice IDs are dropped and never grouped."""
        inv = pd.Series(["", "   ", "\t", "INV01", "INV01", "INV02", "INV02"])
        total = pd.Series([100.0, 100.0, 100.0, 500.0, 500.0, 600.0, 600.0])
        result = _check_invoice_repeat(total, inv)
        # Blank rows dropped; only INV01 and INV02 remain
        assert result["is_repeating"]
        assert result["groups_tested"] == 2
        assert result["repeat_ratio"] == 1.0

    def test_check_invoice_repeat_placeholder_tokens_dropped(self):
        """String placeholders like 'N/A', 'null', 'nan' are dropped and never treated as invoice IDs."""
        inv = pd.Series(["N/A", "n/a", "null", "nan", "<NA>", "INV01", "INV01"])
        total = pd.Series([99.0, 99.0, 99.0, 99.0, 99.0, 300.0, 300.0])
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]
        assert result["groups_tested"] == 1

    def test_check_invoice_repeat_all_missing_returns_zero_groups(self):
        """Dataset with exclusively missing or blank invoice IDs returns 0 groups tested."""
        inv = pd.Series([None, "", "   ", "nan", "N/A"])
        total = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0])
        result = _check_invoice_repeat(total, inv)
        assert not result["is_repeating"]
        assert result["groups_tested"] == 0

    def test_find_canonical_neighbour_dict_mapping(self):
        """_find_canonical_neighbour resolves canonical fields via dict mapping and aliases."""
        from app.services.ambiguity_engine import _find_canonical_neighbour
        df = pd.DataFrame({"Qty": [1, 2], "Bill No": ["A", "B"], "Net Amt": [10, 20]})
        mapping = {"Qty": "Quantity", "Bill No": "Invoice No", "Net Amt": "Line Total"}

        assert _find_canonical_neighbour(df, mapping, "Quantity") == "Qty"
        assert _find_canonical_neighbour(df, mapping, "Invoice No") == "Bill No"
        assert _find_canonical_neighbour(df, mapping, "Line Total") == "Net Amt"
        assert _find_canonical_neighbour(df, mapping, "Selling Price") is None

    def test_find_canonical_neighbour_set_based_callers(self):
        """_find_canonical_neighbour handles both canonical and raw column sets."""
        from app.services.ambiguity_engine import _find_canonical_neighbour
        # 1. Canonical names in set on df with exact column names
        df1 = pd.DataFrame({"Quantity": [1, 2], "Line Total": [10, 20]})
        assert _find_canonical_neighbour(df1, {"Quantity", "Line Total"}, "Quantity") == "Quantity"
        assert _find_canonical_neighbour(df1, {"Quantity", "Line Total"}, "Line Total") == "Line Total"

        # 2. Canonical names in set on df with alias column names
        df2 = pd.DataFrame({"Qty": [1, 2], "Amt": [10, 20]})
        assert _find_canonical_neighbour(df2, {"Quantity", "Line Total"}, "Quantity") == "Qty"
        assert _find_canonical_neighbour(df2, {"Quantity", "Line Total"}, "Line Total") == "Amt"

        # 3. Raw column names in set on df
        df3 = pd.DataFrame({"Qty": [1, 2], "Amt": [10, 20]})
        assert _find_canonical_neighbour(df3, {"Qty", "Amt"}, "Quantity") == "Qty"
        assert _find_canonical_neighbour(df3, {"Qty", "Amt"}, "Line Total") == "Amt"

    def test_find_canonical_neighbour_direct_vs_alias_precedence(self):
        """Direct exact column match takes precedence over alias column match."""
        from app.services.ambiguity_engine import _find_canonical_neighbour
        df = pd.DataFrame({"Quantity": [1, 2], "Qty": [1, 2]})
        # Direct exact match 'Quantity' wins over alias 'Qty'
        assert _find_canonical_neighbour(df, set(), "Quantity") == "Quantity"

    def test_find_canonical_neighbour_multiple_columns_same_role(self):
        """Multiple unmapped columns alias to the same role without committing: returns None to avoid false match."""
        from app.services.ambiguity_engine import _find_canonical_neighbour
        df = pd.DataFrame({"Price1": [10, 20], "Price2": [10, 20]})
        # Multiple unmapped price columns -> ambiguous, returns None
        assert _find_canonical_neighbour(df, set(), "Selling Price") is None

        # When one is explicitly mapped, it is returned
        assert _find_canonical_neighbour(df, {"Price1": "Selling Price"}, "Selling Price") == "Price1"

        # When one is committed to another role, the remaining uncommitted one is returned if unique
        df2 = pd.DataFrame({"Rate": [10, 20], "Price1": [10, 20]})
        mapping = {"Rate": "MRP"}
        assert _find_canonical_neighbour(df2, mapping, "Selling Price") == "Price1"

        # When all candidates are committed to different roles, returns None
        mapping_both = {"Price1": "MRP", "Price2": "Cost Price"}
        assert _find_canonical_neighbour(df, mapping_both, "Selling Price") is None

    def test_find_canonical_neighbour_exception_safety(self, monkeypatch):
        """Any exception inside guess_canonical_column is caught, logs warning, and returns None."""
        from app.services.ambiguity_engine import _find_canonical_neighbour
        import app.utils.data_validator

        def _boom(col):
            raise RuntimeError("Database connection lost")

        monkeypatch.setattr(app.utils.data_validator, "guess_canonical_column", _boom)
        df = pd.DataFrame({"UnknownCol": [1, 2]})
        result = _find_canonical_neighbour(df, set(), "Selling Price")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_batch() accumulation semantics
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluateBatch:
    """evaluate_batch() passes resolved columns forward as context."""

    def test_batch_accumulates_resolved_columns(self):
        """
        A second ambiguous column can use the first auto-resolved one as context.

        Setup: 'Rate' × 'Quantity' ≈ 'Line Total'.
        After 'Rate' is resolved, 'Total' should be verifiable via the now-known
        Selling Price × Quantity.
        """
        qty  = [2, 3, 1, 4, 5, 2, 3, 1, 4, 5]
        rate = [100, 200, 300, 150, 250, 100, 200, 300, 150, 250]
        tot  = [q * r for q, r in zip(qty, rate)]
        df = _df(Quantity=qty, Rate=rate, **{"Line Total": tot})

        # Only Rate is "ambiguous"; Quantity and Line Total are pre-mapped.
        results = evaluate_batch(["Rate"], df, already_mapped={"Quantity", "Line Total"})
        assert "Rate" in results
        result = results["Rate"]
        _auto(result)
        assert result.canonical == "Selling Price"

    def test_batch_returns_all_candidates(self):
        """evaluate_batch returns a result for every candidate."""
        df = _df(
            Rate=[100] * 10,
            Amount=[200] * 10,
            Name=["X"] * 10,
        )
        results = evaluate_batch(["Rate", "Amount", "Name"], df)
        assert set(results.keys()) == {"Rate", "Amount", "Name"}

    def test_batch_missing_column_skipped(self):
        """A column name not in df is silently skipped."""
        df = _df(Rate=[100] * 10)
        results = evaluate_batch(["Rate", "NoSuchColumn"], df)
        assert "NoSuchColumn" not in results
        assert "Rate" in results


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases and defensive behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """The engine must never raise and must handle pathological inputs."""

    def test_empty_series_returns_ask(self):
        series = pd.Series([], dtype=object)
        df = pd.DataFrame({"Rate": []})
        result = evaluate("Rate", series, df, set())
        assert result.decision in {"ask", "conflict"}

    def test_all_null_returns_ask(self):
        series = pd.Series([None, None, None, None, None], dtype=object)
        df = pd.DataFrame({"Amount": [None] * 5})
        result = evaluate("Amount", series, df, set())
        assert result.decision in {"ask", "conflict"}

    def test_unrecognised_header_asks(self):
        """A header that matches no rule family returns ask."""
        df = _df(**{"Warehouse Zone": ["A", "B", "C", "A", "B"]})
        result = evaluate("Warehouse Zone", df["Warehouse Zone"], df, set())
        assert result.decision in {"ask", "conflict"}

    def test_engine_never_raises_on_garbage(self):
        """Malformed inputs must not propagate an exception."""
        import random
        for _ in range(5):
            size = random.randint(0, 3)
            vals = [random.choice([None, "abc", 123, float("nan")]) for _ in range(size)]
            series = pd.Series(vals, dtype=object)
            df = pd.DataFrame({"???Garbage???": vals})
            try:
                result = evaluate("???Garbage???", series, df, set())
                assert result.decision in {"auto", "ask", "conflict"}
            except Exception as exc:
                pytest.fail(f"evaluate() raised unexpectedly: {exc}")

    def test_result_is_dataclass_with_required_fields(self):
        """Every returned EvidenceResult has all required fields."""
        series = _series(18, 12, 18, 12, 18, 12, 18, 18, 12, 5)
        df = _df(**{"GST %": [18, 12, 18, 12, 18, 12, 18, 18, 12, 5]})
        result = evaluate("GST %", series, df, set())
        assert hasattr(result, "decision")
        assert hasattr(result, "canonical")
        assert hasattr(result, "semantic")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
        assert hasattr(result, "evidence")
        assert hasattr(result, "candidates")
        assert isinstance(result.reason, str)
        assert isinstance(result.evidence, list)
        assert isinstance(result.candidates, list)
        assert 0.0 <= result.confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Path A regression guard (Date + Line Total)
# ─────────────────────────────────────────────────────────────────────────────

class TestPathARegression:
    """
    Phase 1 Path A: Date + Line Total upload path is NOT disturbed by the engine.
    """

    @pytest.fixture
    def path_a_df(self):
        return pd.DataFrame({
            "Date": ["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05",
                     "2026-03-06", "2026-03-07", "2026-03-08", "2026-03-09", "2026-03-10"],
            "Item":  ["Kurta"] * 10,
            "Line Total": [500.0, 750.0, 1000.0, 600.0, 800.0, 550.0, 900.0, 650.0, 700.0, 850.0],
        })

    def test_path_a_date_not_altered(self, path_a_df):
        """Date column is never touched by the evidence engine."""
        from app.utils.data_validator import normalize_dataframe
        mapping = {"Date": "Date", "Item": "Item", "Line Total": "Line Total"}
        valid_df, errors = normalize_dataframe(path_a_df, column_mapping=mapping)
        assert "Date" in valid_df.columns
        assert len(errors) == 0

    def test_path_a_revenue_unchanged(self, path_a_df):
        """Line Total column revenue remains exact after normalisation."""
        from app.utils.data_validator import normalize_dataframe
        from app.services.sales_calculations import _prepare
        mapping = {"Date": "Date", "Item": "Item", "Line Total": "Line Total"}
        valid_df, _ = normalize_dataframe(path_a_df, column_mapping=mapping)
        prepped = _prepare(valid_df)
        expected_revenue = sum([500, 750, 1000, 600, 800, 550, 900, 650, 700, 850])
        actual_revenue = float(prepped["_row_revenue"].sum())
        assert abs(actual_revenue - expected_revenue) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Path B regression guard (Date + Quantity + Selling Price)
# ─────────────────────────────────────────────────────────────────────────────

class TestPathBRegression:
    """
    Phase 1 Path B: Date + Quantity + Selling Price upload path is NOT disturbed.
    """

    @pytest.fixture
    def path_b_df(self):
        qty  = [2, 3, 1, 4, 2, 5, 1, 2, 3, 4]
        sp   = [500.0, 400.0, 1000.0, 250.0, 600.0, 300.0, 800.0, 450.0, 700.0, 350.0]
        return pd.DataFrame({
            "Date": [f"2026-03-{i:02d}" for i in range(1, 11)],
            "Quantity": qty,
            "Selling Price": sp,
        })

    def test_path_b_revenue_unchanged(self, path_b_df):
        """Qty × Selling Price revenue is exact after normalisation."""
        from app.utils.data_validator import normalize_dataframe
        from app.services.sales_calculations import _prepare
        mapping = {"Date": "Date", "Quantity": "Quantity", "Selling Price": "Selling Price"}
        valid_df, errors = normalize_dataframe(path_b_df, column_mapping=mapping)
        assert len(errors) == 0
        prepped = _prepare(valid_df)
        qty = [2, 3, 1, 4, 2, 5, 1, 2, 3, 4]
        sp  = [500.0, 400.0, 1000.0, 250.0, 600.0, 300.0, 800.0, 450.0, 700.0, 350.0]
        expected = sum(q * p for q, p in zip(qty, sp))
        actual = float(prepped["_row_revenue"].sum())
        assert abs(actual - expected) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Integration smoke test via column_understanding.analyse()
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    """
    The evidence engine is wired into column_understanding.analyse().
    These tests run the full pipeline and verify the engine fires correctly.
    """

    def _analyse(self, df: pd.DataFrame) -> list[dict]:
        reports, timings, _, _ = asyncio.run(
            __import__("app.services.column_understanding", fromlist=["analyse"]).analyse(
                df, ai_consent=False, run_tier2=False
            )
        )
        return reports

    def test_gst_pct_column_settled_by_evidence_engine(self):
        """
        Full pipeline: 'GST %' column with slab values is settled by evidence
        engine with source='evidence', NOT escalated to Tier 2.
        """
        df = pd.DataFrame({
            "Date": ["2026-01-01"] * 10,
            "Quantity": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "Rate": [100, 200, 300, 150, 250, 100, 200, 300, 150, 250],
            "GST %": [18, 12, 18, 5, 18, 12, 18, 18, 12, 5],
        })
        reports = self._analyse(df)
        gst_report = next((r for r in reports if r["raw_column"] == "GST %"), None)
        assert gst_report is not None
        # Should be resolved by the evidence engine
        assert gst_report["source"] in {"evidence", "local"}, \
            f"Expected source='evidence'|'local', got {gst_report['source']!r}"
        assert gst_report.get("suggested_field") == "Tax" or gst_report.get("needs_review") is not True

    def test_pipeline_timings_include_evidence_ms(self):
        """PipelineTimings now exposes evidence_ms in as_dict()."""
        from app.services.column_understanding import PipelineTimings
        t = PipelineTimings()
        t.evidence_ms = 3.7
        d = t.as_dict()
        assert "evidence_ms" in d
        assert d["evidence_ms"] == 3.7

    def test_pipeline_timings_consistent_contract(self):
        """PipelineTimings contract consistently yields 4 stage keys and serializes into schema."""
        from app.services.column_understanding import PipelineTimings
        from app.models.schemas import PipelineTimings as SchemaTimings
        t = PipelineTimings()
        d = t.as_dict()
        assert set(d.keys()) == {"tier1_ms", "evidence_ms", "tier2_ms", "total_ms"}
        schema_obj = SchemaTimings(**d)
        assert schema_obj.evidence_ms == 0.0
        assert schema_obj.tier1_ms == 0.0
        assert schema_obj.tier2_ms == 0.0
        assert schema_obj.pandas_ms is None

    def test_evidence_engine_does_not_break_clean_file(self):
        """A file with only well-known canonical columns runs through without any 'auto' changes."""
        df = pd.DataFrame({
            "Date": ["2026-01-01"] * 10,
            "Quantity": list(range(1, 11)),
            "Selling Price": [100.0] * 10,
        })
        reports = self._analyse(df)
        # No column should have source='evidence' because they were clean from Tier 1
        evidence_resolved = [r for r in reports if r.get("source") == "evidence"]
        assert len(evidence_resolved) == 0

    def test_auxiliary_date_column_resolved_stored_only(self):
        """'Delivery Date' column in a file with a primary Date is stored-only."""
        df = pd.DataFrame({
            "Date": ["2026-01-01"] * 6,
            "Quantity": [1, 2, 3, 4, 5, 6],
            "Selling Price": [100.0] * 6,
            "Delivery Date": ["2026-01-05"] * 6,
        })
        reports = self._analyse(df)
        delivery_report = next((r for r in reports if r["raw_column"] == "Delivery Date"), None)
        assert delivery_report is not None
        # Delivery Date is classified as auxiliary → stored-only (canonical=None) or needs no change
        # It should NOT be mapped to 'Date' (the primary transaction date)
        assert delivery_report.get("suggested_field") != "Date", \
            "Delivery Date must never be remapped to primary Date"
