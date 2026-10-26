"""
The 2-tier column-understanding pipeline, end to end.

Flow
----
::

    raw DataFrame
        └─ Tier 1  classify_columns()          local embeddings + value shape
             ├─ settled columns  ──────────────► keep
             └─ ambiguous columns
                  └─ Tier 2  resolve_columns()  Gemini Flash, gated on consent
                       ├─ verdict ──────────────► keep (source="gemini")
                       └─ anything else ─────────► mark unmapped (source="fallback")
    merged
        └─ translate semantic → canonical, resolve collisions, flag review, choose final route
            ├─ Tier 2 pending/run ──► recompute final state
            └─ ColumnMappingPreview (existing API shape, plus route/review fields)

Guarantees
----------
* **Never raises.** Every stage degrades to a usable result, because a failing
  classifier must not take an upload down with it. The caller gets a complete
  mapping either way.
* **Never lets AI produce a number.** This module only ever emits field *names*.
  Every figure on the dashboard still comes from Pandas.
* **Consent is checked here and in Tier 2.** ``ai_consent`` defaults to ``False``
  everywhere, and it is combined with the operator's ``AI_ASSIST_ENABLED`` before
  Tier 2 is even asked to run.

On collisions
-------------
Two columns can plausibly map to the same canonical field — a file with both
``Rate`` and ``MRP``. Only the first keeps the suggestion; the later one is
demoted to unmapped so the user chooses explicitly. This mirrors the existing
rule in ``detect_column_mapping`` and exists for the same reason: silently
overwriting one column with another corrupts every number downstream, and a
mapping screen is the cheapest place to make the user disambiguate.
"""

from __future__ import annotations

import logging
import time

import pandas as pd

from app.services import ai_cache, ambiguity_engine, mapping_memory, tier1_classifier, tier2_gemini
from app.services.column_catalog import (
    UNKNOWN_LABEL,
    canonical_field_for,
    is_known_label,
)
from app.services.extra_columns import is_personal_pii
from app.services.tier1_classifier import (
    ROUTE_GEMINI,
    ROUTE_LOCAL,
    SOURCE_FALLBACK,
    SOURCE_GEMINI,
    SOURCE_LOCAL,
    ColumnGuess,
)
from app.utils.data_validator import MAPPABLE_FIELDS, _is_pii_header

logger = logging.getLogger("senova.pipeline")

#: Source label for columns settled by the deterministic evidence engine.
SOURCE_EVIDENCE = "evidence"

#: Source label for columns settled by safe mapping memory.
SOURCE_MEMORY = "memory"


class PipelineTimings:
    """Per-stage wall-clock milliseconds, for the upload response and the logs."""

    __slots__ = ("tier1_ms", "evidence_ms", "tier2_ms", "total_ms")

    def __init__(self) -> None:
        self.tier1_ms: float = 0.0
        self.evidence_ms: float = 0.0   # Module 2.1 deterministic engine
        self.tier2_ms: float = 0.0
        self.total_ms: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "tier1_ms": round(self.tier1_ms, 2),
            "evidence_ms": round(self.evidence_ms, 2),
            "tier2_ms": round(self.tier2_ms, 2),
            "total_ms": round(self.total_ms, 2),
        }


