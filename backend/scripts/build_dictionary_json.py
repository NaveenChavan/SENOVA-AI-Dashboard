"""
Phase 3 — one-shot generator for ``app/data/column_dictionary.json``.

This script is the ONLY place the legacy ``COLUMN_ALIAS_MAP`` (268 entries)
and the semantic ``SEMANTIC_FIELDS`` synonyms (359 entries) are read from
their current Python-literal homes and merged into one JSON dictionary.

It is NOT imported by the application. It is a human-run, one-time (per
regeneration) build step: ``python scripts/build_dictionary_json.py``.

Merge rule (alias precedence)
------------------------------
A legacy alias key and a semantic synonym can normalise to the same
``phrase_norm`` (e.g. "date" is both a ``COLUMN_ALIAS_MAP`` key and a
``date`` synonym). When that happens:

* If their meanings AGREE (the alias's canonical target equals
  ``canonical_field_for(label, raw)`` for the semantic label that produced
  the synonym), the two provenance records are merged into ONE entry, kept
  as ``kind="legacy_alias"`` — alias entries are what production actually
  reads, so alias precedence is preserved.
* If their meanings DISAGREE, the alias entry still wins for production
  (``kind="legacy_alias"`` with the alias's own target), but the conflict is
  recorded in ``provenance`` so it is visible instead of silently dropped.

Every semantic synonym that has no colliding alias key becomes its own
``kind="semantic"`` entry with no ``target_canonical``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.column_catalog import SEMANTIC_FIELDS, SEMANTIC_TO_CANONICAL, canonical_field_for
from app.utils.data_validator import COLUMN_ALIAS_MAP, _FUZZY_KEYWORDS, _normalize_col_name

OUTPUT_PATH = BACKEND / "app" / "data" / "column_dictionary.json"


def _is_devanagari_or_kannada(text: str) -> bool:
    for ch in text:
        codepoint = ord(ch)
        if 0x0900 <= codepoint <= 0x097F:  # Devanagari
            return True
        if 0x0C80 <= codepoint <= 0x0CFF:  # Kannada
            return True
    return False


def _language_for(text: str) -> str:
    return "hi" if _is_devanagari_or_kannada(text) else "en"


def build() -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()

    # phrase_norm -> entry, built in two passes (alias first, then semantic merge).
    entries_by_norm: dict[str, dict] = {}

    # ── Pass 1: legacy aliases (268 entries) — these always become kind=legacy_alias ──
    for raw_key, target_canonical in COLUMN_ALIAS_MAP.items():
        phrase_norm = _normalize_col_name(raw_key)
        entries_by_norm[phrase_norm] = {
            "phrase_raw": raw_key,
            "phrase_norm": phrase_norm,
            "kind": "legacy_alias",
            "semantic_label": None,
            "semantic_order": None,
            "target_canonical": target_canonical,
            "language": _language_for(raw_key),
            "source": "legacy_alias_map",
            "verification_status": "verified",
            "provenance": [
                {
                    "origin": "legacy_alias_map",
                    "raw_key": raw_key,
                    "target_canonical": target_canonical,
                }
            ],
        }

    semantic_count = 0
    merged_count = 0
    conflict_count = 0
    semantic_only_count = 0

    # ── Pass 2: semantic synonyms (359 entries) — merge into existing alias entries
    #     when they agree, flag conflicts when they don't, otherwise stand alone.
    #
    #     ``semantic_order`` records this synonym's zero-based position within
    #     its label's ``field.synonyms`` tuple. It is carried on every entry
    #     that resolves a semantic_label (whether merged into a legacy_alias
    #     entry or standing alone) specifically so the JSON's dict/list
    #     iteration order — which is allowed to differ from the original
    #     per-label synonym order once alias-map entries are interleaved in —
    #     never has to be relied upon to reconstruct that order. The loader
    #     sorts by this field, not by entry position. ──
    for field in SEMANTIC_FIELDS:
        label = field.label
        for position, synonym in enumerate(field.synonyms):
            semantic_count += 1
            phrase_norm = _normalize_col_name(synonym)
            semantic_target = canonical_field_for(label, synonym)

            existing = entries_by_norm.get(phrase_norm)
            if existing is not None and existing["kind"] == "legacy_alias":
                alias_target = existing["target_canonical"]
                agrees = alias_target == semantic_target
                existing["provenance"].append(
                    {
                        "origin": "semantic_synonym",
                        "semantic_label": label,
                        "raw_key": synonym,
                        "semantic_target_canonical": semantic_target,
                        "agrees_with_alias": agrees,
                        "semantic_order": position,
                    }
                )
                if existing["semantic_label"] is None and agrees:
                    existing["semantic_label"] = label
                    existing["semantic_order"] = position
                if agrees:
                    merged_count += 1
                else:
                    conflict_count += 1
                    existing["verification_status"] = "conflict_alias_precedence"
                continue

            if existing is not None and existing["kind"] == "semantic":
                # Same normalised phrase reused by a second semantic label/synonym
                # (rare, but keep first-wins + record provenance).
                existing["provenance"].append(
                    {
                        "origin": "semantic_synonym",
                        "semantic_label": label,
                        "raw_key": synonym,
                        "semantic_target_canonical": semantic_target,
                        "semantic_order": position,
                    }
                )
                continue

            semantic_only_count += 1
            entries_by_norm[phrase_norm] = {
                "phrase_raw": synonym,
                "phrase_norm": phrase_norm,
                "kind": "semantic",
                "semantic_label": label,
                "semantic_order": position,
                "target_canonical": None,
                "language": _language_for(synonym),
                "source": "semantic_fields",
                "verification_status": "verified",
                "provenance": [
                    {
                        "origin": "semantic_synonym",
                        "semantic_label": label,
                        "raw_key": synonym,
                        "semantic_target_canonical": semantic_target,
                        "semantic_order": position,
                    }
                ],
            }

    entries = list(entries_by_norm.values())
    legacy_alias_entries = [e for e in entries if e["kind"] == "legacy_alias"]
    semantic_entries = [e for e in entries if e["kind"] == "semantic"]

    metadata = {
        "generated_at": generated_at,
        "generator": "backend/scripts/build_dictionary_json.py",
        "counts": {
            "total_entries": len(entries),
            "legacy_alias_entries": len(legacy_alias_entries),
            "semantic_entries": len(semantic_entries),
            "source_legacy_alias_map_size": len(COLUMN_ALIAS_MAP),
            "source_semantic_synonym_count": semantic_count,
            "semantic_merged_into_alias_agree": merged_count,
            "semantic_merged_into_alias_conflict": conflict_count,
            "semantic_only_new_entries": semantic_only_count,
            "fuzzy_keywords_count_not_included": len(_FUZZY_KEYWORDS),
            "semantic_field_count": len(SEMANTIC_FIELDS),
            "semantic_to_canonical_count": len(SEMANTIC_TO_CANONICAL),
        },
        "notes": (
            "_FUZZY_KEYWORDS is intentionally NOT represented in this JSON — it "
            "remains a hardcoded, order-sensitive literal in data_validator.py. "
            "Alias precedence: where a legacy alias key and a semantic synonym "
            "normalise to the same phrase, the legacy_alias entry is kept for "
            "production lookups; agreement/conflict is recorded in provenance."
        ),
    }

    return {"metadata": metadata, "entries": entries}


def main() -> None:
    data = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = data["metadata"]["counts"]
    print(f"Wrote {OUTPUT_PATH}")
    for key, value in counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
