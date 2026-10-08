"""
Tier 2 — Gemini Flash, for columns Tier 1 could not settle on its own.

What leaves the server, and what doesn't
---------------------------------------
This is the only module in the project that makes an outbound request carrying a
shop's data. Three gates must all be open before a single byte is sent:

1. ``AI_ASSIST_ENABLED`` — the operator's master switch, default **false**.
2. ``ai_consent`` on this specific request — the user ticked a box.
3. ``GEMINI_API_KEY`` present in the environment.

Any one of them closed means no HTTP client is even constructed. There is a test
that asserts the transport is never called when consent is false.

What is in the payload
----------------------
Per ambiguous column: the header, the inferred dtype, and aggregate shape
statistics. Sample values only where ``pii_mask`` permits them, and always
masked. A customer column, a remarks column, or any unmapped text column sends
header and statistics *only*. The full dataset is never sent — see the system
instruction below, which repeats it to the model as well, and the tests, which
assert the absence of specific literals in the captured request body.

Reliability
-----------
Ten seconds per attempt, two retries with exponential backoff, explicit handling
of 429 and 5xx, and a hard overall budget (``GEMINI_TOTAL_BUDGET_SECONDS``) that
is what actually protects the request — three 10-second attempts plus backoff
would otherwise run to roughly 33 seconds and trip the frontend's request
timeout.

Every failure path ends in the same place: the columns come back marked
``other``/``fallback`` and the upload continues. The dashboard must never fail
because an AI call did.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import (
    AI_ASSIST_ENABLED,
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    GEMINI_TOTAL_BUDGET_SECONDS,
)
from app.services.column_catalog import SEMANTIC_LABELS
from app.services.pii_mask import shape_stats

logger = logging.getLogger("senova.tier2")

#: Gemini's REST endpoint. The model is substituted per call so
#: ``GEMINI_MODEL`` can change without touching this constant.
_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Base delay for the exponential backoff, in seconds. Attempts sleep
#: ``_BACKOFF_BASE * 2 ** attempt_index``, so with retries=2 that's 1s then 2s.
_BACKOFF_BASE = 1.0

#: Why we call it, stated to the model. Repeating the constraints in the prompt
#: costs a few tokens and materially reduces the chance of a model inventing a
#: column meaning that isn't on the enum.
_SYSTEM_INSTRUCTION = """\
You identify the business meaning of spreadsheet column headers.

Rules:
- Choose exactly one label per column from the provided list.
- Base your choice on the column header first, then the shape statistics.
- The shape statistics are aggregate only. "numeric_ratio: 1.0" means every value
  parses as a number; it does NOT tell you whether the column is revenue, cost,
  tax or quantity — only the header can distinguish those.
- Return the label "other" if the header fits none of the listed meanings. Do not
  invent a meaning, and do not pick the closest-sounding label when nothing fits.
- If two meanings are genuinely equally likely, return "other". The caller will
  ask a human, which is a better outcome than a confident wrong answer.
- Never invent values, figures, or column names that were not given to you.

Output format:
Return a JSON object with a single key "columns", containing a list of objects.
Each object must have these exact keys:
- "column": The column header exactly as it was sent
- "label": One of: {', '.join(SEMANTIC_LABELS)}
- "confidence": How sure you are, from 0.0 to 1.0
- "reason": One short sentence explaining the choice
"""


# ── Response schema ──────────────────────────────────────────────────────────


class ColumnVerdict(BaseModel):
    """One column's meaning as decided by Gemini."""

    column: str = Field(..., description="The column header exactly as it was sent")
    label: str = Field(..., description=f"One of: {', '.join(SEMANTIC_LABELS)}")
    confidence: float = Field(
        0.5, ge=0.0, le=1.0, description="How sure the model is, 0 to 1"
    )
    reason: str = Field("", description="One short sentence explaining the choice")


class GeminiVerdict(BaseModel):
    """The whole response. ``columns`` maps header → verdict."""

    columns: list[ColumnVerdict] = Field(default_factory=list)


# ── Insight prose (Step 11) ──────────────────────────────────────────────────


class InsightRewrite(BaseModel):
    """One insight's message, rewritten. Prose only — never a figure."""

    id: str = Field(..., description="The insight id this rewrite belongs to")
    message: str = Field("", description="A clearer phrasing of the same finding")


