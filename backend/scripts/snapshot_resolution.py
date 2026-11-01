"""
Phase 3, Step 0 -- capture the PRE-MIGRATION column-resolution baseline.

This script is a measuring instrument, not part of the application. It imports
the current production resolver, records exactly what it does, and writes the
result as frozen JSON artifacts. It never edits production code or data.

How the baseline is created, reviewed and used
----------------------------------------------
1. CREATE  -- run ONCE, before any migration edit, from ``backend/``::

       .\\.venv\\Scripts\\python.exe scripts\\snapshot_resolution.py --write

   The artifacts land in ``tests/fixtures/phase3_baseline/``.
2. REVIEW  -- a human reads the artifacts and ``baseline_metrics.json`` and
   signs off. The ``manifest.json`` records the SHA-256 of every artifact and of
   the production source files the baseline was captured from.
3. FREEZE  -- after sign-off the artifacts are never regenerated to make a test
   pass. ``--write`` REFUSES to overwrite existing artifacts. The only override
   is ``--force-overwrite``, which is for a deliberate, separately approved
   re-baseline and prints a loud warning. Tests only READ the artifacts.
4. USE     -- ``tests/test_phase3_baseline.py`` compares the frozen artifacts
   with the live resolver. After the dictionary migration the same comparison
   runs against the new dictionary-backed resolver; the only permitted delta is
   the documented ``local`` -> ``dictionary`` source label on exact hits.

``--verify`` regenerates everything in memory and diffs it against the files on
disk. It is how determinism is demonstrated. It writes nothing.

Everything here runs with FastEmbed and Gemini disabled and makes no network
call. ``--real-model-check`` is the one optional exception: it loads the already
cached local embedding model (offline mode) to compare the stored anchor matrix
against a fresh encoding. It is never run by tests.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
DEFAULT_OUT = BACKEND / "tests" / "fixtures" / "phase3_baseline"

SCHEMA_VERSION = 1

ARTIFACT_FILES = (
    "legacy_alias_map.json",
    "fuzzy_keywords.json",
    "catalog_anchors.json",
    "catalog_npz_alignment.json",
    "resolution_snapshot.json",
    "perturbation_snapshot.json",
    "alias_migration_table.json",
    "baseline_metrics.json",
)

#: Production files the baseline is captured from; their hashes go in the manifest.
SOURCE_FILES = (
    "app/utils/data_validator.py",
    "app/services/column_catalog.py",
    "app/services/tier1_classifier.py",
    "app/services/embedder.py",
    "app/services/column_understanding.py",
)

#: Probe headers chosen because the code comments call out tricky behaviour
#: (substring order, the "discount"/"count" trap, PII, bare ids). They are
#: measurement inputs only. They are NOT proposed dictionary entries.
PROBES = (
    "MRP", "Total Qty", "Purchase Qty", "Discount", "Net Amount", "Purchase Rate",
    "Selling Rate", "Customer Email", "Customer Phone", "Unnamed: 0", "id", "ID",
    "Serial", "Customer Id", "Order Id", "Amount", "Rate", "Item Code", "Particulars",
)

FULLWIDTH_OFFSET = 0xFEE0


# ── helpers ──────────────────────────────────────────────────────────────────


def content_sha256(path: Path) -> str:
    """SHA-256 of a text file with CRLF folded to LF (git autocrlf-safe)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def with_ascii(row: dict, raw: str) -> dict:
    """Add an escaped copy of ``raw`` when it holds invisible/non-ASCII characters."""
    escaped = ascii(raw)[1:-1]
    if escaped != raw:
        row["raw_ascii"] = escaped
    return row


def script_kind(text: str) -> str:
    if all(ord(c) < 128 for c in text):
        return "latin_ascii"
    if any(0x0900 <= ord(c) <= 0x097F for c in text):
        return "devanagari"
    if any(0x0C80 <= ord(c) <= 0x0CFF for c in text):
        return "kannada"
    return "other_non_ascii"


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30, check=False
        )
        return out.stdout.strip()
    except Exception as exc:  # pragma: no cover - informational only
        return f"unavailable: {type(exc).__name__}"


