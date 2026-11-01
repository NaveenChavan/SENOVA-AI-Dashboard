"""
Leaf loader for ``app/data/column_dictionary.json``.

This module has exactly one job: turn the JSON dictionary built by
``scripts/build_dictionary_json.py`` into the two lookup shapes production
code needs, without introducing any new runtime behaviour.

Design constraints
-------------------
* stdlib only — no pandas, no app imports, so this can be imported from
  anywhere (``data_validator.py``, ``column_catalog.py``, tests) with zero
  risk of a circular import.
* ``legacy_key`` is an EXACT copy of ``data_validator._normalize_col_name``.
  It is redefined here (not imported) so this module has no dependency on
  ``data_validator`` — ``data_validator`` depends on *this* module, not the
  other way around.
* The JSON is parsed once per process (``functools.lru_cache``) and the two
  indexes are derived from it once.
* ``normalize_phrase`` (NFKC/casefold "stage 2" normalisation) exists for
  future use and tests only. It is deliberately NOT built into an index and
  NOT consulted by ``lookup_legacy_alias`` — production lookup is, and must
  stay, byte-identical to the legacy ``_normalize_col_name`` behaviour.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Any

DICTIONARY_PATH = Path(__file__).resolve().parents[1] / "data" / "column_dictionary.json"

#: Unicode blocks preserved as-is by ``normalize_phrase`` instead of being
#: casefolded/stripped like Latin text — Devanagari and Kannada script in
#: Hindi/Hinglish or Kannada header synonyms.
_DEVANAGARI_RANGE = (0x0900, 0x097F)
_KANNADA_RANGE = (0x0C80, 0x0CFF)

_WHITESPACE_RE = re.compile(r"\s+")


def legacy_key(raw: str) -> str:
    """
    EXACT copy of ``data_validator._normalize_col_name``.

    Kept duplicated (not imported) so this module has zero dependency on
    ``data_validator`` — the import direction is the other way around after
    the Phase 3 migration.
    """
    return str(raw).strip().lstrip("\ufeff").lower()


def _preserve_script(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        _DEVANAGARI_RANGE[0] <= codepoint <= _DEVANAGARI_RANGE[1]
        or _KANNADA_RANGE[0] <= codepoint <= _KANNADA_RANGE[1]
    )


def normalize_phrase(raw: str) -> str:
    """
    Stage-2 normalisation: NFKC, casefold, BOM-strip, whitespace-collapse,
    with Devanagari/Kannada characters preserved rather than casefolded away.

    NOT used by any production lookup path today — ``lookup_legacy_alias``
    uses ``legacy_key`` only, to stay byte-identical to the pre-migration
    behaviour. This function exists so a richer normalisation strategy can be
    tested/adopted later without redesigning the loader.
    """
    text = str(raw).strip().lstrip("\ufeff")
    text = unicodedata.normalize("NFKC", text)

    out_chars = []
    for ch in text:
        if _preserve_script(ch):
            out_chars.append(ch)
        else:
            out_chars.append(ch.casefold())
    text = "".join(out_chars)

    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


@functools.lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    """Parse the JSON dictionary file once per process."""
    with DICTIONARY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _legacy_exact() -> dict[str, dict]:
    """``phrase_norm`` -> entry, for ``kind == "legacy_alias"`` entries only."""
    index: dict[str, dict] = {}
    for entry in _load_raw()["entries"]:
        if entry["kind"] != "legacy_alias":
            continue
        index[entry["phrase_norm"]] = entry
    return index


@functools.lru_cache(maxsize=1)
def _semantic_synonyms() -> dict[str, list[tuple[str, str]]]:
    """``legacy_key(synonym)`` -> ordered list of ``(label, synonym_text)``.

    Built from every entry in the JSON (``legacy_alias`` entries carry a
    ``semantic_label`` when one agreed during the merge, and ``semantic``
    entries always carry one), so a reverse-lookup consumer can still find the
    label a given phrase belongs to.
    """
    index: dict[str, list[tuple[str, str]]] = {}
    for entry in _load_raw()["entries"]:
        label = entry.get("semantic_label")
        if not label:
            continue
        key = legacy_key(entry["phrase_raw"])
        index.setdefault(key, []).append((label, entry["phrase_raw"]))
    return index


@functools.lru_cache(maxsize=1)
def _synonyms_by_label() -> dict[str, tuple[str, ...]]:
    """``label`` -> ordered tuple of synonym strings, preserving original JSON order.

    This is distinct from ``_semantic_synonyms`` (which is keyed by phrase):
    this index is keyed by label and is what ``semantic_synonyms_by_label()``
    serves to ``column_catalog.py`` so ``SEMANTIC_FIELDS`` can be rebuilt with
    the exact same per-label synonym order as before the migration.

    Entries are sorted by their recorded ``semantic_order`` (the synonym's
    zero-based position in the original ``field.synonyms`` tuple at
    generation time), NOT by their position in the JSON's ``entries`` array.
    The two can differ because a legacy-alias entry occupies its alias-map
    insertion slot even after a semantic label is merged onto it, so entry
    order alone cannot be trusted to reconstruct per-label synonym order.
    """
    by_label: dict[str, list[tuple[int, str]]] = {}
    for entry in _load_raw()["entries"]:
        label = entry.get("semantic_label")
        if not label:
            continue
        order = entry.get("semantic_order")
        order = order if order is not None else 1 << 30
        by_label.setdefault(label, []).append((order, entry["phrase_raw"]))
    return {
        label: tuple(text for _, text in sorted(values, key=lambda pair: pair[0]))
        for label, values in by_label.items()
    }


def lookup_legacy_alias(raw: str) -> tuple[str | None, str]:
    """
    Exact-match lookup against the legacy alias dictionary.

    Returns ``(canonical, "exact")`` on a hit or ``(None, "none")`` on a miss
    — the same two-tuple shape ``data_validator.guess_canonical_column`` used
    to get directly from ``COLUMN_ALIAS_MAP``.
    """
    key = legacy_key(raw)
    entry = _legacy_exact().get(key)
    if entry is None:
        return None, "none"
    return entry["target_canonical"], "exact"


def semantic_synonyms_by_label() -> dict[str, list[str]]:
    """
    ``label`` -> ordered list of synonym strings, preserving the original
    per-label synonym order recorded in the JSON (which itself mirrors the
    pre-migration hardcoded ``SEMANTIC_FIELDS`` order).
    """
    return {label: list(values) for label, values in _synonyms_by_label().items()}


def get_alias_compat_view() -> MappingProxyType:
    """
    Read-only dict matching the old ``COLUMN_ALIAS_MAP`` shape exactly:
    ``{phrase_norm: canonical_field}`` for every legacy-alias entry.

    Returned as a ``MappingProxyType`` so callers cannot mutate what looks
    like a plain dict — the JSON file is the single source of truth now.
    """
    view = {norm: entry["target_canonical"] for norm, entry in _legacy_exact().items()}
    return MappingProxyType(view)