async def analyse(
    df: pd.DataFrame,
    ai_consent: bool = False,
    file_id: str | None = None,
    run_tier2: bool = True,
    owner: str | None = None,
) -> tuple[list[dict], PipelineTimings, str | None, str | None]:
    """
    Understand every column in ``df`` and return a mapping report.

    Routing is deliberately computed from the *final pre-Tier-2 state*: Tier 1
    proposes a meaning, collision resolution can demote a previously-local
    suggestion, and only then do we decide whether Gemini should get a second
    look. This is important because a collision is itself a reason to review the
    column.
    """
    overall = time.perf_counter()
    timings = PipelineTimings()

    # ── Tier 1 ──────────────────────────────────────────────────────────────
    tier1_started = time.perf_counter()
    ai_available = tier2_gemini.gemini_enabled()
    guesses = tier1_classifier.classify_columns(df, ai_available=ai_available)
    timings.tier1_ms = (time.perf_counter() - tier1_started) * 1000.0

    reports: dict[str, dict] = {
        guess.raw_column: _report(guess) for guess in guesses
    }

    # Collision resolution and review flags MUST happen before the final route is
    # chosen. A local suggestion may become unresolved here.
    ordered = [reports[str(column)] for column in df.columns]
    _resolve_collisions(ordered)
    _flag_for_review(ordered)
    _set_final_routes(ordered, ai_available=ai_available, ai_consent=ai_consent)

    # ── Evidence Engine (Module 2.1) & Safe Mapping Memory (Module 2.3) ─────
    # Run AFTER Tier 1 and collision resolution, but BEFORE Tier 2 escalation.
    # Only processes columns that Tier 1 couldn't settle (needs_review=True,
    # not recognised_unused). Columns settled deterministically or by safe memory
    # are routed locally so they never consume a Gemini slot.
    evidence_started = time.perf_counter()
    _apply_evidence_and_memory(
        ordered, df, owner=owner, ai_available=ai_available, ai_consent=ai_consent
    )
    timings.evidence_ms = (time.perf_counter() - evidence_started) * 1000.0
    # After evidence or memory may have settled some columns, recompute flags
    # and routes so collision resolution is aware of the new state.
    _resolve_collisions(ordered)
    _flag_for_review(ordered)
    _set_final_routes(ordered, ai_available=ai_available, ai_consent=ai_consent)

    # ── Tier 2 ──────────────────────────────────────────────────────────────
    notice: str | None = None
    reason_code: str | None = None
    review_candidates = [
        report for report in ordered
        if report.get("needs_review") and not report.get("recognised_unused")
    ]

    # Even when AI cannot run, a row that needs review must never be described as
    # "AI not needed". The API carries the honest reason for the frontend banner.
    if review_candidates and not ai_available:
        notice = "AI help is off."
        reason_code = "disabled"
    elif review_candidates and not ai_consent:
        notice = "AI help was not approved for this upload."
        reason_code = "no_consent"

    escalated = [
        report for report in ordered
        if report.get("route") == ROUTE_GEMINI
        and not report.get("recognised_unused")
    ]

    if escalated and run_tier2:
        columns = [
            tier2_gemini.describe_column(
                df[report["raw_column"]],
                report["raw_column"],
                report.get("semantic_label", UNKNOWN_LABEL),
            )
            for report in escalated
        ]

        cache_key = ai_cache.build_key(columns) if file_id else None
        cache_load = (lambda key: ai_cache.load(file_id, key)) if file_id else None
        cache_save = (lambda key, verdicts: ai_cache.save(file_id, key, verdicts)) if file_id else None

        result = await tier2_gemini.resolve_columns(
            columns,
            ai_consent=ai_consent,
            cache_load=cache_load,
            cache_save=cache_save,
            cache_key=cache_key,
        )
        timings.tier2_ms = result.elapsed_ms
        notice = result.notice
        reason_code = result.reason_code

        _apply_tier2_reports(ordered, result, df)

        # Gemini may introduce a second collision or clear the review. Recompute
        # the final state and route once more so the response is self-consistent.
        _resolve_collisions(ordered)
        _flag_for_review(ordered)
        _set_final_routes(ordered, ai_available=ai_available, ai_consent=ai_consent)
    elif escalated:
        # Upload step intentionally defers Tier 2. Mark the final route so the
        # frontend can make the background request.
        for report in escalated:
            report["source"] = "pending"

    elif not run_tier2:
        # Nothing needs Tier 2 and no notice is necessary.
        pass

    timings.total_ms = (time.perf_counter() - overall) * 1000.0

    _log_summary(ordered, timings, ai_consent, ai_available)
    return ordered, timings, notice, reason_code