def load_production():
    """Import the production modules with every external dependency disabled."""
    # Must be set before app.core.config is imported (same reason as conftest.py).
    os.environ["FASTEMBED_ENABLED"] = "false"
    os.environ["AI_ASSIST_ENABLED"] = "false"
    os.environ["GEMINI_API_KEY"] = ""
    sys.path.insert(0, str(BACKEND))

    from app.services import column_catalog as cc
    from app.services import embedder
    from app.services import tier1_classifier as t1
    from app.utils import data_validator as dv

    return dv, cc, t1, embedder


# ── source-level evidence (AST, no execution) ────────────────────────────────


def alias_literal_report(dv_path: Path) -> dict:
    """Read the COLUMN_ALIAS_MAP literal from source to expose silent duplicates."""
    tree = ast.parse(dv_path.read_text(encoding="utf-8"))
    dict_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "COLUMN_ALIAS_MAP":
            dict_node = node.value
        elif isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "COLUMN_ALIAS_MAP" for t in node.targets
        ):
            dict_node = node.value
    if not isinstance(dict_node, ast.Dict):
        return {"error": "COLUMN_ALIAS_MAP literal not found"}

    pairs = []
    for key_node, value_node in zip(dict_node.keys, dict_node.values):
        try:
            pairs.append((ast.literal_eval(key_node), ast.literal_eval(value_node)))
        except Exception:
            pairs.append((None, None))

    seen: dict[str, list] = defaultdict(list)
    for key, value in pairs:
        seen[key].append(value)
    duplicates = [
        {"key": key, "values": values, "conflicting_values": len(set(values)) > 1}
        for key, values in seen.items()
        if len(values) > 1
    ]
    return {
        "literal_entries": len(pairs),
        "unique_keys": len(seen),
        "duplicate_keys": duplicates,
    }


# ── artifact builders ────────────────────────────────────────────────────────


def perturbations_of(text: str) -> list[tuple[str, str]]:
    """Deterministic, documented perturbations. Unchanged results are dropped."""
    full = "".join(chr(ord(c) + FULLWIDTH_OFFSET) if 0x21 <= ord(c) <= 0x7E else
                   ("\u3000" if c == " " else c) for c in text)
    candidates = [
        ("upper", text.upper()),
        ("title", text.title()),
        ("pad_spaces", f"  {text}  "),
        ("double_internal_space", text.replace(" ", "  ", 1)),
        ("bom_prefix", "\ufeff" + text),
        ("bom_then_space", "\ufeff " + text),
        ("space_then_bom", " \ufeff" + text),
        ("underscore_for_space", text.replace(" ", "_")),
        ("space_for_underscore", text.replace("_", " ")),
        ("hyphen_for_space", text.replace(" ", "-")),
        ("trailing_colon", text + ":"),
        ("trailing_dot", text + "."),
        ("nbsp_for_space", text.replace(" ", "\u00a0")),
        ("tab_for_space", text.replace(" ", "\t")),
        ("fullwidth", full),
        ("nfd", unicodedata.normalize("NFD", text)),
    ]
    return [(kind, value) for kind, value in candidates if value != text]


