"""
Phase 3 — offline evaluation of the column resolver against a golden set.

Methodology
-----------
This script measures, it does not tune. It loads
``tests/fixtures/golden_headers.csv`` and, for every header, calls
``app.services.tier1_classifier._alias_fallback_guess(header, ai_available=False)``
— the exact alias/fuzzy-keyword fallback path production uses when the
embedding tier is unavailable. ``ai_available=False`` means the function never
attempts to escalate to Gemini; nothing in this script makes a network call,
imports ``tier2_gemini``, or reads a Gemini API key. ``FASTEMBED_ENABLED`` is
forced to ``"false"`` before any app import so the embedding tier itself
(Tier 1's cosine-similarity path) cannot activate either — this script
evaluates the deterministic alias/fuzzy path only, by design, since that is
the part ``import_headers.py`` and the dictionary migration actually touch.

Routing classification
-----------------------
Every result is bucketed into one of three routing outcomes, from the
``ColumnGuess`` the resolver returns:

* **resolved-by-dictionary** — ``source == "dictionary"`` (an exact
  ``column_dictionary.json`` hit, i.e. ``guess_canonical_column`` returned
  confidence ``"exact"``).
* **resolved-by-fuzzy** — a keyword-substring match
  (``guess_canonical_column`` confidence ``"fuzzy"``), surfaced as a
  non-``None`` canonical with ``source == "local"`` and a fuzzy-only reason.
* **unresolved** — no canonical/semantic decision was reached locally; in a
  live system with AI enabled this is the column that would escalate to
  Tier 2.

Tuning vs. holdout
------------------
The golden CSV's ``split`` column marks each row ``tuning`` or ``holdout``.
This script reports both splits SEPARATELY and takes no action that could
let a holdout number influence behaviour: there is no threshold, weight, or
crosswalk entry in this codebase that this script adjusts. It only measures
and prints/writes a report. If you are tempted to add "if holdout accuracy is
low, change X", that change belongs in a separate, explicitly-reviewed commit
against the *tuning* split only, never driven by this script automatically.

Ambiguous-row handling
-----------------------
A golden row with ``expected_role == "ambiguous"`` has no single correct
canonical answer — ``candidate_roles`` lists the plausible readings, for
information only. Such a row is excluded from standard accuracy/precision/
recall (which would otherwise force an arbitrary "correct" choice), and is
instead scored as a **false mapping** if the resolver commits to any single
canonical/semantic answer for it. A resolver that reports "unresolved" for an
ambiguous row is doing the right thing and is not counted as a false mapping.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force the deterministic, offline alias/fuzzy path before any app import.
# This must happen before ``app.core.config`` is imported anywhere in the
# process (including transitively via tier1_classifier), exactly like
# ``tests/conftest.py`` does for the test suite.
os.environ["FASTEMBED_ENABLED"] = "false"
os.environ["AI_ASSIST_ENABLED"] = "false"
os.environ.setdefault("GEMINI_API_KEY", "")

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_GOLDEN = BACKEND / "tests" / "fixtures" / "golden_headers.csv"
DEFAULT_OUT = BACKEND / "app" / "data" / "staged" / "eval_report.json"

AMBIGUOUS_LABEL = "ambiguous"

ROUTING_DICTIONARY = "resolved-by-dictionary"
ROUTING_FUZZY = "resolved-by-fuzzy"
ROUTING_UNRESOLVED = "unresolved"


def _load_golden(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for row in reader:
            rows.append(
                {
                    "header": row["header"],
                    "expected_role": row["expected_role"],
                    "candidate_roles": [
                        c for c in (row.get("candidate_roles") or "").split("|") if c
                    ],
                    "industry": row.get("industry", ""),
                    "source": row.get("source", ""),
                    "source_url": row.get("source_url", ""),
                    "verification_status": row.get("verification_status", ""),
                    "split": row.get("split", "tuning"),
                }
            )
    return rows


def _classify_routing(guess) -> str:
    if guess.source == "dictionary":
        return ROUTING_DICTIONARY
    if guess.canonical is not None and guess.source == "local":
        return ROUTING_FUZZY
    return ROUTING_UNRESOLVED


def _resolved_role(guess) -> str | None:
    """The role this script scores against — canonical if present, else label."""
    if guess.canonical:
        return guess.canonical
    if guess.label and guess.label not in ("other",):
        return guess.label
    return None


def evaluate_row(row: dict[str, Any], alias_fallback_guess) -> dict[str, Any]:
    guess = alias_fallback_guess(row["header"], ai_available=False)
    routing = _classify_routing(guess)
    resolved = _resolved_role(guess)

    expected = row["expected_role"]
    is_ambiguous = expected.strip().lower() == AMBIGUOUS_LABEL

    outcome: dict[str, Any] = {
        "header": row["header"],
        "expected_role": expected,
        "is_ambiguous": is_ambiguous,
        "resolved_role": resolved,
        "routing": routing,
        "source": guess.source,
        "label": guess.label,
        "canonical": guess.canonical,
        "split": row["split"],
    }

    if is_ambiguous:
        false_mapping = resolved is not None
        outcome["false_mapping"] = false_mapping
        outcome["correct"] = None  # not a correctness-scored row
    else:
        correct = resolved == expected
        outcome["correct"] = correct
        # A "false mapping" for a non-ambiguous row is: resolver committed to
        # a DIFFERENT role than expected (as opposed to leaving it unresolved).
        outcome["false_mapping"] = (resolved is not None) and not correct

    return outcome


def _per_role_precision_recall(outcomes: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Precision/recall per expected role, over non-ambiguous rows only."""
    non_ambiguous = [o for o in outcomes if not o["is_ambiguous"]]

    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()

    for o in non_ambiguous:
        expected = o["expected_role"]
        resolved = o["resolved_role"]
        if resolved == expected:
            tp[expected] += 1
        else:
            fn[expected] += 1
            if resolved is not None:
                fp[resolved] += 1

    roles = set(tp) | set(fp) | set(fn)
    result = {}
    for role in sorted(roles):
        precision_den = tp[role] + fp[role]
        recall_den = tp[role] + fn[role]
        precision = tp[role] / precision_den if precision_den else None
        recall = tp[role] / recall_den if recall_den else None
        result[role] = {
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "tp": tp[role],
            "fp": fp[role],
            "fn": fn[role],
        }
    return result