def _apply_tier2_reports(
    reports: list[dict],
    result: tier2_gemini.Tier2Result,
    df: pd.DataFrame | None = None,
) -> None:
    """Fold Tier 2 verdicts into the already collision-resolved reports."""
    from app.services.extra_columns import is_personal_pii

    for report in reports:
        col_name = report["raw_column"]
        series = df[col_name] if df is not None and col_name in df.columns else pd.Series(dtype=object)
        if is_personal_pii(col_name, series):
            report["semantic_label"] = "personal"
            report["suggested_field"] = None
            report["confidence_band"] = "low"
            report["confidence_score"] = 0.0
            report["source"] = SOURCE_LOCAL
            report["route"] = ROUTE_LOCAL
            report["reason"] = "Personal / contact data (PII) preserved as stored-only; values redacted and never offered as filter or axis."
            continue

        if report.get("route") != ROUTE_GEMINI or report.get("recognised_unused"):
            continue

        verdict = result.verdicts.get(report["raw_column"])
        if not verdict or result.source in (tier2_gemini.SOURCE_FAILED, "local"):
            report["semantic_label"] = UNKNOWN_LABEL
            report["suggested_field"] = None
            report["source"] = "local" if result.source == "local" else SOURCE_FALLBACK
            report["confidence_band"] = "low"
            report["confidence_score"] = 0.0
            if result.source == "local":
                report["reason"] = "AI was not approved for this upload, so we left this for you to map."
            else:
                report["reason"] = "We couldn't identify this column automatically — please choose what it is."
            continue

        label = verdict["label"]
        canonical = canonical_field_for(label, raw_header=report["raw_column"])
        score = float(verdict.get("confidence", 0.0))

        report["semantic_label"] = label
        report["suggested_field"] = canonical
        report["confidence_score"] = round(score, 4)
        report["confidence_band"] = _band(score)
        report["source"] = (
            SOURCE_GEMINI
            if result.source in (tier2_gemini.SOURCE_GEMINI, tier2_gemini.SOURCE_CACHE)
            else SOURCE_LOCAL
        )
        report["reason"] = (
            f"AI read this as {label.replace('_', ' ')}"
            + (f" — {verdict['reason']}" if verdict.get("reason") else "")
        )[:200]

        if label == UNKNOWN_LABEL or not is_known_label(label):
            report["suggested_field"] = None
            report["confidence_band"] = "low"




def _set_final_routes(
    reports: list[dict],
    *,
    ai_available: bool,
    ai_consent: bool,
) -> None:
    """Compute Tier 2 routing from the final post-collision review state."""
    for report in reports:
        if report.get("recognised_unused"):
            report["route"] = ROUTE_LOCAL
            continue

        needs_review = bool(report.get("needs_review"))
        if needs_review and ai_available and ai_consent:
            report["route"] = ROUTE_GEMINI
            if report.get("source") == SOURCE_LOCAL:
                report["reason"] = (
                    report.get("reason") or "Needs a second opinion."
                ) + " AI can take a second look."
        else:
            report["route"] = ROUTE_LOCAL


def _resolve_collisions(reports: list[dict]) -> list[dict]:
    """
    Enforce one canonical field per column name.

    Mirrors ``detect_column_mapping``: the first column to claim a field keeps
    it, and any later column claiming the same field is demoted to unmapped so
    the user decides rather than us silently dropping one.
    """
    claimed: set[str] = set()
    for report in reports:
        field = report.get("suggested_field")
        if not field:
            continue
        if field in claimed:
            report["suggested_field"] = None
            report["confidence_band"] = "low"
            report["reason"] = (
                f"Another column is already mapped to {field}. Choose which one to keep."
            )
        else:
            claimed.add(field)
    return reports


def _flag_for_review(reports: list[dict]) -> None:
    """
    Decide, from the *final* state of each column, whether the user must look at it.

    This runs once at the end, after both tiers and collision resolution, because
    any of those three can change the answer: Gemini can settle a column Tier 1
    escalated, and collision resolution can demote a column that looked fine a
    moment earlier. Deriving the flag earlier — from Tier 1's routing decision —
    left a confidently-resolved AI column highlighted for review and, worse, a
    collision-demoted column with ``needs_review`` still false, which is exactly
    the "unmapped but looks settled" failure this pipeline exists to prevent.
    """
    for report in reports:
        recognised_unused = report.get("semantic_label") in {"currency", "status", "notes", "personal"}
        report["recognised_unused"] = recognised_unused
        report["needs_review"] = (
            not recognised_unused and (
                not report.get("suggested_field")
                or report.get("confidence_band") == "low"
                or report.get("source") == SOURCE_FALLBACK
                or bool(report.get("memory_conflict"))
            )
        )