def build_artifacts() -> dict[str, object]:
    dv, cc, t1, _embedder = load_production()
    import numpy as np

    alias_map = dict(dv.COLUMN_ALIAS_MAP)
    fuzzy_map = dict(dv._FUZZY_KEYWORDS)
    legacy_key = dv._normalize_col_name

    # Semantic synonyms, keyed by legacy normalisation so alias keys can be matched.
    sem_by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    synonym_rows = []
    for field in cc.SEMANTIC_FIELDS:
        for position, synonym in enumerate(field.synonyms):
            sem_by_key[legacy_key(synonym)].append((field.label, synonym))
            synonym_rows.append((field.label, position, synonym))

    # ── legacy alias map ────────────────────────────────────────────────────
    literal = alias_literal_report(Path(dv.__file__))
    legacy_alias = {
        "schema_version": SCHEMA_VERSION,
        "description": "COLUMN_ALIAS_MAP exactly as the live module exposes it, in dict order.",
        "normalisation": "data_validator._normalize_col_name = col.strip().lstrip('\\ufeff').lower()",
        "source_literal": literal,
        "entries": [
            with_ascii(
                {
                    "index": i,
                    "key": key,
                    "canonical": canonical,
                    "legacy_key": legacy_key(key),
                    "reachable": legacy_key(key) == key,
                },
                key,
            )
            for i, (key, canonical) in enumerate(alias_map.items())
        ],
    }

    fuzzy = {
        "schema_version": SCHEMA_VERSION,
        "description": "_FUZZY_KEYWORDS in dict order. Order is behaviour: the first key found inside the header wins.",
        "entries": [
            with_ascii(
                {"index": i, "keyword": kw, "canonical": canonical,
                 "reachable": kw == kw.lower()},
                kw,
            )
            for i, (kw, canonical) in enumerate(fuzzy_map.items())
        ],
    }

    # ── catalog anchors ─────────────────────────────────────────────────────
    anchors = cc.catalog_anchors()
    description_texts = {f.description for f in cc.SEMANTIC_FIELDS}
    anchor_rows = [
        with_ascii(
            {"index": i, "label": label, "kind": "description" if text in description_texts else "synonym",
             "text": text},
            text,
        )
        for i, (label, text) in enumerate(anchors)
    ]
    sequence_hash = hashlib.sha256(
        "\n".join(f"{label}\t{text}" for label, text in anchors).encode("utf-8")
    ).hexdigest()
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "description": "Complete catalog_anchors() sequence: exact text, label and order.",
        "anchor_count": len(anchors),
        "sequence_sha256": sequence_hash,
        "labels_in_order": list(cc.SEMANTIC_LABELS),
        "anchors_per_label": dict(Counter(label for label, _ in anchors)),
        "anchors": anchor_rows,
    }

    # ── npz alignment ───────────────────────────────────────────────────────
    npz_path = BACKEND / "app" / "services" / "catalog_embeddings.npz"
    npz_info: dict = {"path": "app/services/catalog_embeddings.npz", "exists": npz_path.exists()}
    if npz_path.exists():
        data = np.load(npz_path)
        matrix = data["matrix"]
        labels = data["labels"].tolist()
        anchor_labels = [label for label, _ in anchors]
        mismatch = next((i for i, (a, b) in enumerate(zip(labels, anchor_labels)) if a != b), None)
        norms = np.linalg.norm(matrix, axis=1)
        npz_info.update(
            {
                "keys": sorted(data.files),
                "file_bytes": npz_path.stat().st_size,
                "file_sha256": raw_sha256(npz_path),
                "matrix_shape": list(matrix.shape),
                "matrix_dtype": str(matrix.dtype),
                "label_count": len(labels),
                "anchor_count": len(anchors),
                "rows_equal_anchor_count": matrix.shape[0] == len(anchors),
                "labels_equal_anchor_labels": labels == anchor_labels,
                "first_label_mismatch_index": mismatch,
                "labels_per_label": dict(Counter(labels)),
                "row_norm_min": round(float(norms.min()), 6),
                "row_norm_max": round(float(norms.max()), 6),
                "text_alignment_verified": False,
                "text_alignment_note": (
                    "Only shape and label order are checked here. The embedded TEXT of each row "
                    "cannot be verified without the model; see --real-model-check."
                ),
            }
        )

    # ── per-phrase resolution snapshot ──────────────────────────────────────
    phrases: dict[str, list[str]] = {}

    def add(raw: str, origin: str) -> None:
        phrases.setdefault(raw, []).append(origin)

    for key in alias_map:
        add(key, "alias")
    for kw in fuzzy_map:
        add(kw, "fuzzy")
    for label, _pos, synonym in synonym_rows:
        add(synonym, f"synonym:{label}")
    for probe in PROBES:
        add(probe, "probe")

    def guess_dict(raw: str, ai_available: bool) -> dict:
        guess = dataclasses.asdict(t1._alias_fallback_guess(raw, ai_available))
        guess.pop("raw_column", None)
        return json.loads(json.dumps(guess, ensure_ascii=False))

    def fuzzy_matches(key: str) -> list[list[str]]:
        return [[kw, canonical] for kw, canonical in fuzzy_map.items() if kw in key]

    resolution_rows = []
    for raw, origins in phrases.items():
        canonical, confidence = dv.guess_canonical_column(raw)
        key = legacy_key(raw)
        sem_labels = sorted({label for label, _ in sem_by_key.get(key, [])})
        row = {
            "raw": raw,
            "origins": origins,
            "legacy_key": key,
            "tier1_key": t1._normalise_header(raw),
            "pii_header": dv._is_pii_header(raw),
            "guess": [canonical, confidence],
            "conflicted": t1._normalise_header(raw).lower() in t1._ALIAS_MAP_CONFLICTS,
            "semantic_labels": sem_labels,
            "semantic_canonicals": {label: cc.canonical_field_for(label, raw) for label in sem_labels},
            "fallback_ai_off": guess_dict(raw, False),
            "fallback_ai_on": guess_dict(raw, True),
        }
        if confidence != "exact":
            matches = fuzzy_matches(key)
            row["fuzzy_matches"] = matches
            row["fuzzy_order_dependent"] = len({c for _, c in matches}) > 1
        resolution_rows.append(with_ascii(row, raw))

    resolution = {
        "schema_version": SCHEMA_VERSION,
        "description": (
            "Pre-migration outcome for every alias key, fuzzy keyword, semantic synonym and probe. "
            "'guess' is guess_canonical_column(); 'fallback_ai_*' is tier1._alias_fallback_guess() "
            "(the FastEmbed-unavailable path) with AI unavailable / available."
        ),
        "row_count": len(resolution_rows),
        "rows": resolution_rows,
    }

    # ── perturbations ───────────────────────────────────────────────────────
    per_canonical: dict[str, int] = Counter()
    bases: list[tuple[str, str]] = []
    for key, canonical in alias_map.items():
        if per_canonical[canonical] < 2:
            per_canonical[canonical] += 1
            bases.append((key, "alias"))
    non_ascii = [s for _, _, s in synonym_rows if script_kind(s) != "latin_ascii"]
    for synonym in dict.fromkeys(non_ascii).keys():
        if len([b for b in bases if b[1] == "non_ascii_synonym"]) >= 6:
            break
        bases.append((synonym, "non_ascii_synonym"))
    first_semantic_only: dict[str, str] = {}
    for label, _pos, synonym in synonym_rows:
        if legacy_key(synonym) not in alias_map and label not in first_semantic_only \
                and script_kind(synonym) == "latin_ascii":
            first_semantic_only[label] = synonym
    bases.extend((s, "semantic_only_synonym") for s in first_semantic_only.values())

    perturbation_rows = []
    for base, base_kind in dict.fromkeys(bases):
        base_guess = list(dv.guess_canonical_column(base))
        for kind, raw in perturbations_of(base):
            canonical, confidence = dv.guess_canonical_column(raw)
            perturbation_rows.append(
                with_ascii(
                    {
                        "base": base,
                        "base_kind": base_kind,
                        "kind": kind,
                        "raw": raw,
                        "base_guess": base_guess,
                        "guess": [canonical, confidence],
                        "changed_vs_base": [canonical, confidence] != base_guess,
                        "legacy_key": legacy_key(raw),
                        "fallback_ai_off": guess_dict(raw, False),
                    },
                    raw,
                )
            )
    perturbation = {
        "schema_version": SCHEMA_VERSION,
        "description": "Representative perturbations with the raw input and the LEGACY outcome.",
        "base_count": len(dict.fromkeys(bases)),
        "row_count": len(perturbation_rows),
        "rows": perturbation_rows,
    }

    # ── migration table ─────────────────────────────────────────────────────
    migration_rows = []
    for key, canonical in alias_map.items():
        reachable = legacy_key(key) == key
        label = t1._semantic_from_canonical(canonical)
        round_trip = cc.canonical_field_for(label, key) if label else None
        if label is None:
            sem_ok, sem_reason = False, "canonical has no semantic label (passthrough canonical)"
        elif label == cc.UNKNOWN_LABEL:
            sem_ok, sem_reason = False, "canonical maps to the 'other' label"
        elif round_trip == canonical:
            sem_ok, sem_reason = True, None
        else:
            sem_ok, sem_reason = False, (
                f"canonical_field_for({label!r}, key) returns {round_trip!r}, not {canonical!r}"
            )
        sem_matches = sem_by_key.get(legacy_key(key), [])
        if not reachable:
            kind, lossless, reason = "excluded_pending_review", False, (
                "legacy_key(key) != key: this key can never match today. It must not start matching."
            )
        else:
            kind, lossless, reason = "legacy_alias", True, None
        migration_rows.append(
            with_ascii(
                {
                    "key": key,
                    "legacy_key": legacy_key(key),
                    "reachable": reachable,
                    "current_canonical": canonical,
                    "proposed_kind": kind,
                    "proposed_target_canonical": canonical if reachable else None,
                    "lossless_as_legacy_alias": lossless,
                    "legacy_alias_reason": reason,
                    "tier1_semantic_label": label,
                    "semantic_round_trip_canonical": round_trip,
                    "lossless_as_semantic": sem_ok,
                    "semantic_reason": sem_reason,
                    "also_semantic_synonym_of": sorted({lbl for lbl, _ in sem_matches}),
                },
                key,
            )
        )
    migration = {
        "schema_version": SCHEMA_VERSION,
        "description": (
            "Alias-to-target migration table. 'legacy_alias' carries target_canonical directly and "
            "reproduces guess_canonical_column() exactly. 'lossless_as_semantic' says whether the alias "
            "could instead be stored as a semantic label and still round-trip through "
            "canonical_field_for(), including the conditional id -> Invoice No promotion."
        ),
        "row_count": len(migration_rows),
        "rows": migration_rows,
    }

    metrics = build_metrics(
        dv, cc, t1, alias_map, fuzzy_map, synonym_rows, sem_by_key, resolution_rows,
        perturbation_rows, migration_rows, literal, npz_info,
    )

    return {
        "legacy_alias_map.json": legacy_alias,
        "fuzzy_keywords.json": fuzzy,
        "catalog_anchors.json": catalog,
        "catalog_npz_alignment.json": npz_info,
        "resolution_snapshot.json": resolution,
        "perturbation_snapshot.json": perturbation,
        "alias_migration_table.json": migration,
        "baseline_metrics.json": metrics,
    }


