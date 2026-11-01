"""
Phase 3, Step 0 -- frozen-baseline guard tests.

These tests READ the frozen artifacts in ``fixtures/phase3_baseline/`` and
compare them against the live production resolver. They NEVER regenerate the
baseline: a drift makes the test fail, it does not silently rewrite the golden
file. (Regeneration is only ``scripts/snapshot_resolution.py --write``, run by
a human, which itself refuses to overwrite an existing baseline.)

Everything runs with FastEmbed and Gemini disabled -- the whole suite is forced
offline by ``conftest.py`` -- so this exercises the alias-map + fuzzy-keyword
path, i.e. ``tier1_classifier._alias_fallback_guess`` and
``data_validator.guess_canonical_column``. The embedding path is deliberately
NOT exercised here; it needs the model and is out of scope for Step 0.

After the Phase 3 migration (now applied) the SAME tests run against the
dictionary-backed resolver. The only permitted delta is the documented
``local`` -> ``dictionary`` source label on exact, non-PII hits — see
``test_fastembed_off_fallback_matches_frozen_baseline`` and
``test_exact_hit_now_reports_dictionary_source`` for where that exception is
applied explicitly, rather than by silently rewriting the golden file.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.services import column_catalog as cc
from app.services import tier1_classifier as t1
from app.utils import data_validator as dv

BASELINE_DIR = Path(__file__).resolve().parent / "fixtures" / "phase3_baseline"


def _load(name: str) -> dict:
    return json.loads((BASELINE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def resolution() -> dict:
    return _load("resolution_snapshot.json")


@pytest.fixture(scope="module")
def perturbation() -> dict:
    return _load("perturbation_snapshot.json")


@pytest.fixture(scope="module")
def migration() -> dict:
    return _load("alias_migration_table.json")


@pytest.fixture(scope="module")
def anchors() -> dict:
    return _load("catalog_anchors.json")


@pytest.fixture(scope="module")
def npz_align() -> dict:
    return _load("catalog_npz_alignment.json")


@pytest.fixture(scope="module")
def metrics() -> dict:
    return _load("baseline_metrics.json")


def _live_fallback(raw: str, ai_available: bool) -> dict:
    guess = dataclasses.asdict(t1._alias_fallback_guess(raw, ai_available))
    guess.pop("raw_column", None)
    return json.loads(json.dumps(guess, ensure_ascii=False))


# ── the artifacts exist and are self-consistent ──────────────────────────────


def test_all_frozen_artifacts_present():
    expected = {
        "legacy_alias_map.json", "fuzzy_keywords.json", "catalog_anchors.json",
        "catalog_npz_alignment.json", "resolution_snapshot.json",
        "perturbation_snapshot.json", "alias_migration_table.json",
        "baseline_metrics.json", "manifest.json",
    }
    present = {p.name for p in BASELINE_DIR.glob("*.json")}
    assert expected <= present, f"missing frozen artifacts: {expected - present}"


# ── resolution snapshot vs the LIVE resolver (the core no-drift guard) ────────


def test_guess_canonical_column_matches_frozen_baseline(resolution):
    """Every alias key, fuzzy keyword, synonym and probe resolves exactly as frozen."""
    mismatches = []
    for row in resolution["rows"]:
        raw = row["raw"]
        canonical, confidence = dv.guess_canonical_column(raw)
        if [canonical, confidence] != row["guess"]:
            mismatches.append((raw, row["guess"], [canonical, confidence]))
    assert not mismatches, f"guess_canonical_column drifted for {len(mismatches)}: {mismatches[:10]}"


def test_legacy_and_tier1_normalisation_match_frozen_baseline(resolution):
    for row in resolution["rows"]:
        raw = row["raw"]
        assert dv._normalize_col_name(raw) == row["legacy_key"], f"legacy_key drift: {raw!r}"
        assert t1._normalise_header(raw) == row["tier1_key"], f"tier1_key drift: {raw!r}"


def test_pii_header_flag_matches_frozen_baseline(resolution):
    for row in resolution["rows"]:
        assert dv._is_pii_header(row["raw"]) == row["pii_header"], f"pii flag drift: {row['raw']!r}"


def test_fastembed_off_fallback_matches_frozen_baseline(resolution):
    """The FastEmbed-unavailable ColumnGuess is identical, AI-off and AI-on.

    Documented Phase-3 exception: for rows where the frozen exact-hit (i.e.
    ``row["guess"][1] == "exact"``) applies and the header is not PII, the
    live ``source`` is now ``"dictionary"`` instead of ``"local"`` — this is
    the one field allowed to differ from the frozen baseline, and only in
    that direction. Every other field, and every row's source where the
    exception does not apply, must still match exactly.
    """
    off_bad, on_bad = [], []
    for row in resolution["rows"]:
        raw = row["raw"]
        allow_dictionary = (
            row["guess"][1] == "exact"
            and not row["pii_header"]
            and row["fallback_ai_off"]["label"] != "personal"
        )

        live_off = _live_fallback(raw, False)
        expected_off = dict(row["fallback_ai_off"])
        if allow_dictionary and expected_off.get("source") == "local" and live_off.get("source") == "dictionary":
            expected_off["source"] = "dictionary"
        if live_off != expected_off:
            off_bad.append(raw)

        live_on = _live_fallback(raw, True)
        expected_on = dict(row["fallback_ai_on"])
        if allow_dictionary and expected_on.get("source") == "local" and live_on.get("source") == "dictionary":
            expected_on["source"] = "dictionary"
        if live_on != expected_on:
            on_bad.append(raw)

    assert not off_bad, f"AI-off fallback drifted for: {off_bad[:10]}"
    assert not on_bad, f"AI-on fallback drifted for: {on_bad[:10]}"


def test_exact_hit_now_reports_dictionary_source(resolution):
    """Phase-3 migration: exact, non-PII hits now report source == 'dictionary'.

    "Non-PII" here means the row did not already resolve to the ``personal``
    label in the frozen baseline. ``_alias_fallback_guess`` runs its own PII
    gate (``extra_columns.is_personal_pii``), which is broader than
    ``dv._is_pii_header``/``row["pii_header"]`` — e.g. a bare "name" header is
    personal-PII there but not under the header-token check. That gate already
    short-circuits before the dictionary lookup pre-migration, so it is not a
    Phase 3 change; the dictionary-source exception only applies to rows that
    actually reach the alias/dictionary branch.
    """
    for row in resolution["rows"]:
        exact_and_not_pii = (
            row["guess"][1] == "exact"
            and not row["pii_header"]
            and row["fallback_ai_off"]["label"] != "personal"
        )
        live = t1._alias_fallback_guess(row["raw"], False)

        if exact_and_not_pii:
            assert live.source == "dictionary", (
                f"{row['raw']!r}: expected source='dictionary' for exact/non-PII hit, got {live.source!r}"
            )
        else:
            assert live.source != "dictionary", (
                f"{row['raw']!r}: source='dictionary' is only valid for exact/non-PII hits"
            )


def test_canonical_field_for_matches_frozen_baseline(resolution):
    """Semantic label -> canonical translation, incl. the conditional id->Invoice No gate."""
    for row in resolution["rows"]:
        for label, expected in row["semantic_canonicals"].items():
            assert cc.canonical_field_for(label, row["raw"]) == expected, (
                f"canonical_field_for({label!r}, {row['raw']!r}) drifted"
            )


# ── semantic-only synonyms with FastEmbed unavailable (reported limitation) ───


def test_semantic_only_synonym_behaviour_is_as_recorded(resolution, metrics):
    """
    Confirms the reported limitation: semantic-only synonyms (not alias keys)
    have no exact-hit path when FastEmbed is unavailable, so they resolve only
    through the fuzzy heuristic -- mostly not at all.
    """
    alias_keys = {e["key"] for e in _load("legacy_alias_map.json")["entries"]}
    semantic_only = [
        row for row in resolution["rows"]
        if any(o.startswith("synonym:") for o in row["origins"])
        and row["legacy_key"] not in alias_keys
    ]
    reported = metrics["semantic_only_with_fastembed_unavailable"]["count"]
    assert len(semantic_only) == reported

    # None of them is an exact hit in the FastEmbed-off path.
    for row in semantic_only:
        assert row["fallback_ai_off"]["score"] < 1.0 or row["fallback_ai_off"]["canonical"] is None \
            or row["guess"][1] != "exact", f"unexpected exact hit: {row['raw']!r}"


# ── migration table: lossless-as-legacy-alias, nothing force-mapped ───────────


def test_migration_every_alias_lossless_as_legacy_alias(migration):
    not_lossless = [r["key"] for r in migration["rows"] if not r["lossless_as_legacy_alias"]]
    assert not not_lossless, f"aliases not lossless as legacy_alias: {not_lossless}"


def test_migration_target_reproduces_live_guess(migration):
    """The legacy_alias target in the table == what guess_canonical_column returns today."""
    bad = []
    for row in migration["rows"]:
        if row["proposed_kind"] != "legacy_alias":
            continue
        live_canonical, live_conf = dv.guess_canonical_column(row["key"])
        if live_conf != "exact" or live_canonical != row["proposed_target_canonical"]:
            bad.append((row["key"], row["proposed_target_canonical"], [live_canonical, live_conf]))
    assert not bad, f"migration target mismatch: {bad[:10]}"


def test_migration_unreachable_keys_are_excluded_not_forced(migration):
    """Any key that can never match today must be excluded for review, never force-mapped."""
    for row in migration["rows"]:
        if not row["reachable"]:
            assert row["proposed_kind"] == "excluded_pending_review"
            assert row["proposed_target_canonical"] is None


def test_label_less_canonicals_are_not_lossless_as_semantic(migration, metrics):
    """
    The six canonicals with no semantic label (Stock On Hand, Payment Mode,
    Salesperson, Brand, Size, Colour) cannot be stored as a semantic label
    without losing their mapping -- which is exactly why they stay legacy_alias.
    """
    label_less = set(metrics["alias_map"]["canonicals_without_semantic_label"])
    for row in migration["rows"]:
        if row["current_canonical"] in label_less:
            assert not row["lossless_as_semantic"]


# ── catalog anchors + npz alignment (behaviour-critical, order-sensitive) ─────


def test_catalog_anchor_sequence_matches_frozen_baseline(anchors):
    live = cc.catalog_anchors()
    frozen = [(a["label"], a["text"]) for a in anchors["anchors"]]
    assert [list(x) for x in live] == [list(x) for x in frozen], "catalog_anchors() order/text drifted"
    assert len(live) == anchors["anchor_count"]


def test_npz_alignment_matches_frozen_baseline(npz_align):
    import numpy as np

    npz_path = Path(cc.__file__).resolve().parent / "catalog_embeddings.npz"
    data = np.load(npz_path)
    assert list(data["matrix"].shape) == npz_align["matrix_shape"]
    assert data["labels"].tolist() == [lbl for lbl, _ in cc.catalog_anchors()]
    assert npz_align["rows_equal_anchor_count"] is True
    assert npz_align["labels_equal_anchor_labels"] is True
    # Honesty guard: we did NOT verify the embedded text without the model.
    assert npz_align["text_alignment_verified"] is False
