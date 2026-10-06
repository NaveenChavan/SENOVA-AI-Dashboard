"""
Tests for the number post-check.

The test names are the specification. If you cannot state a case as "year 2026
exempt" and "Rs 9,99,999 rejected", the check has a hole in it.

The pairs matter more than the individual cases. "5 units sold" verified against
units=5 and rejected against units=4 proves the check is *doing something*; a
single passing assertion could just as easily mean the token was never examined.
So most tests here come in pairs, and the negative twin is the one that carries
the weight.
"""

from __future__ import annotations

import pytest

from app.services.number_guard import verify


# ── Exempt: years ────────────────────────────────────────────────────────────


class TestYearExemption:
    @pytest.mark.parametrize(
        "text",
        [
            "Sales have fallen since 2026.",
            "The year 2026 started strongly.",
            "Comparing 2026 against the previous year.",
            "In 2026 revenue recovered.",
        ],
    )
    def test_a_bare_year_is_exempt(self, text):
        """A year appears in correct prose and is never a metrics value. Verifying
        it literally would reject the rewrite."""
        assert verify(text, {"revenue": 1000.0})[0] is True

    def test_a_year_is_not_a_count(self):
        """1999 is not a count of anything. If a hallucinated "1,999 units" is
        written with a comma it must still be rejected — the year exemption only
        ever applied to bare years, and this pins that it is not a loophole."""
        assert verify("We sold 1999 units.", {"units": 5.0})[0] is False


# ── Exempt: dates ────────────────────────────────────────────────────────────


class TestDateExemption:
    @pytest.mark.parametrize(
        "text",
        [
            "Revenue dropped sharply on 14 Jul.",
            "Revenue dropped sharply on 14 July.",
            "On 14 Jul revenue dropped sharply.",
            "Sales fell on 2026-07-14.",
            "Sales fell on 14/07/2026.",
            "Sales fell on 14-07-2026.",
            "Sales fell on Jul 14.",
            "On 3 Aug margins were thin.",
        ],
    )
    def test_dates_are_exempt(self, text):
        """A day number is not a business figure. These appear in essentially every
        good insight and appear in no metrics dict."""
        assert verify(text, {"revenue": 1000.0})[0] is True

    def test_a_full_date_is_one_token_not_three_numbers(self):
        """The subtle one. Scanned naively, 2026-07-14 yields 2026, 07 and 14 —
        two of which are hallucinated counts as far as the checker is concerned,
        so every correctly-dated rewrite would be thrown away. If this test ever
        fails, the whole feature has become useless in practice."""
        verified, offenders = verify("Sales were weak on 2026-07-14.", {"revenue": 10.0})
        assert verified is True
        assert offenders == []

    def test_a_day_number_is_exempt_but_a_count_is_not(self):
        """The boundary the exemption must not cross: 14 next to "Jul" is a date,
        14 next to "sold" is a count and has to be checked."""
        assert verify("On 14 Jul sales fell.", {"units": 99.0})[0] is True
        assert verify("We sold 14 units.", {"units": 99.0})[0] is False


# ── Exempt: small ranking ordinals ───────────────────────────────────────────


class TestRankingExemption:
    @pytest.mark.parametrize(
        "text",
        [
            "The top 3 items drive most of your revenue.",
            "Your 3 highest sellers are all in one category.",
            "The bottom 2 items are dead stock.",
            "Check the 5 worst performing lines.",
            "It was the 3rd highest day of the month.",
            "The 2nd biggest problem is slow stock.",
            "Look at the top 1 item first.",
            "The last 4 weeks have been flat.",
        ],
    )
    def test_rankings_are_exempt(self, text):
        """A rank is not a quantity. "The top 3 items" is a position, and no
        metrics dict records positions."""
        assert verify(text, {"revenue": 1000.0})[0] is True

    def test_a_large_rank_is_not_exempt(self):
        """The rank bound is deliberately small. "The top 47 items" is a count of
        how many items, which a shopkeeper could act on, so it is verified."""
        assert verify("Your top 47 items cover 90% of sales.", {"revenue": 100.0})[0] is False

    def test_a_ranking_word_does_not_exempt_a_neighbouring_count(self):
        """The positional rule, stated as a test. "top 3" is a rank and passes; the
        very next number is not adjacent to the ranking word, so it must be
        verified. This is the case that separates a positional implementation from
        a number-range one."""
        verified, offenders = verify("The top 3 items made 5000 units.", {"units": 42.0})
        assert verified is False
        assert "5000" in offenders

    def test_a_small_integer_in_a_count_position_is_verified(self):
        """5 is inside the rank range and is still a count here, because no ranking
        word sits beside it. The exemption is positional, not numeric."""
        verified, offenders = verify("5 units sold on that day.", {"units": 4.0})
        assert verified is False
        assert offenders == ["5"]

        assert verify("5 units sold on that day.", {"units": 5.0})[0] is True