def build_metrics(dv, cc, t1, alias_map, fuzzy_map, synonym_rows, sem_by_key, resolution_rows,
                  perturbation_rows, migration_rows, literal, npz_info) -> dict:
    legacy_key = dv._normalize_col_name
    rows_by_raw = {r["raw"]: r for r in resolution_rows}

    unreachable_alias = [k for k in alias_map if legacy_key(k) != k]
    unreachable_fuzzy = [k for k in fuzzy_map if k != k.lower()]
    overlap = sorted(set(alias_map) & set(fuzzy_map))
    overlap_conflicts = [
        {"phrase": p, "alias": alias_map[p], "fuzzy": fuzzy_map[p]}
        for p in overlap if alias_map[p] != fuzzy_map[p]
    ]

    # Synonyms
    syn_total = len(synonym_rows)
    syn_keys = [legacy_key(s) for _, _, s in synonym_rows]
    syn_unique = len(set(syn_keys))
    cross_label = [
        {"legacy_key": key, "labels": sorted({lbl for lbl, _ in pairs})}
        for key, pairs in sem_by_key.items() if len({lbl for lbl, _ in pairs}) > 1
    ]
    in_label_dupes = [
        key for key, count in Counter(syn_keys).items() if count > 1
        and len({lbl for lbl, _ in sem_by_key[key]}) == 1
    ]
    script_counts = Counter(script_kind(s) for _, _, s in synonym_rows)
    per_label = Counter(label for label, _, _ in synonym_rows)

    semantic_only = [(lbl, s) for lbl, _, s in synonym_rows if legacy_key(s) not in alias_map]
    alias_and_synonym = syn_total - len(semantic_only)

    # Semantic-only behaviour with FastEmbed unavailable and AI unavailable.
    outcomes = Counter()
    outcome_examples: dict[str, list[str]] = defaultdict(list)
    escalated_if_ai = 0
    per_label_outcomes: dict[str, Counter] = defaultdict(Counter)
    for label, synonym in semantic_only:
        row = rows_by_raw[synonym]
        off = row["fallback_ai_off"]
        expected = cc.canonical_field_for(label, synonym)
        if off["label"] == "personal":
            outcome = "pii_shield_stored_only"
        elif off["canonical"] is None and off["label"] in {"currency", "status", "notes"}:
            outcome = "recognised_not_analysed"
        elif off["canonical"] is not None:
            outcome = "fuzzy_agrees_with_label" if off["canonical"] == expected else "fuzzy_disagrees_with_label"
        else:
            outcome = "unresolved_no_suggestion"
        outcomes[outcome] += 1
        per_label_outcomes[label][outcome] += 1
        if len(outcome_examples[outcome]) < 8:
            outcome_examples[outcome].append(synonym)
        if row["fallback_ai_on"]["route"] == "gemini":
            escalated_if_ai += 1

    # Alias vs semantic disagreement (two systems naming different targets).
    disagreements = []
    for key, canonical in alias_map.items():
        sem = rows_by_raw.get(key, {}).get("semantic_canonicals", {})
        if sem and any(v != canonical for v in sem.values()):
            disagreements.append({"key": key, "alias_canonical": canonical, "semantic": sem})

    # PII shield vs alias/synonym
    pii_blocked_alias = [k for k in alias_map if dv._is_pii_header(k)]
    pii_blocked_syn = sorted({s for _, _, s in synonym_rows if dv._is_pii_header(s)})

    # Unresolved across the three phrase sets, under the legacy resolver.
    def unresolved(keys):
        return [k for k in keys if tuple(rows_by_raw[k]["guess"]) == (None, "none")]

    alias_unresolved = unresolved(alias_map)
    fuzzy_kw_unresolved = unresolved(fuzzy_map)
    syn_unresolved = sorted({s for _, _, s in synonym_rows if tuple(rows_by_raw[s]["guess"]) == (None, "none")})

    alias_exact_misses = [k for k in alias_map if rows_by_raw[k]["guess"][1] != "exact"]
    order_dependent = [r["raw"] for r in resolution_rows if r.get("fuzzy_order_dependent")]

    pert_counter = Counter()
    pert_by_kind: dict[str, Counter] = defaultdict(Counter)
    for r in perturbation_rows:
        base_conf = r["base_guess"][1]
        conf = r["guess"][1]
        change = "unchanged" if not r["changed_vs_base"] else f"{base_conf}->{conf}"
        pert_counter[change] += 1
        pert_by_kind[r["kind"]][change] += 1

    migration_lossless_legacy = sum(1 for m in migration_rows if m["lossless_as_legacy_alias"])
    not_lossless_sem = [m["key"] for m in migration_rows if not m["lossless_as_semantic"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "alias_map": {
            "live_entries": len(alias_map),
            "source_literal": literal,
            "reachable": len(alias_map) - len(unreachable_alias),
            "unreachable_legacy_keys": unreachable_alias,
            "canonical_distribution": dict(Counter(alias_map.values())),
            "canonicals_without_semantic_label": sorted(
                {c for c in alias_map.values() if t1._semantic_from_canonical(c) is None}
            ),
            "exact_lookup_misses_for_own_keys": alias_exact_misses,
            "own_keys_unresolved": alias_unresolved,
        },
        "fuzzy_keywords": {
            "entries": len(fuzzy_map),
            "unreachable_keywords": unreachable_fuzzy,
            "overlap_with_alias_keys": len(overlap),
            "overlap_role_conflicts": overlap_conflicts,
            "own_keywords_unresolved": fuzzy_kw_unresolved,
        },
        "semantic_synonyms": {
            "fields": len(cc.SEMANTIC_FIELDS),
            "total": syn_total,
            "unique_by_legacy_key": syn_unique,
            "per_label": dict(per_label),
            "script_breakdown": dict(script_counts),
            "kannada_synonyms_present": script_counts.get("kannada", 0) > 0,
            "that_are_alias_keys": alias_and_synonym,
            "semantic_only_count": len(semantic_only),
            "duplicate_within_one_label": in_label_dupes,
            "cross_label_duplicates": cross_label,
            "unresolved_by_legacy_resolver": syn_unresolved,
        },
        "semantic_only_with_fastembed_unavailable": {
            "note": (
                "These synonyms are NOT alias-map keys. With FastEmbed unavailable they can only "
                "resolve through the fuzzy keyword heuristic, never through an exact hit."
            ),
            "count": len(semantic_only),
            "outcomes": dict(outcomes),
            "per_label_outcomes": {k: dict(v) for k, v in per_label_outcomes.items()},
            "examples": dict(outcome_examples),
            "would_escalate_to_gemini_if_ai_available": escalated_if_ai,
        },
        "conflicts_and_ambiguity": {
            "_ALIAS_MAP_CONFLICTS_size": len(t1._ALIAS_MAP_CONFLICTS),
            "alias_vs_fuzzy_role_conflicts": len(overlap_conflicts),
            "alias_vs_semantic_disagreements": disagreements,
            "cross_label_duplicate_synonyms": len(cross_label),
            "fuzzy_order_dependent_phrases": len(order_dependent),
            "fuzzy_order_dependent_examples": order_dependent[:15],
            "pii_blocked_alias_keys": pii_blocked_alias,
            "pii_blocked_synonyms": pii_blocked_syn,
        },
        "perturbations": {
            "rows": len(perturbation_rows),
            "outcome_vs_base": dict(pert_counter),
            "by_kind": {k: dict(v) for k, v in pert_by_kind.items()},
        },
        "migration_table": {
            "rows": len(migration_rows),
            "lossless_as_legacy_alias": migration_lossless_legacy,
            "excluded_pending_review": [m["key"] for m in migration_rows if m["proposed_kind"] != "legacy_alias"],
            "not_lossless_as_semantic": len(not_lossless_sem),
            "not_lossless_as_semantic_keys": not_lossless_sem,
        },
        "catalog": {
            "anchor_count": len(cc.catalog_anchors()),
            "npz_matrix_shape": npz_info.get("matrix_shape"),
            "npz_rows_equal_anchor_count": npz_info.get("rows_equal_anchor_count"),
            "npz_labels_equal_anchor_labels": npz_info.get("labels_equal_anchor_labels"),
        },
    }


# ── manifest, writing, verification ──────────────────────────────────────────


def build_manifest(out_dir: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": _git("rev-parse", "HEAD"),
        "git_tracked_changes": _git("status", "--porcelain", "--untracked-files=no") or "none",
        "python": sys.version.split()[0],
        "hash_note": "Text files are hashed with CRLF folded to LF so git autocrlf cannot change them.",
        "artifacts": {name: content_sha256(out_dir / name) for name in ARTIFACT_FILES},
        "source_files_at_capture": {rel: content_sha256(BACKEND / rel) for rel in SOURCE_FILES},
        "catalog_embeddings_npz_sha256": raw_sha256(BACKEND / "app" / "services" / "catalog_embeddings.npz"),
    }


def cmd_write(out_dir: Path, force: bool) -> int:
    existing = [n for n in (*ARTIFACT_FILES, "manifest.json") if (out_dir / n).exists()]
    if existing and not force:
        print(
            "REFUSING to overwrite frozen baseline artifacts:\n  " + "\n  ".join(existing)
            + "\nThe baseline is frozen after review. Use --verify to compare, or "
            "--force-overwrite only for a separately approved re-baseline.",
            file=sys.stderr,
        )
        return 2
    if existing and force:
        print("WARNING: --force-overwrite is replacing a frozen baseline.", file=sys.stderr)

    artifacts = build_artifacts()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in artifacts.items():
        (out_dir / name).write_text(dump_json(obj), encoding="utf-8", newline="\n")
    (out_dir / "manifest.json").write_text(dump_json(build_manifest(out_dir)), encoding="utf-8", newline="\n")
    for name in (*ARTIFACT_FILES, "manifest.json"):
        print(f"wrote {out_dir / name}")
    return 0


def cmd_verify(out_dir: Path) -> int:
    missing = [n for n in ARTIFACT_FILES if not (out_dir / n).exists()]
    if missing:
        print("Missing artifacts: " + ", ".join(missing), file=sys.stderr)
        return 2
    fresh = build_artifacts()
    bad = []
    for name, obj in fresh.items():
        on_disk = (out_dir / name).read_bytes().replace(b"\r\n", b"\n")
        if on_disk != dump_json(obj).encode("utf-8"):
            bad.append(name)
    if bad:
        print("DIFFERS from frozen baseline: " + ", ".join(bad), file=sys.stderr)
        return 1
    print(f"OK: {len(fresh)} artifacts regenerate byte-identically to the frozen baseline (nothing written).")
    return 0


def cmd_real_model_check(out_dir: Path) -> int:
    """Optional: re-encode the anchors with the locally cached model and compare."""
    os.environ["HF_HUB_OFFLINE"] = "1"  # never download
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    _dv, cc, _t1, embedder = load_production()
    import numpy as np

    target = out_dir / "catalog_npz_realmodel_check.json"
    result: dict = {"schema_version": SCHEMA_VERSION, "offline": True}
    try:
        from app.core.config import FASTEMBED_CACHE_PATH, FASTEMBED_MODEL

        result.update({"configured_model": FASTEMBED_MODEL, "cache_path": FASTEMBED_CACHE_PATH})
        model = embedder._load_model()
        result["model_loaded"] = model is not None
        result["loaded_model_name"] = getattr(model, "model_name", None)
        result["model_name_matches_config"] = result["loaded_model_name"] == FASTEMBED_MODEL
        if model is None:
            result["status"] = "model_unavailable_offline"
        else:
            anchors = cc.catalog_anchors()
            fresh = embedder.encode([text for _label, text in anchors])
            stored = np.load(BACKEND / "app" / "services" / "catalog_embeddings.npz")["matrix"]
            if fresh is None or fresh.shape != stored.shape:
                result["status"] = "shape_mismatch"
                result["fresh_shape"] = None if fresh is None else list(fresh.shape)
                result["stored_shape"] = list(stored.shape)
            else:
                cosine = (fresh * stored).sum(axis=1)
                worst = np.argsort(cosine)[:10]
                result.update(
                    {
                        "status": "compared",
                        "rows": int(stored.shape[0]),
                        "cosine_min": round(float(cosine.min()), 6),
                        "cosine_mean": round(float(cosine.mean()), 6),
                        "rows_below_0_999": int((cosine < 0.999).sum()),
                        "rows_below_0_95": int((cosine < 0.95).sum()),
                        "worst_rows": [
                            {"index": int(i), "label": anchors[int(i)][0], "text": anchors[int(i)][1],
                             "cosine": round(float(cosine[int(i)]), 6)}
                            for i in worst
                        ],
                    }
                )
    except Exception as exc:
        result["status"] = f"error: {type(exc).__name__}: {exc}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_json(result), encoding="utf-8", newline="\n")
    print(dump_json({k: v for k, v in result.items() if k != "worst_rows"}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="create the frozen baseline (refuses to overwrite)")
    mode.add_argument("--verify", action="store_true", help="regenerate in memory and diff against disk; writes nothing")
    mode.add_argument("--real-model-check", action="store_true", help="optional offline model comparison of the npz")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force-overwrite", action="store_true", help="deliberate, separately approved re-baseline only")
    args = parser.parse_args(argv)

    if args.write:
        return cmd_write(args.out_dir, args.force_overwrite)
    if args.verify:
        return cmd_verify(args.out_dir)
    return cmd_real_model_check(args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
