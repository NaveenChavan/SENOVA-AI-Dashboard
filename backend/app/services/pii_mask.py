"""
Redaction and value-suppression rules for anything Tier 2 sends to Gemini.

This module is the actual privacy enforcement point
---------------------------------------------------
The frontend's consent checkbox is UX. This is the guarantee. Every value that
leaves the server passes through here first, and the rules below are enforced
in backend code regardless of what the client sends, because a client can send
anything:

* **Customer/name-like columns and free-text remarks never send values at all**
  (``PII_SENSITIVE_LABELS`` in ``column_catalog``). Only the header, the
  inferred dtype and aggregate shape statistics go out.
* **Any column we could not identify sends no values if it looks textual.** An
  unmapped column is the highest-risk thing in a file: it could be names,
  addresses, phone numbers or staff remarks, and "we don't know what it is" is
  precisely the state in which sending its contents is worst. An unmapped
  *numeric* column is different — numbers carry little personal data and are
  highly informative for schema matching, so those samples are sent (masked).
* **Everything that is sent is masked first.** Emails become ``[email]``,
  Indian phone numbers become ``[phone]``, and any run of nine or more digits
  becomes ``[number]`` — that last one catches Aadhaar-like identifiers, long
  account numbers and timestamps that no phone regex would.

The suppression decision is made from *measured* statistics, not from pandas'
declared dtype. A currency column ("₹ 1,200") is ``object`` dtype but is not
personal data, and an object column that is really a list of names is. So
``should_suppress_values`` looks at how much of the column actually parses as a
number.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from app.services.column_catalog import PII_SENSITIVE_LABELS, is_known_label

# ── Bounds on what we ever send ──────────────────────────────────────────────

#: Maximum sample values per column. Schema matching needs a handful of examples
#: to recognise a pattern; it does not need a data dump.
SAMPLE_LIMIT = 5

#: Per-value truncation. Long free text is where names and addresses hide, and a
#: truncated value is still plenty for pattern recognition.
SAMPLE_MAX_CHARS = 60

#: Above this share of parseable numbers, a column is treated as numeric rather
#: than textual even when pandas calls it ``object``. Tuned so a column of
#: currency strings still counts as numeric, while a column of names never can.
TEXT_NUMERIC_RATIO_CEILING = 0.5


# ── Masking patterns ─────────────────────────────────────────────────────────
#
# Order matters. Email runs first because an address like
# ``sharma.sales2024@shop.in`` contains a digit run the phone and long-number
# patterns would otherwise chew into, leaving ``[email].shop.in`` behind.

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

#: Indian mobile numbers: optional +91 / 0 prefix, then 6-9 followed by nine
#: digits, tolerating spaces or hyphens as separators. Anchored with lookarounds
#: so it cannot match a fragment of a longer digit run — that case belongs to
#: the long-number rule, which is deliberately stricter.
_PHONE_RE = re.compile(r"(?<![\d.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\d.])")

#: Any run of nine or more digits. Catches Aadhaar numbers, long account numbers,
#: and epoch timestamps that no phone pattern would match.
_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")

_PLACEHOLDER_EMAIL = "[email]"
_PLACEHOLDER_PHONE = "[phone]"
_PLACEHOLDER_NUMBER = "[number]"


def mask_text(value: Any) -> str:
    """
    Redact a single value and truncate it.

    Accepts anything pandas hands back (including ``NaN``/``NaT``, which become
    the empty string rather than the literal ``"nan"``). Non-string input is
    stringified first so a float cell can't bypass the patterns.
    """
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    try:
        if value is pd.NaT or (not isinstance(value, (str, bytes)) and pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass

    text = value if isinstance(value, str) else str(value)
    text = _EMAIL_RE.sub(_PLACEHOLDER_EMAIL, text)
    text = _PHONE_RE.sub(_PLACEHOLDER_PHONE, text)
    text = _LONG_NUMBER_RE.sub(_PLACEHOLDER_NUMBER, text)
    return text[:SAMPLE_MAX_CHARS]


def mask_samples(values: list[Any]) -> list[str]:
    """
    Mask and truncate a list of sample values.

    Empties are dropped *before* the limit is applied, not after. Doing it the
    other way round wastes a slot: a column of ``[None, "a", None, "b", None,
    "c", "d", "e", "f"]`` would yield three samples instead of five, purely
    because the empties happened to sort first.
    """
    masked = (mask_text(value) for value in values)
    return [value for value in masked if value][:SAMPLE_LIMIT]


# ── Shape statistics ─────────────────────────────────────────────────────────

#: Currency/formatting noise stripped before deciding whether a value is a
#: number. Matches what ``data_validator._coerce_numeric`` already tolerates, so
#: the two layers agree on what "₹ 1,200.00" is.
_NUMERIC_NOISE_RE = re.compile(r"[₹$€£,\s%]")

#: Currency *words*, stripped before the symbol class above. Indian exports write
#: amounts as "Rs. 1,200" at least as often as "₹ 1,200", and without this a
#: column of "Rs." amounts measures as 0% numeric — which would push an entirely
#: numeric column over ``TEXT_NUMERIC_RATIO_CEILING`` and get it value-suppressed
#: for no privacy benefit at all.
_CURRENCY_WORD_RE = re.compile(r"(?i)\b(?:rs|inr|rupees?|usd|eur|gbp)\b\.?\s*")

#: A value that *looks* like a date. Deliberately conservative and regex-based
#: rather than ``pd.to_datetime``: pandas will happily read the string ``"12"``
#: as a date, which would make every small-integer column look temporal and
#: wreck the date-parse ratio this module reports.
_MONTH_WORDS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?"
    r"|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?"
    r"|dec(?:ember)?"
)
_DATE_LIKE_RE = re.compile(
    r"^\s*(?:"
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"            # 2026-04-05
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"          # 05/04/2026 or 05-04-26
    r"|\d{1,2}\s*[-/.]?\s*(?:" + _MONTH_WORDS + r")\w*\s*[-/.]?\s*\d{2,4}"   # 5 Apr 2026
    r"|(?:" + _MONTH_WORDS + r")\w*\s*[-/.]?\s*\d{1,2},?\s*\d{2,4}"        # Apr 5, 2026
    r"|\d{8}"                                      # 20260405
    r")\s*$",
    re.IGNORECASE,
)


def _strip_numeric_noise(value: Any) -> str:
    """Reduce a value to its bare digits/sign so ``float()`` can read it."""
    text = _CURRENCY_WORD_RE.sub("", str(value))
    return _NUMERIC_NOISE_RE.sub("", text).strip()


def _is_number_like(value: Any) -> bool:
    """True when a single value parses as a number once currency noise is gone."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        return True
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    cleaned = _strip_numeric_noise(value)
    if not cleaned:
        return False
    try:
        float(cleaned)
    except ValueError:
        return False
    return True


