"""
Number post-check — the guarantee that AI prose cannot invent a figure.

Why checking is not as simple as it sounds
------------------------------------------
The obvious implementation is "every number in the AI text must appear in the
insight's ``metrics``". That is wrong in a way that would quietly destroy the
feature, because most correct prose contains numbers that are *not* metrics:

    "Revenue fell 78% on 14 Jul compared with July."
    "The top 3 items make up most of your sales."
    "Since 2026 the margin has been shrinking."

None of ``14``, ``3``, ``2026`` or ``Jul`` is a metrics key. Verifying them
literally would reject almost every good rewrite, and a post-check that rejects
good text gets switched off by the next person who finds it annoying — at which
point the check is gone entirely.

So each numeric token is **classified first**, and only the load-bearing kinds are
verified. Three kinds are load-bearing: **amounts**, **percentages** and
**counts**. Those are the numbers a shopkeeper will act on. A hallucinated
"revenue was ₹1,20,000" must never survive.

The exemption is positional, not numeric
----------------------------------------
"5 units sold" is a count and **is** verified, because ``5`` there is not
adjacent to a ranking keyword. Only the *ranking* usage of a small integer is
exempt. This distinction is the whole reason the implementation tokenises with
context rather than filtering a number range — and it is why the tests below
check both sides of it: a small integer in a ranking position passes, and the
same integer in a count position does not get a free pass.

What this is not
----------------
This is a safety net, not a proof. It exempts dates, years and small ranking
ordinals, so a hallucinated *date*, or a ranking number inside 1..10, would
pass. That limitation is accepted deliberately and is why the real guarantee
lives elsewhere: by design Gemini rewrites prose and never computes anything. This
module catches the plausible mistakes, it does not certify the text.
"""

from __future__ import annotations

import re

# ── Tokenisation ─────────────────────────────────────────────────────────────

#: Units that scale a number into plain rupees. Indian retail exports and prose
#: both use these, and "1.5 lakh" and "150000" are the same figure — without
#: this, every lakh-formatted amount in good prose would be rejected as
#: hallucinated, which is the failure mode that gets a safety net switched off.
_LAKH = 100_000.0
_CRORE = 10_000_000.0

#: Month names and abbreviations, for date recognition. Lowercased.
_MONTHS = {
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep", "sept",
    "september", "oct", "october", "nov", "november", "dec", "december",
}

#: Unit nouns. Used only to disqualify the year exemption: a number immediately
#: followed by one of these is a quantity that merely happens to look like a year,
#: not a year. Without this, "1999 units" would be exempt as a date and a
#: hallucinated count would sail through.
_UNIT_WORDS = {
    "units", "unit", "pieces", "piece", "items", "item", "orders", "bills",
    "days", "hours", "minutes", "weeks", "months", "years", "times", "people",
    "customers", "orders", "customers", "packs", "boxes", "dozen", "kg", "grams",
}

#: Words that turn a neighbouring integer into a ranking rather than a count.
#: "top 3", "3 highest", "first 5".
_RANKING_WORDS = {
    "top", "bottom", "first", "last", "best", "worst", "highest", "lowest",
    "next", "leading", "biggest", "largest", "smallest",
}

#: A date is scanned as **one token**, not as three numbers. Without this,
#: ``2026-07-14`` tokenises as ``2026``, ``07``, ``14`` and a correct date in good
#: prose is rejected as two hallucinated counts — which is exactly the outcome
#: that gets a safety net switched off.
#:
#: Ordering matters: the date alternative comes first so it wins at any position
#: where both could match.
_DATE = r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"

#: A number, optionally prefixed with a currency symbol or ``Rs``, and optionally
#: suffixed with an Indian scale word. The suffix is part of the token because
#: "1.5 lakh" is one figure — dropping it would verify 1.5 against a metric of
#: 150000 and reject every lakh-formatted amount in correct prose.
#:
#: Note there is no leading ``\s?``: allowing one lets the scan start on the
#: space *before* a date, win on position, and match ``2026`` alone out of
#: ``2026-07-14`` — which is how a date ends up tokenised as three numbers.
_NUMBER = r"[\u20b9$]?(?:rs\.?\s?)?\d[\d,]*(?:\.\d+)?\s*(?:lakh|crore)?"

_NUM_RE = re.compile(rf"(?:{_DATE})|(?:{_NUMBER})", re.IGNORECASE)

#: Rank bound for the small-ranking-ordinal exemption. Kept deliberately small:
#: "the top 47 items" is a count worth verifying, "the top 3" is a ranking.
_RANK_MAX = 10

#: Relative tolerance when comparing a number against a known value.
#:
#: Absolute tolerance alone fails for large figures: a rounding difference on
#: ₹1,20,000 is 500, which no sane absolute tolerance would cover, yet it is not
#: a hallucination. Relative tolerance alone fails for small ones: 0.5% of a count
#: of 4 is 0.02, so "5 units" would never match 4. Taking the max of both is what
#: makes one comparison rule work across rupees, percentages and unit counts.
_ABS_TOLERANCE = 0.5
_REL_TOLERANCE = 0.005