class GeminiNarrative(BaseModel):
    """The whole response. ``rewrites`` is keyed by insight id."""

    rewrites: list[InsightRewrite] = Field(default_factory=list)


#: Why we call it for prose, stated to the model. The critical instruction is the
#: last one: the model has seen real aggregates by this point, and a model that
#: reasons about numbers will happily produce one. Prose-only is what keeps
#: ``insights_engine`` the sole source of truth for every figure on the dashboard.
_SYSTEM_INSTRUCTION_PROSE = """\
You rewrite the explanation on business insight cards so a shop owner understands
them faster. You are NOT doing analysis and you are NOT computing anything.

Rules:
- Keep the finding itself identical. Same meaning, same severity, same conclusion.
- Rewrite for clarity and plain language. Shorter is better. Use the shopkeeper's
  vocabulary, not accounting terms.
- NEVER introduce, change, round, or infer any number, date, amount, percentage
  or count. Every figure in the original text must appear unchanged if you mention
  it at all. It is much safer to omit a figure than to restate it.
- Do not add advice, causes, predictions or recommendations that were not in the
  original text.
- Keep each rewrite to one or two sentences.
- If a card's original message is already clear, return it unchanged.

Output format:
Return a JSON object with a single key "rewrites", containing a list of objects.
Each object must have these exact keys:
- "id": The insight id this rewrite belongs to
- "message": A clearer phrasing of the same finding
"""


# ── Outcome ──────────────────────────────────────────────────────────────────

#: Where the answer came from, surfaced to the UI so a user can see whether they
#: are looking at a fresh model verdict or a cached one.
SOURCE_GEMINI = "gemini"
SOURCE_CACHE = "cache"
SOURCE_SKIPPED = "skipped"
SOURCE_FAILED = "fallback"


class Tier2Result(BaseModel):
    """Outcome of the Tier 2 stage for one upload."""

    #: header → verdict dict, only for columns Gemini actually answered.
    verdicts: dict[str, dict] = Field(default_factory=dict)
    source: str = SOURCE_SKIPPED
    #: Wall-clock milliseconds the stage took, for the pipeline timings.
    elapsed_ms: float = 0.0
    #: Plain-language reason when ``source`` is ``skipped`` or ``fallback``.
    notice: str | None = None
    #: Short machine-readable code for the reason, to surface exact failures in the UI.
    reason_code: str | None = None


def gemini_enabled() -> bool:
    """
    Whether Tier 2 *could* run — the operator switch and a key are present.

    Note this deliberately does not consider consent, which is per request.
    """
    return bool(AI_ASSIST_ENABLED and GEMINI_API_KEY)


def _build_prompt(columns: list[dict]) -> str:
    """
    Render the ambiguous columns as the compact JSON blob sent to Gemini.

    Deliberately built by hand rather than ``json.dumps``-ing the caller's
    structures: this is the last point where we choose exactly which fields of a
    shop's data are included, so it should read as an explicit allowlist rather
    than a serialisation of whatever was passed in.
    """
    described = []
    for column in columns:
        entry: dict[str, Any] = {
            "column": column["name"],
            "inferred_dtype": column.get("dtype", "unknown"),
        }
        stats = column.get("stats") or {}
        if stats:
            entry["shape"] = {
                "numeric_ratio": stats.get("numeric_ratio"),
                "date_parse_ratio": stats.get("date_parse_ratio"),
                "unique_ratio": stats.get("unique_ratio"),
                "mean_length": stats.get("mean_length"),
                "all_integer": stats.get("all_integer"),
                "null_ratio": stats.get("null_ratio"),
            }
        # Absent entirely — not an empty list — when values were suppressed, so
        # the model cannot infer column contents from a present-but-blank field.
        if column.get("samples"):
            entry["sample_values"] = column["samples"]
        described.append(entry)

    return (
        "Identify the business meaning of each column below.\n\n"
        f"Valid labels: {', '.join(SEMANTIC_LABELS)}\n\n"
        f"Columns:\n{json.dumps(described, ensure_ascii=False, indent=2)}"
    )