# ── Verified: counts ─────────────────────────────────────────────────────────


class TestCountVerification:
    def test_a_matching_count_passes(self):
        assert verify("You sold 47 units.", {"units": 47.0})[0] is True

    def test_a_wrong_count_is_rejected(self):
        verified, offenders = verify("You sold 47 units.", {"units": 12.0})
        assert verified is False
        assert offenders == ["47"]

    def test_a_near_miss_is_rejected(self):
        """12 versus 47 is not a rounding difference. The tolerance exists to
        absorb genuine rounding, not to wave away a wrong figure."""
        assert verify("You sold 47 units.", {"units": 46.0})[0] is False

    def test_rounding_within_tolerance_passes(self):
        """Absolute tolerance of 0.5 exists for exactly this: a model rounding
        47.4 to 47 has not invented anything."""
        assert verify("You sold 47 units.", {"units": 47.4})[0] is True


# ── Verified: amounts ────────────────────────────────────────────────────────


class TestAmountVerification:
    @pytest.mark.parametrize(
        "text",
        [
            "Revenue was ₹1,20,000 this month.",
            "Revenue was Rs. 120,000 this month.",
            "Revenue was Rs 120000 this month.",
        ],
    )
    def test_a_matching_amount_passes(self, text):
        """Currency symbol, "Rs." prefix and plain digits are the same figure. All
        three notations occur in Indian retail exports and in prose."""
        assert verify(text, {"revenue": 120000.0})[0] is True

    def test_a_hallucinated_amount_is_rejected(self):
        """The case this entire module exists for. A model inventing a revenue
        figure is the one failure a shopkeeper cannot detect by eye."""
        verified, offenders = verify(
            "Revenue was ₹1,20,000 this month.", {"revenue": 99999.0}
        )
        assert verified is False
        assert offenders

    def test_an_over_the_top_amount_is_rejected(self):
        """A plausible-looking but wrong magnitude. 9,99,999 vs 1,20,000 is a
        rounding difference to the eye and a completely different business
        result, which is why relative tolerance matters."""
        verified, offenders = verify("Revenue was Rs 9,99,999.", {"revenue": 120000.0})
        assert verified is False
        assert "9,99,999" in offenders[0].replace("Rs", "").strip() or offenders

    def test_lakh_and_crore_are_understood(self):
        """Indian retail prose uses these constantly. If "1.5 lakh" were verified
        as 1.5, every correctly-written amount in that style would be rejected and
        the check would be switched off within a week."""
        assert verify("You made 1.5 lakh in revenue.", {"revenue": 150000.0})[0] is True
        assert verify("You made 2 crore in revenue.", {"revenue": 20000000.0})[0] is True

    def test_a_wrong_lakh_amount_is_still_rejected(self):
        """Scaling must not become a loophole: 3 lakh against 1.5 lakh is wrong."""
        assert verify("You made 3 lakh in revenue.", {"revenue": 150000.0})[0] is False


# ── Verified: percentages ────────────────────────────────────────────────────


class TestPercentageVerification:
    def test_a_matching_percentage_passes(self):
        assert verify("Revenue fell 78% last month.", {"drop_pct": 78.0})[0] is True

    def test_a_wrong_percentage_is_rejected(self):
        verified, offenders = verify("Revenue fell 78% last month.", {"drop_pct": 41.0})
        assert verified is False
        assert offenders == ["78"]

    def test_percent_sign_is_not_part_of_the_number(self):
        """78 and 78.0 must compare equal — otherwise every percentage in the
        system fails the check on a type technicality."""
        assert verify("Margin was 12% today.", {"margin_pct": 12})[0] is True

    def test_a_small_rounding_difference_passes(self):
        """77.9 rounds to 78 in prose. That is a formatting choice, not a
        hallucination, and the 0.5 absolute tolerance is what allows it."""
        assert verify("Margin was 78%.", {"margin_pct": 77.9})[0] is True


