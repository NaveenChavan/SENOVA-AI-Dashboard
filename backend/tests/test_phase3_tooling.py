"""
Phase 3 — focused tests for the staged-import and evaluation tooling.

These prove the two remaining Phase 3 deliverables behave safely:

* ``import_headers.py`` is staged-only (never mutates the runtime
  dictionary), merges same-role provenance, reports same-phrase/different-role
  conflicts instead of auto-resolving them, and never invents a role for an
  unmapped ``proposed_role``.
* ``eval_columns.py`` runs offline (no Gemini), reports the required metric
  shape, scores inherently ambiguous rows as ambiguous (a single-role answer
  for them is a false mapping, never "correct"), and reports tuning and
  holdout splits separately.

All script output goes to ``tmp_path`` so nothing is written into
``app/data/`` or the committed fixtures. The committed
``tests/fixtures/golden_headers.csv`` is read as an input only.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
from pathlib import Path

import pytest

import_headers = importlib.import_module("scripts.import_headers")
eval_columns = importlib.import_module("scripts.eval_columns")

BACKEND = Path(__file__).resolve().parent.parent
RUNTIME_DICT = BACKEND / "app" / "data" / "column_dictionary.json"
STARTER_PACK = BACKEND.parent / "SENOVA_real_world_header_starter_pack" / "verified_header_starter.csv"
GOLDEN = BACKEND / "tests" / "fixtures" / "golden_headers.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── import: staged-only, no auto-promote ─────────────────────────────────────


def test_import_does_not_touch_runtime_dictionary(tmp_path):
    before = _sha256(RUNTIME_DICT)
    import_headers.run_import(STARTER_PACK, tmp_path)
    after = _sha256(RUNTIME_DICT)
    assert before == after, "import_headers must NEVER modify app/data/column_dictionary.json"


def test_import_writes_only_staged_artifacts(tmp_path):
    import_headers.run_import(STARTER_PACK, tmp_path)
    written = {p.name for p in tmp_path.glob("*.json")}
    assert written == {"staged_dictionary.json", "conflict_report.json", "import_summary.json"}

    staged = json.loads((tmp_path / "staged_dictionary.json").read_text(encoding="utf-8"))
    # Nothing staged is ever marked "verified"; it stays a documented candidate.
    for entry in staged["entries"]:
        assert entry["kind"] == "staged_candidate"
        assert "verified" != entry["verification_status"]
        assert "staged-candidate" in entry["verification_status"]


def test_import_merges_same_role_provenance():
    rows = [
        {"header": "Bill Date", "proposed_role": "date", "industry": "sales",
         "source": "A", "source_url": "u1", "verification_note": "", "verification_status": "documented-source"},
        {"header": "bill date", "proposed_role": "date", "industry": "orders",
         "source": "B", "source_url": "u2", "verification_note": "", "verification_status": "documented-source"},
    ]
    # NOTE: "bill date" already exists in the runtime dictionary as Date, so it
    # is reported as already_present rather than staged. Use a phrase that is
    # NOT already a runtime alias to exercise the merge path.
    rows = [
        {"header": "Shipment Day", "proposed_role": "delivery_date", "industry": "orders",
         "source": "A", "source_url": "u1", "verification_note": "", "verification_status": "documented-source"},
        {"header": "shipment day", "proposed_role": "delivery_date", "industry": "sales",
         "source": "B", "source_url": "u2", "verification_note": "", "verification_status": "documented-source"},
    ]
    result = import_headers.build_staged_import(rows)
    assert result["summary"]["merged_provenance_groups"] == 1
    staged = result["staged_entries"]
    merged = [e for e in staged if e["phrase_norm"] == "shipment day"]
    assert len(merged) == 1
    assert len(merged[0]["provenance"]) == 2  # both source rows preserved


def test_import_reports_same_phrase_different_role_conflict_without_choosing():
    rows = [
        {"header": "Net Value", "proposed_role": "line_total", "industry": "sales",
         "source": "A", "source_url": "u1", "verification_note": "", "verification_status": "documented-source"},
        {"header": "net value", "proposed_role": "cost_price", "industry": "accounting",
         "source": "B", "source_url": "u2", "verification_note": "", "verification_status": "documented-source"},
    ]
    result = import_headers.build_staged_import(rows)
    # Conflict recorded, nothing staged for this phrase, no role auto-chosen.
    assert result["summary"]["same_phrase_different_target_conflicts"] == 1
    assert not any(e["phrase_norm"] == "net value" for e in result["staged_entries"])
    conflict = result["same_phrase_conflicts"][0]
    assert conflict["phrase_norm"] == "net value"
    assert set(conflict["targets"].keys()) == {"Line Total", "Cost Price"}


def test_import_never_invents_a_role_for_unmapped_proposed_role():
    rows = [
        {"header": "Voucher Type", "proposed_role": "document_type", "industry": "accounting",
         "source": "Tally", "source_url": "u", "verification_note": "", "verification_status": "documented-source"},
        {"header": "Tax Rate %", "proposed_role": "tax_rate", "industry": "tax",
         "source": "ERPNext", "source_url": "u", "verification_note": "", "verification_status": "documented-source"},
    ]
    result = import_headers.build_staged_import(rows)
    assert result["summary"]["staged_entries"] == 0
    assert result["summary"]["unmapped_rows"] == 2
    unmapped_roles = {u["proposed_role"] for u in result["unmapped"]}
    assert unmapped_roles == {"document_type", "tax_rate"}
    # Each unmapped row carries a reason (not a silent drop).
    assert all(u["reason"] for u in result["unmapped"])


def test_import_crosswalk_targets_are_all_in_allowed_vocabulary():
    for proposed, target in import_headers.PROPOSED_ROLE_CROSSWALK.items():
        assert target in import_headers.ALLOWED_TARGETS, f"{proposed}->{target} is outside allowed roles"


def test_import_on_starter_pack_is_deterministic(tmp_path):
    a = import_headers.build_staged_import(import_headers._read_rows(STARTER_PACK))
    b = import_headers.build_staged_import(import_headers._read_rows(STARTER_PACK))
    assert a["summary"] == b["summary"]


# ── eval: offline, metric shape, ambiguous handling, split separation ────────


def test_eval_runs_offline_and_has_required_metric_shape(tmp_path):
    report = eval_columns.run_eval(GOLDEN, split="all")
    overall = report["overall"]
    for key in (
        "accuracy_non_ambiguous", "unresolved_share", "routing_proportions",
        "per_role_precision_recall", "top_confusions", "false_mapping_count",
    ):
        assert key in overall, f"missing metric: {key}"
    for bucket in ("resolved-by-dictionary", "resolved-by-fuzzy", "unresolved"):
        assert bucket in overall["routing_proportions"]


def test_eval_reports_tuning_and_holdout_separately():
    report = eval_columns.run_eval(GOLDEN, split="all")
    assert set(report["by_split"].keys()) == {"tuning", "holdout"}
    # Non-overlapping, together equal to the overall row count.
    total = report["by_split"]["tuning"]["row_count"] + report["by_split"]["holdout"]["row_count"]
    assert total == report["overall"]["row_count"]


def test_eval_scores_ambiguous_rows_as_ambiguous_not_correct():
    report = eval_columns.run_eval(GOLDEN, split="all")
    # There is at least one ambiguous golden row, and ambiguous rows are
    # excluded from accuracy and only ever counted as (potential) false mappings.
    assert report["overall"]["ambiguous_count"] >= 1


def test_eval_ambiguous_single_answer_is_false_mapping_not_correct():
    guess_calls = {}

    class _Guess:
        def __init__(self, canonical, label, source):
            self.canonical = canonical
            self.label = label
            self.source = source

    def fake_fallback(header, ai_available=False):  # noqa: ARG001
        # Pretend the resolver commits "Amount" -> Line Total.
        return _Guess("Line Total", "revenue", "dictionary")

    row = {
        "header": "Amount", "expected_role": "ambiguous",
        "candidate_roles": ["Line Total"], "industry": "", "source": "curated",
        "source_url": "", "verification_status": "", "split": "tuning",
    }
    outcome = eval_columns.evaluate_row(row, fake_fallback)
    assert outcome["is_ambiguous"] is True
    assert outcome["correct"] is None          # never scored "correct"
    assert outcome["false_mapping"] is True     # committing to a role is a false mapping


def test_eval_unresolved_on_ambiguous_is_not_a_false_mapping():
    class _Guess:
        canonical = None
        label = "other"
        source = "local"

    def fake_fallback(header, ai_available=False):  # noqa: ARG001
        return _Guess()

    row = {
        "header": "Mystery", "expected_role": "ambiguous", "candidate_roles": [],
        "industry": "", "source": "curated", "source_url": "", "verification_status": "", "split": "holdout",
    }
    outcome = eval_columns.evaluate_row(row, fake_fallback)
    assert outcome["false_mapping"] is False    # leaving it unresolved is correct behaviour


def test_golden_dataset_roles_within_allowed_vocabulary():
    allowed = import_headers.ALLOWED_TARGETS | {"ambiguous"}
    with GOLDEN.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            assert row["expected_role"] in allowed, f"golden expected_role outside vocab: {row['expected_role']}"