def _extract_json(response_text: str) -> dict:
    """
    Pull the JSON object out of a Gemini response.

    Structured output should return bare JSON, but a model can still wrap it in
    a fenced code block. Rather than trust it, we try ``json.loads`` and then a
    fenced-block extraction, and raise on both failing so the caller retries.
    """
    text = (response_text or "").strip()
    if not text:
        raise ValueError("Empty response body.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        block = text.split("```", 2)[1] if text.count("```") >= 2 else ""
        block = block.removeprefix("json").strip()
        if block:
            return json.loads(block)

    raise ValueError("Response body was not valid JSON.")


def _sanitise_verdicts(payload: dict, expected: list[str]) -> dict[str, dict]:
    """
    Validate the model's answer against the schema and the request.

    Three things are checked because a model can plausibly get each wrong:

    * the payload parses as ``GeminiVerdict`` (a Pydantic model, so types and
      bounds are enforced);
    * every verdict names a column that was actually asked about — a model may
      hallucinate a column header that was never in the request;
    * every label is on the catalog enum.

    Results are keyed by the column name **we** sent, not the one the model
    echoed back. The lookup is case- and whitespace-insensitive so a model that
    re-cases a header still resolves, but the caller then gets back exactly the
    string it passed in — which is what it needs to index the DataFrame by.
    """
    result = GeminiVerdict.model_validate(payload)

    # Map normalised header → the exact header we asked about.
    allowed = {str(name).strip().lower(): str(name) for name in expected}
    clean: dict[str, dict] = {}

    for verdict in result.columns:
        lookup = str(verdict.column).strip().lower()
        if lookup not in allowed:
            logger.warning("Discarding a verdict for a column we never asked about.")
            continue
        label = str(verdict.label).strip().lower()
        if label not in set(SEMANTIC_LABELS):
            logger.warning("Discarding a verdict naming an unknown label %r.", verdict.label)
            continue
        clean[allowed[lookup]] = {
            "label": label,
            "confidence": float(verdict.confidence),
            "reason": (verdict.reason or "")[:200],
        }

    return clean


def _is_retryable(status_code: int) -> bool:
    """429 and 5xx are worth another try; 4xx generally means our request is wrong."""
    return status_code == 429 or status_code >= 500


async def _call_gemini(
    client: httpx.AsyncClient,
    model_name: str,
    max_retries: int,
    columns: list[dict],
    deadline: float,
) -> dict[str, dict]:
    """
    POST the ambiguous columns to Gemini with retries, returning clean verdicts.

    Raises on unrecoverable failure; the caller turns that into a fallback.
    """
    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": _build_prompt(columns)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    url = _ENDPOINT_TEMPLATE.format(model=model_name)
    expected = [column["name"] for column in columns]

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        # Never start an attempt we have no budget to finish. Without this check a
        # slow upstream could push the request well past the frontend's timeout
        # on the final retry.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Tier 2 budget exhausted before the final attempt.")

        try:
            # Respect both the per-attempt timeout and the remaining total budget
            from . import tier2_gemini
            timeout_for_attempt = min(tier2_gemini.GEMINI_TIMEOUT_SECONDS, remaining)
            response = await client.post(url, json=body, timeout=timeout_for_attempt)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            logger.warning("Tier 2 attempt %d failed to reach Gemini (%s).", attempt + 1, type(exc).__name__)
        else:
            if response.status_code == 200:
                try:
                    payload = _extract_json(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                    return _sanitise_verdicts(payload, expected)
                except (ValidationError, ValueError, KeyError, IndexError, TypeError) as exc:
                    # A well-formed HTTP 200 with unusable content. Gemini does
                    # this occasionally, and it is worth one more try.
                    last_error = ValueError("invalid_json")
                    logger.warning("Tier 2 attempt %d returned an unusable body (%s).", attempt + 1, type(exc).__name__)

            elif _is_retryable(response.status_code):
                reason = "rate_limit" if response.status_code == 429 else "server_error"
                last_error = httpx.HTTPStatusError(
                    reason,
                    request=response.request,
                    response=response,
                )
                logger.warning("Tier 2 attempt %d got HTTP %d.", attempt + 1, response.status_code)
            else:
                # 400/401/403/404: our request or our key is wrong. Retrying
                # changes nothing.
                reason = "bad_request"
                if response.status_code in (401, 403):
                    reason = "key_invalid"
                elif response.status_code == 404:
                    reason = "model_unavailable"
                    
                raise httpx.HTTPStatusError(
                    reason,
                    request=response.request,
                    response=response,
                )

        if attempt < max_retries:
            delay = _BACKOFF_BASE * (2**attempt)
            # Honour the deadline over the backoff schedule.
            if time.monotonic() + delay >= deadline:
                break
            await asyncio.sleep(delay)

    raise last_error or RuntimeError("server_error")


async def resolve_columns(
    columns: list[dict],
    ai_consent: bool,
    cache_load=None,
    cache_save=None,
    cache_key: str | None = None,
) -> Tier2Result:
    """
    Resolve a batch of ambiguous columns, escalating nothing silently.

    ``columns`` is a list of ``{name, dtype, stats, samples, suppressed}``.
    ``cache_load`` / ``cache_save`` are optional callables taking ``(key)`` and
    ``(key, verdicts)`` — injected rather than imported so this module stays free
    of file-handler dependencies and is trivially testable.

    Order of operations, and why: consent is checked before the cache, so a user
    who declines is never recorded as having had AI assistance; and the cache is
    checked before the network, so a repeat upload of the same structure costs
    nothing.
    """
    started = time.perf_counter()

    if not columns:
        return Tier2Result(source=SOURCE_SKIPPED, elapsed_ms=0.0)

    if not AI_ASSIST_ENABLED:
        return Tier2Result(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI column detection is switched off on this server.",
            reason_code="disabled"
        )

    if not ai_consent:
        return Tier2Result(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI column detection was not approved for this upload.",
            reason_code="no_consent"
        )

    if not GEMINI_API_KEY:
        # Operator enabled AI but forgot the key. Worth saying out loud, because
        # otherwise the user sees silently worse column guesses with no
        # explanation.
        logger.warning("AI_ASSIST_ENABLED is true but GEMINI_API_KEY is empty.")
        return Tier2Result(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI column detection is enabled but no API key is configured on this server.",
            reason_code="key_missing"
        )

    key = cache_key
    if cache_load is not None and key:
        cached = cache_load(key)
        if cached:
            logger.info("Tier 2 served %d column(s) from cache.", len(cached))
            return Tier2Result(
                verdicts=cached,
                source=SOURCE_CACHE,
                elapsed_ms=_elapsed_ms(started),
            )

    deadline = time.monotonic() + GEMINI_TOTAL_BUDGET_SECONDS

    logger.info(
        "Tier 2 call starting: model=%s fallback=%s timeout=%ss budget=%ss",
        GEMINI_MODEL,
        GEMINI_FALLBACK_MODEL,
        GEMINI_TIMEOUT_SECONDS,
        GEMINI_TOTAL_BUDGET_SECONDS,
    )

    try:
        async with httpx.AsyncClient(
            timeout=GEMINI_TIMEOUT_SECONDS,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        ) as client:
            try:
                verdicts = await _call_gemini(client, GEMINI_MODEL, GEMINI_MAX_RETRIES, columns, deadline)
            except Exception as primary_exc:
                is_timeout = isinstance(primary_exc, (httpx.TimeoutException, TimeoutError))
                is_404 = isinstance(primary_exc, httpx.HTTPStatusError) and str(primary_exc.args[0]) == "model_unavailable"
                
                if (is_timeout or is_404) and GEMINI_FALLBACK_MODEL:
                    logger.warning("Primary model failed (%s), trying fallback %s...", "timeout" if is_timeout else "404", GEMINI_FALLBACK_MODEL)
                    try:
                        verdicts = await _call_gemini(client, GEMINI_FALLBACK_MODEL, 0, columns, deadline)
                        return Tier2Result(
                            verdicts=verdicts,
                            source=SOURCE_GEMINI,
                            elapsed_ms=_elapsed_ms(started),
                            reason_code="fallback_used",
                            notice="The primary AI model was unavailable, so a fallback model was used."
                        )
                    except Exception:
                        raise primary_exc
                else:
                    raise primary_exc
    except Exception as exc:
        reason_code = "server_error"
        if isinstance(exc, httpx.HTTPStatusError):
            reason_code = str(exc.args[0])
        elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            reason_code = "timeout"
        elif isinstance(exc, ValueError) and str(exc) == "invalid_json":
            reason_code = "invalid_json"

        # Deliberately broad. A Tier 2 failure is never allowed to fail the
        # upload, so whatever went wrong becomes a fallback and a notice.
        logger.warning("Tier 2 failed (%s: %s). Falling back to manual mapping.", type(exc).__name__, exc)
        return Tier2Result(
            source=SOURCE_FAILED,
            elapsed_ms=_elapsed_ms(started),
            notice=(
                "We couldn't identify some columns automatically, so they've been "
                "left for you to map. Everything else analysed normally."
            ),
            reason_code=reason_code
        )

    if cache_save is not None and key:
        cache_save(key, verdicts)

    return Tier2Result(verdicts=verdicts, source=SOURCE_GEMINI, elapsed_ms=_elapsed_ms(started))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def describe_column(series, name: str, label: str | None) -> dict:
    """
    Build one Tier 2 request entry for a column.

    Runs the whole privacy decision here so no caller can accidentally assemble a
    payload by hand and skip it: values are fetched, stats computed and the
    suppression rule applied in one place.
    """
    from app.services.pii_mask import prepare_samples

    stats = shape_stats(series)
    samples, suppressed = prepare_samples(
        series,
        label,
        numeric_ratio=float(stats["numeric_ratio"]),
        inferred_dtype=str(series.dtype),
    )

    return {
        "name": name,
        "dtype": str(series.dtype),
        "stats": stats,
        "samples": samples,
        "suppressed": suppressed,
    }


# ── Insight prose ────────────────────────────────────────────────────────────
#
# A separate entry point from ``resolve_columns``, sharing the transport, the
# retries, the budget and the gates — but nothing else. The two carry different
# privacy postures, and keeping them apart is what stops that from drifting:
# columns send masked samples, insights send aggregates the user has already
# seen on their own dashboard.
#
# What is sent
# -------------
# The insight id, title, existing message, severity and metrics. That is derived
# data the caller already has on screen, so nothing new is disclosed — but the
# shopkeeper's actual rows, customer names and product identifiers are *not* sent,
# because an insight message is all the model needs and evidence strings can
# contain item names a shop would rather not leave the country.


class NarrativeResult(BaseModel):
    """Outcome of the prose stage for one slice."""

    #: insight id → rewritten message, only for cards that passed the number check.
    rewrites: dict[str, str] = Field(default_factory=dict)
    source: str = SOURCE_SKIPPED
    elapsed_ms: float = 0.0
    notice: str | None = None
    reason_code: str | None = None


def _build_narrative_prompt(insights: list[dict]) -> str:
    """
    Render the insight cards for rewriting.

    Built as an explicit allowlist, for the same reason as ``_build_prompt``:
    ``evidence`` is the field that would leak item and customer names, so it is
    simply not included. The model is told the metrics exist so it can avoid
    contradicting them, but it is not asked to use them.
    """
    cards = [
        {
            "id": insight["id"],
            "severity": insight.get("severity", "neutral"),
            "title": insight.get("title", ""),
            "message": insight.get("message", ""),
        }
        for insight in insights
    ]
    return (
        "Rewrite each insight message below so a shop owner understands it faster.\n"
        "Keep the same finding. Change only the wording. Do not change or add any number.\n\n"
        f"Insights:\n{json.dumps(cards, ensure_ascii=False, indent=2)}"
    )


def _sanitise_rewrites(payload: dict, expected_ids: list[str]) -> dict[str, str]:
    """
    Keep only rewrites for insights we actually asked about.

    Same reasoning as ``_sanitise_verdicts``: a model can return an id it was never
    given, and an unrecognised id must never reach the response where the UI would
    have no way to tell it apart from a real one.
    """
    result = GeminiNarrative.model_validate(payload)
    allowed = {str(identifier).strip(): identifier for identifier in expected_ids}

    clean: dict[str, str] = {}
    for rewrite in result.rewrites:
        key = str(rewrite.id).strip()
        message = (rewrite.message or "").strip()
        if key not in allowed:
            logger.warning("Discarding a rewrite for an insight we never asked about.")
            continue
        if not message:
            continue
        clean[allowed[key]] = message[:600]
    return clean


async def _call_gemini_narrative(
    client: httpx.AsyncClient,
    insights: list[dict],
    deadline: float,
) -> dict[str, str]:
    """POST the insights for rewriting, returning sanitised rewrites."""
    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION_PROSE}]},
        "contents": [{"role": "user", "parts": [{"text": _build_narrative_prompt(insights)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    url = _ENDPOINT_TEMPLATE.format(model=GEMINI_MODEL)
    expected = [insight["id"] for insight in insights]

    last_error: Exception | None = None

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Narrative budget exhausted before the final attempt.")

        try:
            timeout_for_attempt = min(GEMINI_TIMEOUT_SECONDS, remaining)
            response = await client.post(url, json=body, timeout=timeout_for_attempt)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            logger.warning("Narrative attempt %d failed to reach Gemini (%s).", attempt + 1, type(exc).__name__)
        else:
            if response.status_code == 200:
                try:
                    payload = _extract_json(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                    return _sanitise_rewrites(payload, expected)
                except (ValidationError, ValueError, KeyError, IndexError, TypeError) as exc:
                    last_error = ValueError("invalid_json")
                    logger.warning("Narrative attempt %d returned an unusable body (%s).", attempt + 1, type(exc).__name__)

            elif _is_retryable(response.status_code):
                reason = "rate_limit" if response.status_code == 429 else "server_error"
                last_error = httpx.HTTPStatusError(
                    reason, request=response.request, response=response
                )
                logger.warning("Narrative attempt %d got HTTP %d.", attempt + 1, response.status_code)
            else:
                reason = "bad_request"
                if response.status_code in (401, 403):
                    reason = "key_invalid"
                elif response.status_code == 404:
                    reason = "model_not_found"
                    
                raise httpx.HTTPStatusError(
                    reason,
                    request=response.request,
                    response=response,
                )

        if attempt < GEMINI_MAX_RETRIES:
            delay = _BACKOFF_BASE * (2**attempt)
            if time.monotonic() + delay >= deadline:
                break
            await asyncio.sleep(delay)

    raise last_error or RuntimeError("server_error")


async def rewrite_insights(insights: list[dict], ai_consent: bool) -> NarrativeResult:
    """
    Ask Gemini to rephrase each insight, if consent and configuration allow.

    Returns a result carrying *candidate* text only. Nothing here is trusted: the
    caller runs every rewrite through ``number_guard.verify`` against that
    insight's own metrics, and keeps the deterministic sentence wherever the
    candidate does not check out.

    That ordering matters. Verification lives with the caller rather than here
    because the check needs the insight's ``metrics`` and ``evidence``, which are
    the caller's to supply — and because a stage that marked its own output
    verified would be the wrong place to be the only thing checking it.
    """
    started = time.perf_counter()

    if not insights:
        return NarrativeResult(source=SOURCE_SKIPPED, elapsed_ms=0.0)

    if not AI_ASSIST_ENABLED:
        return NarrativeResult(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI-written explanations are switched off on this server.",
            reason_code="disabled"
        )

    if not ai_consent:
        return NarrativeResult(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI-written explanations were not approved.",
            reason_code="no_consent"
        )

    if not GEMINI_API_KEY:
        logger.warning("AI_ASSIST_ENABLED is true but GEMINI_API_KEY is empty.")
        return NarrativeResult(
            source=SOURCE_SKIPPED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI-written explanations need an API key configured on this server.",
            reason_code="key_missing"
        )

    deadline = time.monotonic() + GEMINI_TOTAL_BUDGET_SECONDS

    try:
        async with httpx.AsyncClient(
            timeout=GEMINI_TIMEOUT_SECONDS,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        ) as client:
            rewrites = await _call_gemini_narrative(client, insights, deadline)
    except Exception as exc:
        reason_code = "server_error"
        if isinstance(exc, httpx.HTTPStatusError):
            reason_code = str(exc.args[0])
        elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            reason_code = "timeout"
        elif isinstance(exc, ValueError) and str(exc) == "invalid_json":
            reason_code = "invalid_json"
            
        # Same posture as the column path: a prose failure must never fail the
        # dashboard. The caller keeps every deterministic sentence.
        logger.warning("Narrative stage failed (%s: %s). Keeping original text.", type(exc).__name__, exc)
        return NarrativeResult(
            source=SOURCE_FAILED,
            elapsed_ms=_elapsed_ms(started),
            notice="AI-written explanations weren't available, so the original text was kept.",
            reason_code=reason_code
        )

    return NarrativeResult(rewrites=rewrites, source=SOURCE_GEMINI, elapsed_ms=_elapsed_ms(started))