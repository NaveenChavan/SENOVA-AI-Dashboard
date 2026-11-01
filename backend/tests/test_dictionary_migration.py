"""
Phase 3 — focused migration tests.

These exercise the JSON-backed dictionary end to end: that the JSON file is
the actual runtime source (not a decorative copy of the old literal), that
every frozen Step-0 baseline still resolves identically except for the one
documented ``local`` -> ``dictionary`` source change on exact hits, and that
the catalog/npz/compat-view/fuzzy-keyword surfaces are byte-for-byte
unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import column_catalog as cc
from app.services import tier1_classifier as t1
from app.utils import column_dictionary as cd
from app.utils import data_validator as dv

BASELINE_DIR = Path(__file__).resolve().parent / "fixtures" / "phase3_baseline"


def _load_baseline(name: str) -> dict:
    return json.loads((BASELINE_DIR / name).read_text(encoding="utf-8"))


# ── 1. JSON is the actual runtime source, not a decorative copy ─────────────


def test_json_is_runtime_source(tmp_path, monkeypatch):
    """
    Point the loader at a JSON dictionary where ``date`` resolves to
    ``Category`` instead of ``Date``, and confirm the live resolver picks
    that up. This is the proof that production reads the JSON file, not a
    frozen-at-import-time literal.
    """
    temp_json = tmp_path / "column_dictionary.json"
    temp_json.write_text(
        json.dumps(
            {
                "metadata": {"counts": {}},
                "entries": [
                    {
                        "phrase_raw": "date",
                        "phrase_norm": "date",
                        "kind": "legacy_alias",
                        "semantic_label": "date",
                        "semantic_order": 0,
                        "target_canonical": "Category",
                        "language": "en",
                        "source": "test",
                        "verification_status": "verified",
                        "provenance": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cd, "DICTIONARY_PATH", temp_json)
    cd._load_raw.cache_clear()
    cd._legacy_exact.cache_clear()
    cd._semantic_synonyms.cache_clear()
    cd._synonyms_by_label.cache_clear()

    try:
        canonical, confidence = dv.guess_canonical_column("date")
        assert canonical == "Category"
        assert confidence == "exact"
    finally:
        # Restore caches so later tests in this process see the real dictionary.
        cd._load_raw.cache_clear()
        cd._legacy_exact.cache_clear()
        cd._semantic_synonyms.cache_clear()
        cd._synonyms_by_label.cache_clear()


# ── 2. Snapshot compatibility, with the documented source exception ─────────


def test_snapshot_compat_after_migration():
    resolution = _load_baseline("resolution_snapshot.json")

    guess_mismatches = []
    source_mismatches = []
    other_mismatches = []

    for row in resolution["rows"]:
        raw = row["raw"]

        live_canonical, live_confidence = dv.guess_canonical_column(raw)
        if [live_canonical, live_confidence] != row["guess"]:
            guess_mismatches.append((raw, row["guess"], [live_canonical, live_confidence]))

        live_guess = t1._alias_fallback_guess(raw, False)

        frozen = row["fallback_ai_off"]
        exact_and_not_pii = (
            row["guess"][1] == "exact"
            and not row["pii_header"]
            and frozen["label"] != "personal"
        )

        if live_guess.canonical != frozen["canonical"] or live_guess.label != frozen["label"]:
            other_mismatches.append((raw, "canonical/label", frozen, live_guess))
            continue

        if live_guess.source != frozen["source"]:
            allowed = exact_and_not_pii and frozen["source"] == "local" and live_guess.source == "dictionary"
            if not allowed:
                source_mismatches.append((raw, frozen["source"], live_guess.source))

    assert not guess_mismatches, f"guess_canonical_column drifted: {guess_mismatches[:10]}"
    assert not other_mismatches, f"non-source fields drifted: {other_mismatches[:10]}"
    assert not source_mismatches, f"undocumented source drift: {source_mismatches[:10]}"


# ── 3. catalog_anchors() unchanged ───────────────────────────────────────────


def test_catalog_anchors_unchanged():
    frozen = _load_baseline("catalog_anchors.json")
    live = cc.catalog_anchors()
    frozen_pairs = [(a["label"], a["text"]) for a in frozen["anchors"]]
    assert live == frozen_pairs
    assert len(live) == frozen["anchor_count"] == 376


# ── 4. npz alignment ──────────────────────────────────────────────────────────


def test_npz_alignment():
    import numpy as np

    npz_path = Path(cc.__file__).resolve().parent / "catalog_embeddings.npz"
    data = np.load(npz_path)
    anchors = cc.catalog_anchors()
    assert data["matrix"].shape[0] == len(anchors)
    assert data["labels"].tolist() == [label for label, _ in anchors]


# ── 5. compatibility view matches frozen legacy alias map ───────────────────


def test_compatibility_view():
    frozen = _load_baseline("legacy_alias_map.json")
    reachable_entries = [e for e in frozen["entries"] if e.get("reachable", True)]

    compat = dv.COLUMN_ALIAS_MAP
    assert len(compat) == len(reachable_entries)

    for entry in reachable_entries:
        key = entry["legacy_key"]
        assert key in compat, f"missing key: {key!r}"
        assert compat[key] == entry["canonical"], f"value drift for {key!r}"


# ── 6. _FUZZY_KEYWORDS unchanged, same order ─────────────────────────────────


def test_fuzzy_keywords_unchanged():
    frozen = _load_baseline("fuzzy_keywords.json")
    frozen_pairs = [(e["keyword"], e["canonical"]) for e in frozen["entries"]]
    live_pairs = list(dv._FUZZY_KEYWORDS.items())
    assert live_pairs == frozen_pairs


# ── 7/8. source value on exact vs fuzzy hits ─────────────────────────────────


def test_dictionary_source_on_exact_hit():
    guess = t1._alias_fallback_guess("Bill Date", False)
    assert guess.source == "dictionary"
    assert guess.canonical == "Date"


def test_non_exact_stays_local():
    # "Total Qty" is not a COLUMN_ALIAS_MAP key, so it falls through to the
    # fuzzy keyword heuristic ("qty" substring -> Quantity).
    canonical, confidence = dv.guess_canonical_column("Total Qty")
    assert confidence == "fuzzy"

    guess = t1._alias_fallback_guess("Total Qty", False)
    assert guess.source == "local"
