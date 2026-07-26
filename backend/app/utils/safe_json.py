"""
JSON-safety helpers for every number that leaves the API.

Why this module exists
---------------------
Pandas/NumPy happily produce ``NaN``, ``inf`` and ``-inf`` from ordinary
retail maths — a margin on zero revenue, a growth rate against a zero
baseline, a velocity over a zero-day window. Pydantic serialises those
values as the bare literals ``NaN`` / ``Infinity``, which are **not valid
JSON**: the browser's ``JSON.parse`` throws and the whole dashboard shows
a generic network error instead of a number.

Every calculation module therefore funnels its output through
``safe_float`` / ``safe_int`` / ``safe_div`` here, so a single unusual row
in a shop's CSV can never take the dashboard down.
"""

from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any, digits: int = 2, default: float | None = None) -> float | None:
    """
    Coerce anything numeric to a rounded, JSON-safe ``float``.

    Returns ``default`` (``None`` by default, which serialises to JSON
    ``null``) when the value is missing, non-numeric, ``NaN`` or infinite —
    the three cases Pydantic would otherwise emit as invalid JSON.
    """
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return round(number, digits)


def safe_int(value: Any, default: int = 0) -> int:
    """
    Coerce anything numeric to a JSON-safe ``int``.

    Truncates toward zero (``int(float(v))``) and falls back to ``default``
    for missing/NaN/infinite input, so ``.astype(int)``-style crashes can
    never reach a response.
    """
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return int(number)


def safe_div(numerator: Any, denominator: Any, default: float | None = None) -> float | None:
    """
    Division that never raises and never returns an unserialisable value.

    Used for every ratio in the codebase (margin %, growth %, days of
    cover, velocity) because a zero denominator is normal business data,
    not an error: a day with no sales, an item with no revenue, a period
    with no previous period to compare against.
    """
    num = safe_float(numerator, digits=10)
    den = safe_float(denominator, digits=10)
    if num is None or den is None or den == 0:
        return default
    return safe_float(num / den, digits=10)


def safe_percentage(part: Any, whole: Any, digits: int = 2, default: float | None = None) -> float | None:
    """``part / whole * 100``, rounded, with the same zero/NaN guarantees as ``safe_div``."""
    ratio = safe_div(part, whole)
    if ratio is None:
        return default
    return safe_float(ratio * 100, digits=digits, default=default)
