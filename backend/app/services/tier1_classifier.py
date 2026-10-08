"""
Tier 1 — local column classification, and the routing decision it drives.

How a column is scored
----------------------
Two independent signals, blended:

* **Header similarity** — cosine distance between the embedded column header and
  the embedded catalog anchors, taking the best anchor per label. This is what
  recognises ``"Kitne"`` as quantity or ``"Purchase Rate"`` as cost.
* **Value-shape fit** — how well the column's *values* match what that label
  implies. A column called "Amount" whose values are 87% parseable as dates is
  much more likely to be a date column than a revenue one, and no amount of
  header text should override the evidence of the data itself.

``score = TIER1_HEADER_WEIGHT * header + TIER1_STATS_WEIGHT * stats``

Routing: confidence **and** margin
----------------------------------
A column is accepted locally only when it clears ``HIGH_CONF_THRESHOLD`` *and*
its top two labels are at least ``AMBIGUITY_MARGIN`` apart. The margin rule is
the important half. ``MRP`` scores highly against *both* ``mrp`` and
``unit_price`` — the two genuinely are similar concepts, and the whole point of
this feature is to stop guessing between them. A high top-1 score with a tiny
margin means "two readings fit this header about equally well", which is
exactly when a second opinion is worth paying for.

Degradation
-----------
``FASTEMBED_ENABLED=false``, a missing model, or a failed embed all route every
column through the pre-existing alias map + fuzzy keyword heuristic
(``data_validator.guess_canonical_column``). The pipeline keeps working; it just
loses the embedding signal. Existing exact alias hits still win outright, since
they are precise and free.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.config import (
    AMBIGUITY_MARGIN,
    FASTEMBED_ENABLED,
    HIGH_CONF_THRESHOLD,
    TIER1_HEADER_WEIGHT,
    TIER1_STATS_WEIGHT,
)
from app.services import embedder
from app.services.column_catalog import SEMANTIC_LABELS, UNKNOWN_LABEL
from app.services.pii_mask import shape_stats
from app.utils.data_validator import guess_canonical_column

logger = logging.getLogger("senova.tier1")

# ── Semantic label → canonical field, for the alias-map fallback ─────────────
#
# The legacy guesser answers in canonical field names. Tier 1 answers in semantic
# labels. This inverts the existing alias map so both tiers speak one language
# downstream: canonical "Selling Price" becomes semantic "unit_price", canonical
# "Line Total" becomes "revenue", and so on.
#
# Deliberately not the full 17: canonical fields with no semantic equivalent
# (Stock On Hand, Payment Mode, Salesperson, Brand, Size, Colour) still resolve
# through the alias map in fallback mode and are translated *back* to canonical
# immediately by ``column_understanding``. Keeping this map small and honest
# avoids pretending those fields have a meaning-layer representation.

#: Canonical field → the semantic label that produces it.
_CANONICAL_TO_SEMANTIC: dict[str, str] = {
    "Date": "date",
    "Category": "category",
    "Item": "product",
    "Quantity": "quantity",
    "Selling Price": "unit_price",
    "Cost Price": "cost",
    "Line Total": "revenue",
    "Discount": "discount",
    "Tax": "tax",
    "Customer": "customer",
    "Branch": "region",
    "Invoice No": "id",
    "MRP": "mrp",
}

#: Where a canonical field the alias map can return, but which has no semantic
#: label, should land once translated into the meaning layer. Keeping them as
#: ``None`` lets ``column_understanding`` pass them straight through to the
#: canonical mapping untouched, which is what preserves today's behaviour for
#: Stock On Hand / Payment Mode / etc. in fallback mode.
_PASSTHROUGH_CANONICAL: frozenset[str] = frozenset(
    {"Stock On Hand", "Payment Mode", "Salesperson", "Brand", "Size", "Colour"}
)


def _semantic_from_canonical(canonical: str | None) -> str | None:
    """Invert one alias-map answer into a semantic label."""
    if not canonical:
        return None
    if canonical in _CANONICAL_TO_SEMANTIC:
        return _CANONICAL_TO_SEMANTIC[canonical]
    if canonical in _PASSTHROUGH_CANONICAL:
        return None
    return UNKNOWN_LABEL


#: Headers the legacy alias map resolves confidently but *wrongly*.
#: (Currently empty since MRP has been corrected in the alias map).
_ALIAS_MAP_CONFLICTS: frozenset[str] = frozenset()


# ── Result types ─────────────────────────────────────────────────────────────

#: How the pipeline arrived at a column's meaning.
SOURCE_LOCAL = "local"
SOURCE_GEMINI = "gemini"
SOURCE_FALLBACK = "fallback"

#: Where the decision goes next.
ROUTE_LOCAL = "local"
ROUTE_GEMINI = "gemini"


@dataclass
class ColumnGuess:
    """
    Tier 1's verdict for one column.

    ``label`` is the semantic meaning (or ``"other"``). ``canonical`` is the
    SENOVA field name it maps to, or ``None`` when we recognise the meaning but
    have nowhere to put it — ``mrp``, ``status`` and ``notes`` all land there, and
    that is a real answer the UI shows as "recognised, not analysed", not a
    failure.
    """

    raw_column: str
    label: str = UNKNOWN_LABEL
    canonical: str | None = None
    score: float = 0.0
    margin: float = 0.0
    route: str = ROUTE_LOCAL
    source: str = SOURCE_LOCAL
    #: Human-readable reason for the route, surfaced in the API response so a
    #: surprising mapping can be explained without reading server logs.
    reason: str = ""
    #: Runner-up label and score, for the UI's "we also considered…" affordance.
    alternatives: list[tuple[str, float]] = field(default_factory=list)


#: Below this header similarity there is no usable textual evidence for any
#: label, and the classifier reports ``other`` rather than guessing.
#:
#: This is about what the shape signal is and isn't allowed to do. Value shape can
#: *refute* a label — a column of dates is not a cost column, a column of numbers
#: is not a customer column — but it can never *positively identify* one. Nothing
#: in "87% of these values parse as numbers" distinguishes revenue from cost from
#: tax, and nothing in "these values are words" distinguishes a customer column
#: from a status column. So shape only ever adjusts a label the header proposed.
#:
#: Without this floor a header the model has never seen ("Some Vendor Specific
#: Column") would tie every textual label and win by catalog order — reporting a
#: confident, wrong answer instead of an honest "don't know".
MIN_HEADER_SIMILARITY = 0.15


# ── Value-shape fit ──────────────────────────────────────────────────────────

#: Which shape each label expects, and how strongly to reward matching it.
#
# Represented as (numeric_ratio_ideal, date_ratio_ideal). A label's fit is 1.0
# when the column's measured ratios match its expectation and falls off from
# there, so a date column whose values are 0% dates scores badly for ``date`` even
# if its header says "Date".
_EXPECTED_SHAPE: dict[str, tuple[float, float]] = {
    "date": (0.0, 1.0),
    "quantity": (1.0, 0.0),
    "unit_price": (1.0, 0.0),
    "mrp": (1.0, 0.0),
    "cost": (1.0, 0.0),
    "revenue": (1.0, 0.0),
    "discount": (1.0, 0.0),
    "tax": (1.0, 0.0),
    "id": (0.0, 0.0),
    "product": (0.0, 0.0),
    "category": (0.0, 0.0),
    "customer": (0.0, 0.0),
    "region": (0.0, 0.0),
    "status": (0.0, 0.0),
    "notes": (0.0, 0.0),
    "other": (0.0, 0.0),
}


def _shape_fit(label: str, stats: dict[str, float | bool]) -> float:
    """
    How well a column's value shape matches what ``label`` implies, in ``[0, 1]``.

    Two components:

    * **Numeric/date agreement** — the measured ``numeric_ratio`` and
      ``date_parse_ratio`` compared against the label's expectation.
    * **Textualness** — ``product``, ``category``, ``status``, ``notes``,
      ``customer`` and ``region`` are all labels whose values are text, so a
      column that is overwhelmingly numeric is evidence *against* them. This is
      what stops a numeric column of stock codes being called ``customer``.

    Note what is deliberately absent: ``unique_ratio`` does not participate.
    High cardinality is a weak signal that misfires on genuine dates (every
    value unique) and on serial invoice numbers.
    """
    expected_numeric, expected_date = _EXPECTED_SHAPE.get(label, (0.0, 0.0))
    numeric_ratio = float(stats.get("numeric_ratio", 0.0) or 0.0)
    date_ratio = float(stats.get("date_parse_ratio", 0.0) or 0.0)

    numeric_agreement = 1.0 - min(abs(numeric_ratio - expected_numeric), 1.0)
    date_agreement = 1.0 - min(abs(date_ratio - expected_date), 1.0)

    if expected_numeric == 0.0 and expected_date == 0.0:
        # A textual label: reward *not* being a number and *not* being a date.
        # ``numeric_ratio`` alone suffices, since a date column is 0% numeric and
        # would otherwise look perfectly textual.
        return numeric_agreement

    return (numeric_agreement + date_agreement) / 2.0


# ── Header similarity ────────────────────────────────────────────────────────


def _header_scores(headers: list[str]) -> dict[str, dict[str, float]] | None:
    """
    Cosine similarity of each header against every catalog label.

    Returns ``{header: {label: best_score}}``, or ``None`` when the embedder is
    unavailable so the caller can take the alias-map path.
    """
    matrix, labels = embedder.catalog_embeddings()
    if matrix is None or labels is None:
        return None

    header_vectors = embedder.encode(headers)
    if header_vectors is None:
        return None

    # Both matrices are unit-length, so the dot product is cosine similarity.
    similarity = header_vectors @ matrix.T

    labels_arr = np.array(labels)
    results: dict[str, dict[str, float]] = {}

    label_maxes: dict[str, np.ndarray] = {}
    for label in SEMANTIC_LABELS:
        indices = np.where(labels_arr == label)[0]
        if len(indices) > 0:
            label_maxes[label] = similarity[:, indices].max(axis=1)

    for row_index, header in enumerate(headers):
        results[header] = {
            label: float(label_maxes[label][row_index])
            for label in SEMANTIC_LABELS
            if label in label_maxes
        }
    return results


def _normalise_header(raw_column: str) -> str:
    """
    Clean a header for embedding and for the alias map.

    Strips whitespace and a leading BOM (both common in exports from Indian POS
    software) and collapses internal runs of separators to single spaces, so
    ``"  BILL   DATE  "`` and ``"Bill Date"`` are the same string to both the
    embedder and the alias map.
    """
    import re

    cleaned = str(raw_column).replace("\ufeff", "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


# ── Routing ──────────────────────────────────────────────────────────────────


def _route(
    top_score: float,
    margin: float,
    high_threshold: float,
    margin_threshold: float,
) -> tuple[str, str]:
    """
    Decide whether a column is settled locally or needs a second opinion.

    Returns ``(route, reason)``. The reason strings are surfaced in the API
    response, so they are written to be read by a shop owner looking at the
    mapping screen rather than by a developer reading a stack trace.
    """
    if top_score < high_threshold:
        return ROUTE_GEMINI, "Low confidence in the local match."
    if margin < margin_threshold:
        return (
            ROUTE_GEMINI,
            "Two meanings fit this header about equally well — needs a second opinion.",
        )
    return ROUTE_LOCAL, "Clear local match."


# ── Public entry point ───────────────────────────────────────────────────────


def classify_columns(df: pd.DataFrame, ai_available: bool = False) -> list[ColumnGuess]:
    """
    Classify every column in ``df`` and decide, per column, whether to escalate.

    ``ai_available`` tells the classifier whether Tier 2 will actually be able to
    run. It matters for one decision only: a column that would normally escalate
    stays local, with its keyword-heuristic suggestion, when there is nothing to
    escalate to. That keeps behaviour identical to today in the
    ``AI_ASSIST_ENABLED=false`` / ``FASTEMBED_ENABLED=false`` configuration.

    Never raises. If the embedding path is unavailable — ``FASTEMBED_ENABLED`` is
    false, ``fastembed`` isn't installed, the model won't download — every column
    falls back to the pre-existing alias map, and the pipeline proceeds exactly as
    it did before this feature existed.
    """
    headers = [str(column) for column in df.columns]
    if not headers:
        return []

    if not FASTEMBED_ENABLED:
        return [_alias_fallback_guess(header, ai_available) for header in headers]

    try:
        similarity = _header_scores([_normalise_header(header) for header in headers])
    except Exception as exc:  # defensive: embedding must never break an upload
        logger.warning("Tier 1 header scoring failed (%s: %s).", type(exc).__name__, exc)
        similarity = None

    if similarity is None:
        return [_alias_fallback_guess(header, ai_available) for header in headers]

    guesses: list[ColumnGuess] = []
    for raw_column in headers:
        guesses.append(
            _score_one(
                raw_column,
                df[raw_column],
                similarity.get(_normalise_header(raw_column), {}),
                ai_available,
            )
        )
    return guesses


def _score_one(
    raw_column: str,
    series: pd.Series,
    scores: dict[str, float],
    ai_available: bool = False,
) -> ColumnGuess:
    """Score a single column against the header similarities and its value shape."""
    stats = shape_stats(series)

    best_header_similarity = max(scores.values()) if scores else 0.0

    # No usable textual evidence: report ``other`` rather than letting the shape
    # signal pick a label it has no power to identify. See MIN_HEADER_SIMILARITY.
    if best_header_similarity <= MIN_HEADER_SIMILARITY:
        escalating = ai_available
        return ColumnGuess(
            raw_column=raw_column,
            label=UNKNOWN_LABEL,
            canonical=None,
            score=0.0,
            margin=0.0,
            route=ROUTE_GEMINI if escalating else ROUTE_LOCAL,
            source=SOURCE_LOCAL,
            reason=(
                "This heading isn't one we recognise."
                if escalating
                else "This heading isn't one we recognise — please map it by hand."
            ),
        )

    # Score every label, not a header-only shortlist. The shape signal has to be
    # in the ranking, not applied afterwards: picking the shortlist on header
    # similarity alone meant a column whose heading the model didn't recognise was
    # decided by catalog order, which is how a "Total" column full of dates ends
    # up reported as revenue.
    combined: list[tuple[str, float]] = []
    for label, header_score in scores.items():
        header_score = max(0.0, header_score)
        stats_score = _shape_fit(label, stats)
        combined.append(
            (label, TIER1_HEADER_WEIGHT * header_score + TIER1_STATS_WEIGHT * stats_score)
        )

    combined.sort(key=lambda pair: pair[1], reverse=True)

    if not combined:
        return _alias_fallback_guess(raw_column, ai_available)

    top_label, top_score = combined[0]
    runner_up_score = combined[1][1] if len(combined) > 1 else 0.0
    margin = top_score - runner_up_score

    # An exact alias-map hit is precise and free, so it short-circuits the
    # embedding score. This is also what keeps the previous behaviour bit-for-bit
    # for every file that already mapped cleanly.
    #
    # Two exclusions: headers the legacy map is known to get wrong (``mrp``), and
    # the case where there's nowhere to escalate to anyway.
    alias_canonical, alias_confidence = guess_canonical_column(raw_column)
    if alias_confidence == "exact" and _normalise_header(raw_column).lower() not in _ALIAS_MAP_CONFLICTS:
        alias_label = _semantic_from_canonical(alias_canonical)
        if alias_label:
            return ColumnGuess(
                raw_column=raw_column,
                label=alias_label,
                canonical=alias_canonical,
                score=1.0,
                margin=1.0,
                route=ROUTE_LOCAL,
                source=SOURCE_LOCAL,
                reason="Matched a known column name exactly.",
            )

    route, reason = _route(top_score, margin, HIGH_CONF_THRESHOLD, AMBIGUITY_MARGIN)
    if top_label in {"currency", "status", "notes"}:
        route = ROUTE_LOCAL
        reason = "Recognised, not analysed. You can still map it by hand."

    if not ai_available and route == ROUTE_GEMINI:
        route = ROUTE_LOCAL
        reason += " AI disambiguation is switched off, so this needs your confirmation."

    return ColumnGuess(
        raw_column=raw_column,
        label=top_label,
        canonical=None,
        score=round(float(top_score), 4),
        margin=round(float(margin), 4),
        route=route,
        source=SOURCE_LOCAL,
        reason=reason,
        alternatives=[(label, round(float(score), 4)) for label, score in combined[1:3]],
    )


def _alias_fallback_guess(raw_column: str, ai_available: bool = False) -> ColumnGuess:
    """
    Score a column using only the pre-existing alias map.

    Used when Tier 1's embedding path is unavailable. Exact alias hits are
    trusted outright — except for the known-wrong headers in
    ``_ALIAS_MAP_CONFLICTS``, which fall through to the fuzzy/unknown paths so an
    MRP column is never quietly reported as a selling price.

    A fuzzy keyword match carries the *suggested* canonical name through only when
    there is no AI available to improve on it. When Tier 2 can run, the column is
    escalated with nothing committed, because a keyword substring match is
    precisely the heuristic that mis-reads ``MRP`` as a selling price.
    """
    alias_canonical, alias_confidence = guess_canonical_column(raw_column)
    conflicted = _normalise_header(raw_column).lower() in _ALIAS_MAP_CONFLICTS

    if alias_confidence == "exact" and alias_canonical and not conflicted:
        label = _semantic_from_canonical(alias_canonical)
        return ColumnGuess(
            raw_column=raw_column,
            label=label or UNKNOWN_LABEL,
            canonical=alias_canonical,
            score=1.0,
            margin=1.0,
            route=ROUTE_LOCAL,
            source=SOURCE_LOCAL,
            reason="Matched a known column name exactly.",
        )

    norm = _normalise_header(raw_column).lower()
    if norm in {"currency", "ccy", "curr"}:
        return ColumnGuess(raw_column=raw_column, label="currency", canonical=None, score=1.0, margin=1.0, route=ROUTE_LOCAL, source=SOURCE_LOCAL, reason="Recognised, not analysed. You can still map it by hand.")
    if norm in {"status", "order status", "payment status", "fulfillment status"}:
        return ColumnGuess(raw_column=raw_column, label="status", canonical=None, score=1.0, margin=1.0, route=ROUTE_LOCAL, source=SOURCE_LOCAL, reason="Recognised, not analysed. You can still map it by hand.")
    if norm in {"notes", "remarks", "comments", "comment", "remark", "note"}:
        return ColumnGuess(raw_column=raw_column, label="notes", canonical=None, score=1.0, margin=1.0, route=ROUTE_LOCAL, source=SOURCE_LOCAL, reason="Recognised, not analysed. You can still map it by hand.")

    if alias_confidence == "fuzzy" and alias_canonical:
        escalating = ai_available
        return ColumnGuess(
            raw_column=raw_column,
            label=_semantic_from_canonical(alias_canonical) or UNKNOWN_LABEL,
            canonical=None if escalating else alias_canonical,
            score=0.5,
            margin=0.0,
            route=ROUTE_GEMINI if escalating else ROUTE_LOCAL,
            source=SOURCE_LOCAL,
            reason=(
                "Matched by keyword only, and two column meanings are plausible here."
                if escalating
                else "Matched by keyword only — please confirm."
            ),
        )

    return ColumnGuess(
        raw_column=raw_column,
        label=UNKNOWN_LABEL,
        canonical=None,
        score=0.0,
        margin=0.0,
        route=ROUTE_GEMINI if ai_available else ROUTE_LOCAL,
        source=SOURCE_LOCAL,
        reason=(
            "Not recognised locally — asking AI to identify it."
            if ai_available
            else "Not recognised. You can map it by hand on the next screen."
        ),
    )