def _is_date_like(value: Any) -> bool:
    """True when a value's text matches a recognised date shape."""
    if value is None:
        return False
    try:
        if not isinstance(value, str) and pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float, np.integer, np.floating)):
        # A bare number is a date only if it is an 8-digit YYYYMMDD stamp,
        # which _is_number_like would otherwise claim outright.
        text = str(int(value))
        return len(text) == 8 and text.isdigit()
    return bool(_DATE_LIKE_RE.match(str(value).strip()))


def shape_stats(series: pd.Series) -> dict[str, float | bool]:
    """
    Aggregate-only description of a column's values.

    Deliberately returns ratios and averages and nothing else — no value, no
    example, no distinct-value list. This is the entire description of a column
    that Tier 2 receives when its values are suppressed, so it has to carry the
    signal without carrying the data.

    * ``null_ratio`` — share of cells that are empty/NaN.
    * ``numeric_ratio`` — share of non-null cells that parse as a number.
    * ``date_parse_ratio`` — share of non-null cells that look like a date.
    * ``unique_ratio`` — distinct values ÷ non-null values.
    * ``mean_length`` — mean character length of the non-null values.
    * ``all_integer`` — every numeric value is a whole number.
    """
    total = int(len(series))
    if total == 0:
        return {
            "null_ratio": 0.0,
            "numeric_ratio": 0.0,
            "date_parse_ratio": 0.0,
            "unique_ratio": 0.0,
            "mean_length": 0.0,
            "all_integer": False,
        }

    not_null = series[series.notna()]
    present = int(len(not_null))

    if present == 0:
        return {
            "null_ratio": 1.0,
            "numeric_ratio": 0.0,
            "date_parse_ratio": 0.0,
            "unique_ratio": 0.0,
            "mean_length": 0.0,
            "all_integer": False,
        }

    numeric_flags = [_is_number_like(value) for value in not_null]
    date_flags = [_is_date_like(value) for value in not_null]

    numeric_count = sum(numeric_flags)
    lengths = [len(str(value).strip()) for value in not_null]

    all_integer = True
    if numeric_count == present:
        for value in not_null:
            if not float(_strip_numeric_noise(value)).is_integer():
                all_integer = False
                break
    else:
        all_integer = False

    return {
        "null_ratio": round((total - present) / total, 4),
        "numeric_ratio": round(numeric_count / present, 4),
        "date_parse_ratio": round(sum(date_flags) / present, 4),
        "unique_ratio": round(float(not_null.nunique()) / present, 4),
        "mean_length": round(float(np.mean(lengths)), 2),
        "all_integer": all_integer,
    }


