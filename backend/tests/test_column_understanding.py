"""
Tests for the 2-tier orchestrator.

The property that matters most here is not accuracy — it's that the pipeline
*always* produces a complete, usable mapping regardless of what Tier 1 or Tier 2
do. A shopkeeper uploading a file must never get an error page because a model
was slow, and must never get a confident-looking mapping for a column nobody
actually understood.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.services import ai_cache, column_understanding, tier1_classifier, tier2_gemini
from app.services.column_understanding import _resolve_collisions, analyse


@pytest.fixture
def gemini_off(monkeypatch):
    """Operator switch off — the default production posture."""
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", False)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "")


@pytest.fixture
def gemini_on(monkeypatch):
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(tier2_gemini, "GEMINI_TOTAL_BUDGET_SECONDS", 5.0)


@pytest.fixture
def no_embeddings(monkeypatch):
    """Force the alias-map path so these tests don't need the ONNX model."""
    monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", False)


def _by_name(reports):
    return {report["raw_column"]: report for report in reports}


# ── The AI-off path ──────────────────────────────────────────────────────────


class TestAiDisabled:
    async def test_aliased_file_maps_identically_to_before(self, gemini_off, no_embeddings):
        """With both switches off this must reproduce the pre-feature behaviour
        for a file whose headers are all known aliases."""
        frame = pd.DataFrame(
            {
                "Bill Date": ["01-04-2026", "02-04-2026"],
                "Item Name": ["Kurta", "Saree"],
                "Stock Group": ["Kurta", "Saree"],
                "Qty.": [3, 2],
                "Rate/Unit": [750, 3200],
                "Purchase Rate": [300, 1800],
            }
        )
        reports, timings, notice = await analyse(frame, ai_consent=False)

        assert notice is None
        assert _by_name(reports)["Bill Date"]["suggested_field"] == "Date"
        assert _by_name(reports)["Item Name"]["suggested_field"] == "Item"
        assert _by_name(reports)["Stock Group"]["suggested_field"] == "Category"
        assert _by_name(reports)["Qty."]["suggested_field"] == "Quantity"
        assert _by_name(reports)["Rate/Unit"]["suggested_field"] == "Selling Price"
        assert _by_name(reports)["Purchase Rate"]["suggested_field"] == "Cost Price"
        assert timings.tier2_ms == 0.0

    async def test_no_gemini_call_is_attempted(self, gemini_off, no_embeddings, monkeypatch):
        called = []

        async def _spy(*args, **kwargs):
            called.append(1)
            return tier2_gemini.Tier2Result(source=tier2_gemini.SOURCE_SKIPPED)

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _spy)

        frame = pd.DataFrame({"Weird Column": ["a", "b"]})
        await analyse(frame, ai_consent=True)
        assert called == []

    async def test_unrecognised_column_is_left_for_the_user(self, gemini_off, no_embeddings):
        frame = pd.DataFrame({"Bill Date": ["01-04-2026", "02-04-2026"], "Zorp Factor": ["x", "y"]})
        reports, _timings, _notice = await analyse(frame, ai_consent=False)

        report = _by_name(reports)["Zorp Factor"]
        assert report["suggested_field"] is None
        assert report["needs_review"] is True
        assert report["confidence_band"] == "low"

    async def test_timings_are_always_reported(self, gemini_off, no_embeddings):
        frame = pd.DataFrame({"Qty.": [1, 2, 3]})
        _reports, timings, _notice = await analyse(frame)
        payload = timings.as_dict()
        assert set(payload) == {"tier1_ms", "tier2_ms", "total_ms"}
        assert payload["total_ms"] >= payload["tier1_ms"]


# ── Consent propagation ──────────────────────────────────────────────────────


class TestConsentPropagation:
    async def test_consent_false_leaves_ambiguous_columns_unmapped(self, gemini_on, no_embeddings):
        frame = pd.DataFrame({"Zorp Factor": ["a", "b", "c"]})
        reports, timings, notice = await analyse(frame, ai_consent=False)

        report = _by_name(reports)["Zorp Factor"]
        assert report["suggested_field"] is None
        assert timings.tier2_ms == 0.0
        assert notice is None or "not approved" in notice

    async def test_consent_false_never_reaches_gemini(self, gemini_on, no_embeddings, monkeypatch):
        """The end-to-end version of the Tier 2 gate: with consent withheld, the
        whole pipeline must not produce a single outbound request."""
        recorder_calls = []

        class _Boom:
            def __init__(self, *a, **k):
                recorder_calls.append(1)

        monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Boom)

        frame = pd.DataFrame({"Zorp Factor": ["a", "b", "c"]})
        await analyse(frame, ai_consent=False)
        assert recorder_calls == []