def _top_confusions(outcomes: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    non_ambiguous = [o for o in outcomes if not o["is_ambiguous"]]
    confusions: Counter[tuple[str, str | None]] = Counter()
    for o in non_ambiguous:
        if not o["correct"]:
            confusions[(o["expected_role"], o["resolved_role"])] += 1
    ranked = confusions.most_common(limit)
    return [
        {"expected": pair[0], "got": pair[1], "count": count}
        for pair, count in ranked
    ]


def summarize_split(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    non_ambiguous = [o for o in outcomes if not o["is_ambiguous"]]
    ambiguous = [o for o in outcomes if o["is_ambiguous"]]

    correct = sum(1 for o in non_ambiguous if o["correct"])
    accuracy = correct / len(non_ambiguous) if non_ambiguous else None

    unresolved = sum(1 for o in outcomes if o["routing"] == ROUTING_UNRESOLVED)
    unresolved_share = unresolved / len(outcomes) if outcomes else None

    routing_counts = Counter(o["routing"] for o in outcomes)
    routing_proportions = {
        key: round(routing_counts.get(key, 0) / len(outcomes), 4) if outcomes else None
        for key in (ROUTING_DICTIONARY, ROUTING_FUZZY, ROUTING_UNRESOLVED)
    }

    false_mappings = [o for o in outcomes if o["false_mapping"]]
    ambiguous_false_mappings = [o for o in ambiguous if o["false_mapping"]]

    return {
        "row_count": len(outcomes),
        "non_ambiguous_count": len(non_ambiguous),
        "ambiguous_count": len(ambiguous),
        "accuracy_non_ambiguous": round(accuracy, 4) if accuracy is not None else None,
        "unresolved_share": round(unresolved_share, 4) if unresolved_share is not None else None,
        "routing_proportions": routing_proportions,
        "per_role_precision_recall": _per_role_precision_recall(outcomes),
        "top_confusions": _top_confusions(outcomes),
        "false_mapping_count": len(false_mappings),
        "false_mappings": [
            {
                "header": o["header"],
                "expected_role": o["expected_role"],
                "resolved_role": o["resolved_role"],
                "is_ambiguous": o["is_ambiguous"],
            }
            for o in false_mappings
        ],
        "ambiguous_false_mapping_count": len(ambiguous_false_mappings),
    }


def run_eval(golden_path: Path, split: str = "all") -> dict[str, Any]:
    from app.services.tier1_classifier import _alias_fallback_guess

    rows = _load_golden(golden_path)
    if split != "all":
        rows = [r for r in rows if r["split"] == split]

    outcomes = [evaluate_row(row, _alias_fallback_guess) for row in rows]

    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        by_split[outcome["split"]].append(outcome)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "backend/scripts/eval_columns.py",
        "golden_path": str(golden_path),
        "split_filter": split,
        "overall": summarize_split(outcomes),
        "by_split": {name: summarize_split(group) for name, group in sorted(by_split.items())},
    }
    return report


def _print_report(report: dict[str, Any]) -> None:
    print(f"Golden set: {report['golden_path']}")
    print(f"Split filter: {report['split_filter']}")
    print()
    for name, summary in report["by_split"].items():
        print(f"=== split: {name} ===")
        print(f"  rows: {summary['row_count']} (non_ambiguous={summary['non_ambiguous_count']}, ambiguous={summary['ambiguous_count']})")
        print(f"  accuracy (non-ambiguous): {summary['accuracy_non_ambiguous']}")
        print(f"  unresolved share: {summary['unresolved_share']}")
        print(f"  routing proportions: {summary['routing_proportions']}")
        print(f"  false mappings: {summary['false_mapping_count']} (of which ambiguous: {summary['ambiguous_false_mapping_count']})")
        if summary["top_confusions"]:
            print("  top confusions:")
            for c in summary["top_confusions"][:5]:
                print(f"    {c['expected']} -> {c['got']}: {c['count']}")
        print()
    print("=== overall ===")
    overall = report["overall"]
    print(f"  rows: {overall['row_count']}")
    print(f"  accuracy (non-ambiguous): {overall['accuracy_non_ambiguous']}")
    print(f"  unresolved share: {overall['unresolved_share']}")
    print(f"  routing proportions: {overall['routing_proportions']}")
    print(f"  false mappings: {overall['false_mapping_count']} (of which ambiguous: {overall['ambiguous_false_mapping_count']})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline, no-network evaluation of the alias/fuzzy column resolver against a golden set."
    )
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="Path to golden_headers.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path to write eval_report.json")
    parser.add_argument(
        "--split",
        choices=["tuning", "holdout", "all"],
        default="all",
        help="Restrict evaluation to one split (default: all, but always reported split-wise)",
    )
    args = parser.parse_args()

    report = run_eval(args.golden, args.split)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_report(report)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