# ── The suppression decision ─────────────────────────────────────────────────


def should_suppress_values(
    label: str | None,
    numeric_ratio: float | None = None,
    inferred_dtype: str | None = None,
) -> bool:
    """
    Decide whether a column's **values** may be sent to Tier 2 at all.

    Three rules, in order:

    1. A PII-sensitive meaning (``customer``, ``notes``) → always suppress.
    2. An unidentified meaning (``None``/``"other"``) → suppress when the column
       looks textual. "Textual" is decided from the measured ``numeric_ratio``
       when we have it, because a currency-string column is ``object`` dtype but
       is not personal data; otherwise fall back to the declared dtype.
    3. Everything else → send (masked).

    When we know neither the meaning nor the shape, this returns ``True``.
    Uncertainty is the reason to redact, not a reason to send.
    """
    if label is not None and label.strip().lower() in PII_SENSITIVE_LABELS:
        return True

    if is_known_label(label):
        return False

    if numeric_ratio is not None:
        return numeric_ratio < TEXT_NUMERIC_RATIO_CEILING

    if inferred_dtype is not None:
        return str(inferred_dtype).lower() in {"object", "string", "str", "category", "mixed"}

    return True


def prepare_samples(
    series: pd.Series,
    label: str | None,
    numeric_ratio: float | None = None,
    inferred_dtype: str | None = None,
) -> tuple[list[str], bool]:
    """
    Produce the sample values Tier 2 is allowed to see for one column.

    Returns ``(samples, suppressed)``. When ``suppressed`` is True the caller
    must send only the header and the shape statistics — ``samples`` is empty
    and is not to be serialised into the request at all.
    """
    stats = numeric_ratio if numeric_ratio is not None else shape_stats(series)["numeric_ratio"]
    if should_suppress_values(label, stats, inferred_dtype):
        return [], True

    # Drop nulls before sampling: an example of the empty string teaches the
    # model nothing, and it would consume one of our five slots.
    usable = series[series.notna()]
    if len(usable) > SAMPLE_LIMIT:
        # Head and tail rather than a random slice — retail registers are often
        # ordered by date or insertion, and the last rows are the ones a shop's
        # most recent edits live in.
        half = SAMPLE_LIMIT // 2
        usable = pd.concat([usable.head(half), usable.tail(SAMPLE_LIMIT - half)])

    return mask_samples(list(usable)), False