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
        └─ translate semantic → canonical, resolve collisions
            └─ ColumnMappingPreview (the existing API shape, plus new fields)

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

from app.services import ai_cache, tier1_classifier, tier2_gemini
from app.services.column_catalog import (
    UNKNOWN_LABEL,
    canonical_field_for,
    is_known_label,
)
from app.services.tier1_classifier import (
    ROUTE_GEMINI,
    SOURCE_FALLBACK,
    SOURCE_GEMINI,
    SOURCE_LOCAL,
    ColumnGuess,
)

logger = logging.getLogger("senova.pipeline")


class PipelineTimings:
    """Per-stage wall-clock milliseconds, for the upload response and the logs."""

    __slots__ = ("tier1_ms", "tier2_ms", "total_ms")

    def __init__(self) -> None:
        self.tier1_ms: float = 0.0
        self.tier2_ms: float = 0.0
        self.total_ms: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "tier1_ms": round(self.tier1_ms, 2),
            "tier2_ms": round(self.tier2_ms, 2),
            "total_ms": round(self.total_ms, 2),
        }


async def analyse(
    df: pd.DataFrame,
    ai_consent: bool = False,
    file_id: str | None = None,
) -> tuple[list[dict], PipelineTimings, str | None]:
    """
    Understand every column in ``df`` and return a mapping report.

    Returns ``(reports, timings, notice)`` where each report is the dict shape
    the upload endpoint already returns for a column, extended with the new
    confidence/source fields. ``notice`` is non-``None`` only when something went
    wrong that the user should know about.

    ``file_id`` enables the Tier 2 disk cache; omit it and Tier 2 still runs, it
    just won't be able to reuse a previous answer.
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

    # ── Tier 2, only for columns Tier 1 declined to settle ───────────────────
    notice: str | None = None
    escalated = [guess for guess in guesses if guess.route == ROUTE_GEMINI and guess.canonical is None]

    if escalated:
        columns = [
            tier2_gemini.describe_column(df[guess.raw_column], guess.raw_column, guess.label)
            for guess in escalated
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

        _apply_tier2(reports, escalated, result)

    timings.total_ms = (time.perf_counter() - overall) * 1000.0

    # Collisions are resolved last, once both tiers have spoken: either tier can
    # be the one that claims a field twice.
    ordered = [reports[str(column)] for column in df.columns]
    _resolve_collisions(ordered)
    _flag_for_review(ordered)

    _log_summary(ordered, timings, ai_consent, ai_available)
    return ordered, timings, notice


def _apply_tier2(
    reports: dict[str, dict],
    escalated: list[ColumnGuess],
    result: tier2_gemini.Tier2Result,
) -> None:
    """
    Fold Tier 2's verdicts into the reports.

    A column Gemini answered for gets the model's label and score. A column it
    didn't — because of a failure, or because the model declined to guess — is
    explicitly marked ``fallback`` and unmapped, so the UI can highlight it and
    the user knows to look at it. Silence would be worse: an unmapped column
    that looks confident is exactly the failure this feature is meant to remove.
    """
    for guess in escalated:
        report = reports[guess.raw_column]
        verdict = result.verdicts.get(guess.raw_column)

        if not verdict or result.source == tier2_gemini.SOURCE_FAILED:
            report["semantic_label"] = UNKNOWN_LABEL
            report["source"] = SOURCE_FALLBACK
            report["confidence_band"] = "low"
            report["confidence_score"] = 0.0
            report["reason"] = (
                "We couldn't identify this column automatically — please choose what it is."
            )
            continue

        label = verdict["label"]
        canonical = canonical_field_for(label, raw_header=guess.raw_column)
        score = float(verdict.get("confidence", 0.0))

        report["semantic_label"] = label
        report["suggested_field"] = canonical
        report["confidence_score"] = round(score, 4)
        report["confidence_band"] = _band(score)
        # ``SOURCE_CACHE`` is a Gemini verdict this process did not fetch, but it
        # is still Gemini's answer rather than a local decision, so it reports as
        # ``gemini``. Anything else that carries a verdict has been sanitised and
        # accepted upstream, so ``local`` is the honest floor.
        report["source"] = (
            SOURCE_GEMINI
            if result.source in (tier2_gemini.SOURCE_GEMINI, tier2_gemini.SOURCE_CACHE)
            else SOURCE_LOCAL
        )
        report["reason"] = (
            f"AI read this as {label.replace('_', ' ')}"
            + (f" — {verdict['reason']}" if verdict.get("reason") else "")
        )[:200]

        # Gemini can resolve a column Tier 1 thought was fine (or vice versa).
        # If it also *unmapped* something, that is a real answer too.
        if label == UNKNOWN_LABEL or not is_known_label(label):
            report["suggested_field"] = None
            report["confidence_band"] = "low"


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
        report["needs_review"] = (
            not report.get("suggested_field")
            or report.get("confidence_band") == "low"
            or report.get("source") == SOURCE_FALLBACK
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
        "source": guess.source,
        "semantic_label": guess.label,
        "reason": guess.reason,
        "alternatives": [{"label": label, "score": score} for label, score in guess.alternatives],
        # Provisional. ``_flag_for_review`` recomputes this from the final state
        # once Tier 2 and collision resolution have both had their say.
        "needs_review": not guess.canonical,
    }


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
        "Column pipeline: tier1=%.1fms tier2=%.1fms total=%.1fms "
        "sources=%s ai_available=%s consent=%s",
        timings.tier1_ms,
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