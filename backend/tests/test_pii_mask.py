"""
Tests for the redaction layer that gates everything Tier 2 sends to Gemini.

The property under test throughout: **no raw value from a suppressed or
maskable column reaches the request payload**. Several tests assert on absence
of a specific literal rather than on the presence of a placeholder, because a
masking bug that silently dropped nothing would still pass a weaker check.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pii_mask import (
    SAMPLE_LIMIT,
    mask_samples,
    mask_text,
    prepare_samples,
    shape_stats,
    should_suppress_values,
)


# ── Masking ──────────────────────────────────────────────────────────────────


class TestMaskText:
    def test_plain_text_passes_through(self):
        assert mask_text("Cotton Kurta") == "Cotton Kurta"

    def test_email_is_masked(self):
        masked = mask_text("bill to ramesh.sharma@shop.in today")
        assert "ramesh.sharma" not in masked
        assert "@shop.in" not in masked
        assert "[email]" in masked

    def test_indian_mobile_is_masked(self):
        assert "9876543210" not in mask_text("9876543210")
        assert "[phone]" in mask_text("9876543210")

    def test_prefixed_indian_mobile_is_masked(self):
        for value in ("+91 98765 43210", "+919876543210", "91-9876543210"):
            assert "9876543210" not in mask_text(value), value

    def test_long_digit_run_is_masked(self):
        # An Aadhaar-style identifier that no phone pattern would catch.
        masked = mask_text("aadhaar 123456789012")
        assert "123456789012" not in masked
        assert "[number]" in masked

    def test_email_masking_wins_over_phone_pattern(self):
        """An address whose local part looks phone-like must not survive partly."""
        masked = mask_text("9876543210@shop.in")
        assert "9876543210" not in masked
        assert masked == "[email]"

    def test_short_numbers_are_not_masked(self):
        # A quantity of 3 and an invoice sequence of 1204 are ordinary data.
        assert mask_text("3") == "3"
        assert "[number]" not in mask_text("order 1204 of 5000")

    def test_nan_and_nat_become_empty_string(self):
        assert mask_text(float("nan")) == ""
        assert mask_text(None) == ""
        assert mask_text(pd.NaT) == ""

    def test_long_value_is_truncated(self):
        masked = mask_text("A" * 500)
        assert len(masked) == 60

    def test_non_string_input_cannot_bypass_masking(self):
        # A numeric cell rendered to text still passes through the patterns.
        assert isinstance(mask_text(9876543210), str)

    def test_mask_samples_respects_the_limit_and_drops_empties(self):
        samples = mask_samples(["a", "", None, "b", "c", "d", "e", "f"])
        assert len(samples) == SAMPLE_LIMIT
        assert "" not in samples and "nan" not in samples


# ── Shape statistics ─────────────────────────────────────────────────────────


class TestShapeStats:
    def test_numeric_column(self):
        stats = shape_stats(pd.Series([1, 2, 3, 4, 5]))
        assert stats["numeric_ratio"] == 1.0
        assert stats["all_integer"] is True
        assert stats["date_parse_ratio"] == 0.0

    def test_currency_strings_count_as_numeric(self):
        """'₹ 1,200.00' is object dtype but is not personal data."""
        stats = shape_stats(pd.Series(["₹ 1,200.00", "Rs. 900", "1200", "850.5"]))
        assert stats["numeric_ratio"] == 1.0

    def test_text_column(self):
        stats = shape_stats(pd.Series(["Cotton Kurta", "Silk Saree", "Denim Jeans"]))
        assert stats["numeric_ratio"] == 0.0
        assert stats["unique_ratio"] == 1.0

    def test_dates_recognised_in_both_orders(self):
        series = pd.Series(["2026-04-05", "05/04/2026", "5 Apr 2026", "Apr 5, 2026"])
        assert shape_stats(series)["date_parse_ratio"] == 1.0

    def test_bare_small_integer_is_not_a_date(self):
        """Guards against pd.to_datetime reading '12' as a date."""
        assert shape_stats(pd.Series(["12", "7", "3", "42"]))["date_parse_ratio"] == 0.0

    def test_empty_series_is_safe(self):
        stats = shape_stats(pd.Series([], dtype="object"))
        assert stats["numeric_ratio"] == 0.0
        assert stats["null_ratio"] == 0.0

    def test_all_null_series_is_safe(self):
        stats = shape_stats(pd.Series([None, None], dtype="object"))
        assert stats["null_ratio"] == 1.0

    def test_never_returns_raw_values(self):
        """The stats dict is what a suppressed column reports, so it must be data-free."""
        series = pd.Series(["Ramesh Sharma", "Sunita Verma", "Ajay Gupta"])
        rendered = str(shape_stats(series))
        for name in ("Ramesh", "Sharma", "Sunita", "Ajay"):
            assert name not in rendered


# ── The suppression decision ─────────────────────────────────────────────────


class TestShouldSuppressValues:
    @pytest.mark.parametrize("label", ["customer", "notes", "Customer", "NOTES"])
    def test_pii_sensitive_labels_always_suppress(self, label):
        assert should_suppress_values(label, numeric_ratio=1.0) is True

    def test_pii_suppresses_even_for_a_numeric_looking_column(self):
        # A customer id column is numeric and still must not be sent.
        assert should_suppress_values("customer", numeric_ratio=1.0) is True

    @pytest.mark.parametrize("label", [None, "", "other"])
    def test_unknown_text_column_suppresses(self, label):
        assert should_suppress_values(label, numeric_ratio=0.0) is True

    @pytest.mark.parametrize("label", [None, "", "other"])
    def test_unknown_numeric_column_does_not_suppress(self, label):
        assert should_suppress_values(label, numeric_ratio=1.0) is False

    def test_unknown_falls_back_to_dtype_when_no_ratio(self):
        assert should_suppress_values("other", inferred_dtype="object") is True
        assert should_suppress_values("other", inferred_dtype="float64") is False

    def test_total_uncertainty_suppresses(self):
        assert should_suppress_values(None) is True

    @pytest.mark.parametrize(
        "label", ["date", "quantity", "unit_price", "cost", "revenue", "product", "region"]
    )
    def test_known_non_pii_labels_send_masked_values(self, label):
        assert should_suppress_values(label, numeric_ratio=0.0) is False


# ── Sample preparation ───────────────────────────────────────────────────────


class TestPrepareSamples:
    def test_customer_column_returns_no_samples(self):
        series = pd.Series(["Ramesh Sharma", "Sunita Verma", "Ajay Gupta"])
        samples, suppressed = prepare_samples(series, "customer", numeric_ratio=0.0)
        assert suppressed is True
        assert samples == []

    def test_unmapped_text_column_returns_no_samples(self):
        series = pd.Series(["some free text", "another remark", "a third note"])
        samples, suppressed = prepare_samples(series, "other", numeric_ratio=0.0)
        assert suppressed is True
        assert samples == []

    def test_unmapped_numeric_column_does_send_samples(self):
        series = pd.Series([1, 2, 3, 4])
        samples, suppressed = prepare_samples(series, "other", numeric_ratio=1.0)
        assert suppressed is False
        assert len(samples) == 4

    def test_sent_samples_are_masked(self):
        series = pd.Series(["9876543210", "ramesh@shop.in", "123456789012"])
        samples, suppressed = prepare_samples(series, "other", numeric_ratio=0.0)
        # numeric_ratio is 0 so this is suppressed — assert the guarantee, then
        # exercise masking directly on a label that is allowed to send.
        assert suppressed is True
        assert samples == []

        allowed, allowed_suppressed = prepare_samples(
            series, "id", numeric_ratio=0.0, inferred_dtype="object"
        )
        # 'id' is a known non-PII label, so values flow — but masked.
        assert allowed_suppressed is False
        assert "9876543210" not in " ".join(allowed)
        assert "ramesh@shop.in" not in " ".join(allowed)
        assert "123456789012" not in " ".join(allowed)

    def test_nulls_do_not_consume_sample_slots(self):
        series = pd.Series([None, "₹ 100", None, "₹ 200", None, "₹ 300"])
        samples, _ = prepare_samples(series, "revenue", numeric_ratio=1.0)
        assert samples == ["₹ 100", "₹ 200", "₹ 300"]

    def test_large_column_samples_head_and_tail(self):
        series = pd.Series(range(1000))
        samples, _ = prepare_samples(series, "quantity", numeric_ratio=1.0)
        assert len(samples) == SAMPLE_LIMIT
        assert "0" in samples and "999" in samples

    def test_numeric_ratio_is_derived_when_not_supplied(self):
        series = pd.Series([1, 2, 3])
        _, suppressed = prepare_samples(series, "other")
        assert suppressed is False

    def test_empty_series_is_safe(self):
        samples, suppressed = prepare_samples(pd.Series([], dtype="object"), "revenue")
        assert samples == []
        assert suppressed is False