def _band(score: float) -> str:
    """Confidence band for the UI badge. Kept in one place so the thresholds
    the badge uses can never drift from the ones the API reports."""
    if score >= 0.9:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _report(guess: ColumnGuess) -> dict:
    """
    Render one ``ColumnGuess`` into the existing report shape.

    ``confidence`` keeps its original ``exact``/``fuzzy``/``none`` string because
    ``ColumnGuess.confidence`` and the frontend's ``ConfidenceBadge`` both already
    depend on it — changing the type would break existing consumers for no gain.
    The new ``confidence_score`` and ``confidence_band`` carry the granularity,
    and ``exact``/``fuzzy`` keep their established meanings: we are certain of
    this field name, versus we are showing a keyword-derived suggestion.
    """
    if guess.score >= 1.0 and guess.canonical:
        legacy_confidence = "exact"
    elif guess.canonical:
        legacy_confidence = "fuzzy"
    else:
        legacy_confidence = "none"

    return {
        "raw_column": guess.raw_column,
        "suggested_field": guess.canonical,
        "confidence": legacy_confidence,
        "confidence_score": round(float(guess.score), 4),
        "confidence_band": _band(float(guess.score)),
        "margin": round(float(guess.margin), 4),
        "route": guess.route,
        "source": guess.source,
        "semantic_label": guess.label,
        "reason": guess.reason,
        "alternatives": [{"label": label, "score": score} for label, score in guess.alternatives],
        # Provisional. ``_flag_for_review`` recomputes this from the final state
        # once Tier 2 and collision resolution have both had their say.
        "needs_review": not guess.canonical,
    }