# ── Evidence counts as a source ──────────────────────────────────────────────


class TestEvidenceSource:
    def test_a_number_from_evidence_is_allowed(self):
        """Prose legitimately reaches for specifics from the finding's evidence
        list — an item name, a date, a per-item figure — that were never headline
        metrics. Without evidence the check would reject correct rewrites."""
        assert verify(
            "Cotton Kurta fell 31 units this week.",
            {"revenue": 1000.0},
            evidence=["Cotton Kurta", "31 units this week"],
        )[0] is True

    def test_evidence_does_not_license_anything_else(self):
        """The exemption is per-value. Having one correct figure in evidence does
        not make every other number in the sentence acceptable."""
        verified, offenders = verify(
            "Cotton Kurta fell 31 units and then 9000 units.",
            {"revenue": 1000.0},
            evidence=["Cotton Kurta", "31 units"],
        )
        assert verified is False
        assert "9000" in offenders


# ── Multiple numbers, mixed exemptions ───────────────────────────────────────


class TestMixedProse:
    def test_a_realistic_rewrite_passes(self):
        """
        One sentence containing all three exempt kinds and two real figures — the
        case that a naive "every digit must be a metric" implementation would
        reject, and therefore the case that decides whether this feature is usable.
        """
        text = (
            "Since 2026, revenue on 14 Jul fell 78% versus the same day last month; "
            "your top 3 items still account for most of the ₹1,20,000 you took."
        )
        verified, offenders = verify(text, {"drop_pct": 78.0, "revenue": 120000.0})
        assert verified is True, offenders

    def test_one_bad_number_poisons_the_whole_sentence(self):
        """Deliberate: the unit of output is the sentence, not the token. A rewrite
        with one invented figure is discarded whole rather than half-trusted, so
        the UI never has to reason about partial verification."""
        verified, offenders = verify(
            "Revenue fell 78% and then recovered to Rs 9,99,999.",
            {"drop_pct": 78.0, "revenue": 120000.0},
        )
        assert verified is False
        assert len(offenders) == 1


# ── Degenerate input ─────────────────────────────────────────────────────────


class TestDegenerateInput:
    @pytest.mark.parametrize("text", ["", None, "   ", "No figures in this sentence at all."])
    def test_text_without_numbers_always_passes(self, text):
        """Nothing to check means nothing to reject. A rewrite with no numbers
        carries no risk of a hallucinated number."""
        assert verify(text, {"revenue": 100.0})[0] is True

    def test_no_metrics_and_no_evidence_rejects_every_number(self):
        """If the insight carries no figures, any figure in the prose is invented.
        """
        verified, offenders = verify("Revenue was ₹5,000.", {}, [])
        assert verified is False
        assert offenders

    def test_text_without_numbers_passes_even_with_no_metrics(self):
        assert verify("Sales have been soft this month.", {}, [])[0] is True

    def test_none_metrics_is_treated_as_empty(self):
        assert verify("Revenue was ₹5,000.", None, None)[0] is False

    def test_non_numeric_metrics_values_are_skipped(self):
        """A metrics dict legitimately carries None and labels. Coercing those to
        floats would either raise or invent a 0.0 that anything could match."""
        verified, offenders = verify(
            "Something happened.", {"item": None, "category": "Kurta"}
        )
        assert verified is True

    def test_boolean_metric_values_are_not_treated_as_numbers(self):
        """``True`` is an ``int`` in Python. Treating it as 1.0 would let a
        hallucinated "1 unit" match any true-flagged metric."""
        assert verify("You sold 1 unit.", {"flag": True})[0] is False

    def test_offenders_are_returned_for_logging(self):
        """The offenders list is what the log line and the test suite both read, so
        it has to name the offending tokens rather than just reporting a boolean."""
        verified, offenders = verify("Lost ₹1,000 and 50 units.", {"units": 10.0})
        assert verified is False
        assert len(offenders) == 2