def _to_float(token: str) -> float | None:
    """
    Parse a numeric token into a plain float, normalising Indian notation.

    Handles ``₹1,20,000``, ``Rs. 1,200.50``, ``78%``, ``1.5 lakh`` and
    ``2 crore``. Returns ``None`` if there is no number in the token at all.
    """
    text = token.strip().lower()
    scale = 1.0
    if re.search(r"\bcrore", text):
        scale = _CRORE
        text = re.sub(r"\bcrore\b", "", text)
    elif re.search(r"\blakh", text):
        scale = _LAKH
        text = re.sub(r"\blakh\b", "", text)

    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    try:
        # Commas are grouping separators in both 1,20,000 and 1,200 conventions;
        # removing them handles the two-number ambiguity without needing to know
        # which convention the writer used.
        return float(match.group(0).replace(",", "")) * scale
    except ValueError:
        return None


def _is_ranking_ordinal(value: float, before: str, after: str) -> bool:
    """
    A small integer in a ranking position, which is not a business figure.

    Two forms, both caught by the neighbouring words: an ordinal suffix
    (``3rd``, ``2nd``) and a ranking keyword either side (``top 5 items``,
    ``5 highest``). The rank bound is deliberately small — "the top 47 items" is a
    count worth verifying, "the top 3" is a rank.

    Only the *ranking* use is exempt. ``5`` in "top 5 items" is a rank; ``5`` in
    "5 units sold" has no ranking word beside it and is verified as a count.
    """
    if after in {"rd", "nd", "st", "th"}:
        return True
    if value != int(value) or not (1 <= value <= _RANK_MAX):
        return False
    return before in _RANKING_WORDS or after in _RANKING_WORDS


def _neighbours(text: str, start: int, end: int) -> tuple[str, str]:
    """The words immediately before and after a token, lowercased, stripped."""
    before = re.search(r"([a-z]+)\s*$", text[:start].lower())
    after = re.match(r"\s*([a-z]+)", text[end:].lower())
    return (
        before.group(1) if before else "",
        after.group(1) if after else "",
    )


def _is_date_token(token: str, before: str, after: str) -> bool:
    """
    Recognise a date fragment, so it is exempt rather than verified.

    Three shapes, because these are the three ways dates actually get written:

    * a full ISO or slashed/dashed date (``2026-07-14``, ``14/07/2026``) — the
      whole token is one date and must not be read as three separate numbers;
    * a day number adjacent to a month name (``14 Jul``, ``Jul 14``);
    * a bare year (handled separately, in :func:`_is_year`).
    """
    raw = token.strip()
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", raw):
        return True
    if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", raw):
        return True
    return bool(before in _MONTHS or after in _MONTHS)


def _is_year(value: float, raw: str, after: str) -> bool:
    """
    A bare integer that looks like a calendar year, standing alone.

    "Standing alone" is load-bearing, and it is why this needs the neighbouring
    word. ``1999`` on its own is a year; ``1999 units`` is a count of nearly two
    thousand pieces, and exempting it because it happens to fall in the same
    numeric range would let a hallucinated quantity through — a shopkeeper has no
    way to notice a plausible 1999. So a unit word immediately after disqualifies
    it.

    The trailing-comma strip matters for the same reason: ``Since 2026, revenue``
    tokenises as ``2026,`` and without stripping it the digit test fails and every
    correctly-written year gets flagged.
    """
    digits = raw.strip().rstrip(",.;").strip()
    if not digits.isdigit():
        return False
    if after in _UNIT_WORDS:
        return False
    return value == int(value) and 1900 <= value <= 2099


def _close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= max(_ABS_TOLERANCE, _REL_TOLERANCE * abs(expected))


def _expected_values(metrics: dict, evidence: list[str]) -> list[float]:
    """
    Every number this insight is allowed to cite.

    Both sources count, and both are needed. ``metrics`` holds the headline
    figures; ``evidence`` holds the specifics prose reaches for — "Cotton Kurta",
    "14 Jul" — where a rewrite naturally mentions a figure that was never a
    top-level metric but is genuinely part of the finding.

    Non-numeric values are skipped rather than coerced, since a metrics dict
    legitimately carries ``None`` and string labels.
    """
    values: list[float] = []
    for source in (metrics or {},):
        for value in source.values():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))

    for line in evidence or []:
        for match in _NUM_RE.finditer(str(line)):
            parsed = _to_float(match.group(0))
            if parsed is not None:
                values.append(parsed)
    return values


def verify(text: str, metrics: dict | None = None, evidence: list[str] | None = None) -> tuple[bool, list[str]]:
    """
    Check every load-bearing number in ``text`` against known values.

    Returns ``(verified, offenders)``. ``verified`` is ``False`` if any amount,
    percentage or count in the text cannot be traced back to ``metrics`` or
    ``evidence``; ``offenders`` lists those tokens, for logging and for the test
    that asserts we notice a hallucination rather than waving it through.

    Dates, years and small ranking ordinals are classified and skipped — see the
    module docstring for why verifying them literally would reject correct prose.
    """
    known = _expected_values(metrics or {}, evidence or [])
    offenders: list[str] = []

    for match in _NUM_RE.finditer(text or ""):
        token = match.group(0)
        start, end = match.span()
        before, after = _neighbours(text, start, end)

        value = _to_float(token)
        if value is None:
            continue

        # Exempt first: these are correct-but-unlisted, and verifying them
        # literally is what would make this check useless in practice.
        if _is_date_token(token, before, after):
            continue
        if _is_year(value, token, after):
            continue
        if _is_ranking_ordinal(value, before, after):
            continue

        if not any(_close(value, expected) for expected in known):
            offenders.append(token.strip())

    return (not offenders), offenders