def _apply_evidence_and_memory(
    reports: list[dict],
    df: pd.DataFrame,
    owner: str | None = None,
    ai_available: bool = False,
    ai_consent: bool = False,
) -> None:
    """
    Evaluates ambiguous columns using the Module 2.1 Deterministic Evidence Rules
    Engine and Module 2.3 Safe Mapping Memory.

    Precedence:
    1. PII columns (headers or cell values) are strictly shielded as stored-only.
       Neither deterministic evidence nor saved memory is permitted to assign
       a canonical role to personal data.
    2. Decisive statistical evidence ("auto") takes precedence over memory.
       If saved memory contradicts decisive evidence, memory is rejected and
       the column is flagged for user review.
    3. If evidence is ambiguous/neutral ("ask") and valid, non-colliding memory exists,
       the column is settled locally using memory (source="memory", route="local", skipping Tier 2).
    4. If evidence is ambiguous and no memory exists, evidence facts and candidates are
       preserved for the Grouped Clarification Dialog / Tier 2.
    """
    already_mapped: dict[str, str] = {
        r["raw_column"]: r["suggested_field"]
        for r in reports
        if r.get("suggested_field")
    }

    candidates = [
        r["raw_column"]
        for r in reports
        if r.get("needs_review") and not r.get("recognised_unused")
    ]

    if not candidates:
        return

    # Load owner's memory for this template, if owner is provided
    memory_mappings: dict[str, str] = {}
    colliding_tokens: set[str] = set()
    if owner:
        template_sig = mapping_memory.compute_template_signature(df.columns)
        colliding_tokens = mapping_memory.get_colliding_tokens(df.columns)
        memory_mappings = mapping_memory.load_template_mappings(owner, template_sig, colliding_tokens)

    evidence_results = ambiguity_engine.evaluate_batch(candidates, df, already_mapped)

    for report in reports:
        col = report["raw_column"]
        if col not in candidates:
            continue

        # Rule 0: PII Shield
        series = df[col] if col in df.columns else pd.Series(dtype=object)
        if _is_pii_header(col):
            report["semantic_label"] = "personal"
            report["suggested_field"] = None
            report["confidence_score"] = 0.0
            report["confidence_band"] = "low"
            report["source"] = SOURCE_LOCAL
            report["route"] = ROUTE_LOCAL
            report["needs_review"] = False
            report["reason"] = (
                "Personal / contact data (PII) preserved as stored-only; values redacted "
                "and never offered as filter or axis."
            )
            continue

        norm_col = mapping_memory.normalize_header(col)
        mem_target = memory_mappings.get(norm_col) if norm_col not in colliding_tokens else None
        has_pii_values = is_personal_pii(col, series)
        if has_pii_values:
            # Personal data in cell values: memory and evidence must NEVER map this column
            mem_target = None
            if not (ai_available and ai_consent):
                report["semantic_label"] = "personal"
                report["suggested_field"] = None
                report["confidence_score"] = 0.0
                report["confidence_band"] = "low"
                report["source"] = SOURCE_LOCAL
                report["route"] = ROUTE_LOCAL
                report["needs_review"] = False
                report["reason"] = (
                    "Personal / contact data (PII) preserved as stored-only; values redacted "
                    "and never offered as filter or axis."
                )
                continue

        result = evidence_results.get(col) if not has_pii_values else None

        if result is not None and result.decision == "auto":
            # Decisive evidence verdict
            if mem_target is not None and result.canonical is not None and mem_target != result.canonical:
                # Contradiction: evidence contradicts saved memory. Reject memory, flag for review!
                report["suggested_field"] = result.canonical
                report["semantic_label"] = result.semantic or report.get("semantic_label", UNKNOWN_LABEL)
                report["confidence_score"] = round(result.confidence, 4)
                report["confidence_band"] = _band(result.confidence)
                report["source"] = SOURCE_EVIDENCE
                report["route"] = ROUTE_LOCAL
                report["memory_conflict"] = True
                report["needs_review"] = True
                report["reason"] = (
                    f"Data evidence indicates '{result.canonical}' ({result.reason}), "
                    f"which differs from saved memory '{mem_target}'. Please review."
                )
                report["evidence_facts"] = result.evidence
                report["evidence_candidates"] = [result.canonical, mem_target]
            else:
                # Evidence accepted cleanly
                report["suggested_field"] = result.canonical
                report["semantic_label"] = result.semantic or report.get("semantic_label", UNKNOWN_LABEL)
                report["confidence_score"] = round(result.confidence, 4)
                report["confidence_band"] = _band(result.confidence)
                report["source"] = SOURCE_EVIDENCE
                report["route"] = ROUTE_LOCAL
                report["reason"] = result.reason
                report["needs_review"] = False
                report["evidence_facts"] = result.evidence
                report["evidence_candidates"] = result.candidates
        elif mem_target is not None and mem_target in MAPPABLE_FIELDS:
            # Evidence is not decisive ("ask" or None) and compatible memory exists: settle from memory!
            report["suggested_field"] = mem_target
            report["confidence_score"] = 0.95
            report["confidence_band"] = "high"
            report["source"] = SOURCE_MEMORY
            report["route"] = ROUTE_LOCAL
            report["needs_review"] = False
            report["reason"] = "Recalled from saved mapping memory for this template."
            if result is not None and result.candidates:
                report["evidence_candidates"] = result.candidates
                report["evidence_facts"] = result.evidence
        else:
            # Indeterminate evidence and no memory: preserve evidence candidates for dialog / Tier 2
            if result is not None and result.candidates:
                report["evidence_candidates"] = result.candidates
                report["evidence_reason"] = result.reason
                report["evidence_facts"] = result.evidence


def _log_summary(
    reports: list[dict],
    timings: PipelineTimings,
    ai_consent: bool,
    ai_available: bool,
) -> None:
    """
    Log what happened — counts and timings only.

    Column *names* are logged because a shopkeeper needs to be able to report
    "it got my 'Kitne' column wrong", and a header is not personal data the way
    its contents are. Column *values* never appear in a log line from this
    module.
    """
    counts: dict[str, int] = {}
    for report in reports:
        counts[report["source"]] = counts.get(report["source"], 0) + 1

    logger.info(
        "Column pipeline: tier1=%.1fms evidence=%.1fms tier2=%.1fms total=%.1fms "
        "sources=%s ai_available=%s consent=%s",
        timings.tier1_ms,
        timings.evidence_ms,
        timings.tier2_ms,
        timings.total_ms,
        counts,
        ai_available,
        ai_consent,
    )

    unresolved = [report["raw_column"] for report in reports if not report["suggested_field"]]
    if unresolved:
        logger.info(
            "Columns left for manual mapping (%d): %s",
            len(unresolved),
            ", ".join(unresolved[:25]),
        )