# ── Tier 2 merging ───────────────────────────────────────────────────────────


class TestTier2Merging:
    async def test_verdict_is_merged_with_source_gemini(self, gemini_on, no_embeddings, monkeypatch):
        async def _fake_resolve(columns, ai_consent, cache_load=None, cache_save=None, cache_key=None):
            assert ai_consent is True
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "quantity", "confidence": 0.92, "reason": "values are whole numbers"}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _timings, _notice = await analyse(frame, ai_consent=True)

        report = _by_name(reports)["Zorp Factor"]
        assert report["suggested_field"] == "Quantity"
        assert report["source"] == "gemini"
        assert report["confidence_band"] == "high"
        # Settled by Gemini at 0.92 — the user has nothing to disambiguate here.
        assert report["needs_review"] is False

    async def test_cached_verdict_still_reports_as_gemini(self, gemini_on, no_embeddings, monkeypatch):
        """A cache hit is Gemini's answer even though this process never called
        it. Reporting it as 'local' would tell the user their own data decided
        something the local classifier cannot see."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "quantity", "confidence": 0.9, "reason": "rounded"}},
                source=tier2_gemini.SOURCE_CACHE,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=True)
        assert _by_name(reports)["Zorp Factor"]["source"] == "gemini"

    async def test_failure_marks_the_column_for_review(self, gemini_on, no_embeddings, monkeypatch):
        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                source=tier2_gemini.SOURCE_FAILED,
                notice="We couldn't identify some columns automatically.",
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _timings, notice = await analyse(frame, ai_consent=True)

        report = _by_name(reports)["Zorp Factor"]
        assert report["suggested_field"] is None
        assert report["source"] == "fallback"
        assert report["needs_review"] is True
        assert notice is not None

    async def test_a_gemini_verdict_clears_the_review_flag(self, gemini_on, no_embeddings, monkeypatch):
        """Tier 1 escalates 'Zorp Factor'; Gemini answers. The column must not
        still be flagged for review — the review list is what the user reads to
        decide what to check, and a stale flag makes it untrustworthy."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "quantity", "confidence": 0.95, "reason": "whole numbers"}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=True)
        assert _by_name(reports)["Zorp Factor"]["needs_review"] is False

    async def test_collision_demotion_forces_review_on(self, gemini_on, no_embeddings, monkeypatch):
        """A column demoted by a collision is unmapped, so it must be flagged —
        otherwise it sits in the mapping looking decided and silently gets
        dropped by normalize_dataframe."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Rate": {"label": "unit_price", "confidence": 0.95, "reason": ""}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Selling Price": [100, 200], "Rate": [120, 240]})
        reports, _t, _n = await analyse(frame, ai_consent=True)

        demoted = [r for r in reports if r["suggested_field"] is None]
        assert len(demoted) == 1
        assert demoted[0]["needs_review"] is True

    async def test_clean_file_flags_nothing_for_review(self, gemini_off, no_embeddings):
        """The ordinary case: every header an exact alias match. The review list
        must be empty, or every upload opens with noise the user must dismiss."""

        frame = pd.DataFrame(
            {
                "Bill Date": ["01-04-2026", "02-04-2026"],
                "Item Name": ["Kurta", "Saree"],
                "Qty.": [3, 2],
                "Rate/Unit": [750, 3200],
            }
        )
        reports, _t, _n = await analyse(frame, ai_consent=False)
        assert [r["raw_column"] for r in reports if r["needs_review"]] == []

    async def test_a_low_confidence_suggestion_still_needs_review(self, gemini_on, no_embeddings, monkeypatch):
        """Mapped is not the same as settled. A 0.4-confidence guess should still
        be checked by a human before any number is computed from it."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "tax", "confidence": 0.4, "reason": "guess"}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=True)

        report = _by_name(reports)["Zorp Factor"]
        assert report["suggested_field"] == "Tax"
        assert report["needs_review"] is True

    async def test_model_saying_other_is_respected(self, gemini_on, no_embeddings, monkeypatch):
        """A model that declines to guess must not be overruled."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "other", "confidence": 0.8, "reason": "unclear"}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=True)
        assert _by_name(reports)["Zorp Factor"]["suggested_field"] is None

    async def test_mapped_semantics_with_no_canonical_target(self, gemini_on, no_embeddings, monkeypatch):
        """Gemini identifying a notes column is a real answer — it just has
        nowhere to go. It must surface as recognised-but-unused, not as a
        broken mapping."""

        async def _fake_resolve(*args, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"Remarks": {"label": "notes", "confidence": 0.95, "reason": "additional info"}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Remarks": ["ok", "damaged"]})
        reports, _t, _n = await analyse(frame, ai_consent=True)

        report = _by_name(reports)["Remarks"]
        assert report["semantic_label"] == "notes"
        assert report["suggested_field"] is None


# Upload already ran it and sent a ``file_id``, and by then the upload has
    # succeeded — a cache that cannot be read or written must never fail the
    # request. The point of the test is that it doesn't, not that it is fast.
    async def test_a_broken_cache_does_not_fail_the_pipeline(self, gemini_on, no_embeddings, tmp_path, monkeypatch):
        """A cache read that raises must not take the upload down. Verified
        end-to-end rather than by mocking ai_cache, because the risk lives in the
        wiring — a cache path that doesn't exist yet is the normal first-upload
        case, not an edge case."""

        def _explode(*args, **kwargs):
            raise OSError("cache path unavailable")

        monkeypatch.setattr(ai_cache, "load", _explode)
        monkeypatch.setattr(ai_cache, "save", _explode)

        async def _fake_resolve(columns, ai_consent, cache_load=None, cache_save=None, cache_key=None):
            return tier2_gemini.Tier2Result(
                verdicts={"Zorp Factor": {"label": "quantity", "confidence": 0.9, "reason": ""}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=True, file_id="abc123")
        assert _by_name(reports)["Zorp Factor"]["suggested_field"] == "Quantity"

    async def test_cache_key_is_derived_from_what_was_actually_sent(self, gemini_on, no_embeddings, monkeypatch):
        """The cache key must be built from the described columns, not from the
        raw DataFrame. A key built from column names alone would let a file whose
        values changed completely replay a stale verdict — the exact silent-
        wrong-answer this cache must not be able to produce."""

        seen: dict = {}

        async def _fake_resolve(columns, ai_consent, cache_load=None, cache_save=None, cache_key=None):
            seen["columns"] = columns
            seen["cache_key"] = cache_key
            return tier2_gemini.Tier2Result(source=tier2_gemini.SOURCE_FAILED)

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        await analyse(frame, ai_consent=True, file_id="abc123")

        assert seen["cache_key"]
        assert [c["name"] for c in seen["columns"]] == ["Zorp Factor"]

    async def test_no_cache_key_without_a_file_id(self, gemini_on, no_embeddings, monkeypatch):
        """Tier 2 must still run without a cache — it just cannot reuse anything."""

        seen: dict = {}

        async def _fake_resolve(columns, ai_consent, cache_load=None, cache_save=None, cache_key=None):
            seen["cache_key"] = cache_key
            seen["cache_load"] = cache_load
            return tier2_gemini.Tier2Result(source=tier2_gemini.SOURCE_FAILED)

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Zorp Factor": [3, 5, 2]})
        await analyse(frame, ai_consent=True)

        assert seen["cache_key"] is None
        assert seen["cache_load"] is None


# ── Privacy: the orchestrator must not be the thing that leaks ────────────────


class TestPrivacyAtThePipelineLevel:
    async def test_suppressed_column_values_never_reach_tier2(
        self, gemini_on, no_embeddings, monkeypatch
    ):
        """End-to-end version of the Tier 2 privacy tests: whatever a column's
        label, the orchestrator must hand Tier 2 only what describe_column chose
        to expose. An unmapped free-text column is the highest-risk column in any
        file, and this asserts the pipeline does not accidentally widen that."""

        captured: list[dict] = []

        async def _fake_resolve(columns, ai_consent, **kwargs):
            captured.extend(columns)
            return tier2_gemini.Tier2Result(source=tier2_gemini.SOURCE_FAILED)

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        secret = "Priya Sharma, 9876543210"
        frame = pd.DataFrame({"Zorp Factor": [secret, "Rahul Verma 9123456789"]})
        await analyse(frame, ai_consent=True, file_id="abc123")

        assert captured, "the column should have been escalated"
        assert secret not in json.dumps(captured)
        assert "9876543210" not in json.dumps(captured)
        assert captured[0]["suppressed"] is True

    async def test_tier1_only_columns_are_never_described(self, gemini_on, no_embeddings, monkeypatch):
        """Only escalated columns may have their values read at all. A column the
        local classifier settled must not even be sampled, because sampling is
        what touches the data."""

        captured: list[dict] = []

        async def _fake_resolve(columns, ai_consent, **kwargs):
            captured.extend(columns)
            return tier2_gemini.Tier2Result(source=tier2_gemini.SOURCE_FAILED)

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame(
            {
                "Bill Date": ["01-04-2026", "02-04-2026"],
                "Qty.": [3, 2],
                "Zorp Factor": ["x", "y"],
            }
        )
        await analyse(frame, ai_consent=True, file_id="abc123")

        assert [c["name"] for c in captured] == ["Zorp Factor"]


# ── Collisions ───────────────────────────────────────────────────────────────


class TestCollisions:
    def test_first_claimant_keeps_the_field(self):
        reports = [
            {"raw_column": "Rate", "suggested_field": "Selling Price", "confidence_band": "high"},
            {"raw_column": "Selling Price", "suggested_field": "Selling Price", "confidence_band": "high"},
        ]
        _resolve_collisions(reports)

        assert reports[0]["suggested_field"] == "Selling Price"
        assert reports[1]["suggested_field"] is None
        assert reports[1]["confidence_band"] == "low"
        assert "already mapped" in reports[1]["reason"]

    async def test_collision_across_tiers_is_resolved(self, gemini_on, no_embeddings, monkeypatch):
        """Tier 1 maps Rate, Gemini maps MRP to unit_price — only one can win."""

        async def _fake_resolve(columns, ai_consent, **kwargs):
            return tier2_gemini.Tier2Result(
                verdicts={"MRP": {"label": "unit_price", "confidence": 0.9, "reason": ""}},
                source=tier2_gemini.SOURCE_GEMINI,
            )

        monkeypatch.setattr(tier2_gemini, "resolve_columns", _fake_resolve)

        frame = pd.DataFrame({"Rate": [100, 200], "MRP": [1200, 1500]})
        reports, _t, _n = await analyse(frame, ai_consent=True)

        mapped = [r for r in reports if r["suggested_field"] == "Selling Price"]
        assert len(mapped) == 1


# ── Report shape ─────────────────────────────────────────────────────────────


class TestReportShape:
    async def test_every_column_gets_a_report_in_file_order(self, gemini_off, no_embeddings):
        frame = pd.DataFrame(
            {"Qty.": [1, 2], "Item Name": ["a", "b"], "Weird": ["c", "d"], "Bill Date": ["01-04-2026", "02-04-2026"]}
        )
        reports, _t, _n = await analyse(frame, ai_consent=False)

        assert [r["raw_column"] for r in reports] == list(frame.columns)

    async def test_report_carries_the_legacy_confidence_string(self, gemini_off, no_embeddings):
        """The existing API field must keep its original three values so the
        current frontend badge keeps working unchanged."""
        frame = pd.DataFrame({"Qty.": [1, 2], "Mystery": ["x", "y"]})
        reports, _t, _n = await analyse(frame, ai_consent=False)

        by_name = _by_name(reports)
        assert by_name["Qty."]["confidence"] == "exact"
        assert by_name["Mystery"]["confidence"] == "none"

    async def test_alternatives_are_serialisable(self, gemini_off, no_embeddings):
        frame = pd.DataFrame({"Qty.": [1, 2]})
        reports, _t, _n = await analyse(frame, ai_consent=False)

        json.dumps(reports)  # must not raise on numpy types

    async def test_reports_satisfy_the_api_schema(self, gemini_off, no_embeddings):
        """The upload endpoint does ColumnGuess(**report) on every one of these,
        so a missing or mistyped key is a 500 on upload, not a wrong value. This
        is the test that would have caught the schema drifting from the
        orchestrator."""

        frame = pd.DataFrame(
            {
                "Bill Date": ["01-04-2026", "02-04-2026"],
                "Qty.": [3, 2],
                "Mystery": ["x", "y"],
            }
        )
        reports, timings, _n = await analyse(frame, ai_consent=False)

        from app.models.schemas import ColumnGuess, PipelineTimings

        for report in reports:
            ColumnGuess(**report)  # must not raise

        PipelineTimings(**timings.as_dict())

    async def test_empty_frame_returns_empty(self, gemini_off, no_embeddings):
        reports, _t, _n = await analyse(pd.DataFrame())
        assert reports == []

    async def test_missing_column_value_is_safe(self, gemini_off, no_embeddings):
        frame = pd.DataFrame({"Qty.": [1, None, 3], "Mystery": [None, "b", None]})
        reports, _t, _n = await analyse(frame, ai_consent=False)
        assert len(reports) == 2


class TestLoggingPrivacy:
    async def test_logs_column_names_but_never_values(self, gemini_off, no_embeddings, caplog):
        frame = pd.DataFrame({"Mystery Notes": ["SECRET-CUSTOMER-VALUE", "another"]})
        with caplog.at_level("INFO", logger="senova.pipeline"):
            await analyse(frame, ai_consent=False)

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "Mystery Notes" in logged
        assert "SECRET-CUSTOMER-VALUE" not in logged
        assert "another" not in logged