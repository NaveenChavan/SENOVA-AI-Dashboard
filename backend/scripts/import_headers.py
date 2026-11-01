"""
Phase 3 — source-backed staged import of real-world header candidates.

What this script does
----------------------
Reads a CSV of real-world header examples (default: the repo's
``SENOVA_real_world_header_starter_pack/verified_header_starter.csv``) and
turns each row into a STAGED dictionary candidate — never a live one.

Policy (read this before changing the script)
-----------------------------------------------
* STAGED ONLY. This script NEVER writes to ``app/data/column_dictionary.json``
  and NEVER imports anything that would let it do so by accident. Its only
  outputs are three JSON files inside ``--out-dir``
  (default ``app/data/staged/``): ``staged_dictionary.json``,
  ``conflict_report.json``, ``import_summary.json``.
* NO AUTO-PROMOTE. A human (or a later, separate, explicitly-run promotion
  step that does not exist yet) decides if/when a staged entry is merged into
  the runtime dictionary. Running this script twice, or a hundred times, must
  never change ``app/data/column_dictionary.json``.
* NO INVENTED ALIASES. Every staged entry's ``target_canonical`` /
  ``target_semantic_label`` comes only from an explicit, reviewable
  ``PROPOSED_ROLE_CROSSWALK`` entry defined in this file. A ``proposed_role``
  value with no safe, unambiguous crosswalk entry is reported as unmapped —
  it is never guessed, fuzzy-matched, or silently coerced into the nearest
  canonical field.
* NO FABRICATED SOURCE EVIDENCE. Every staged entry carries the
  ``source_platform``/``source_url``/``verification_status`` from its input
  row untouched. The verification_status on a staged entry is never upgraded
  to "verified" by this script — that word is reserved for entries humans
  have actually checked against a real export.

Normalisation and schema reuse
-------------------------------
Phrases are normalised with ``app.utils.column_dictionary.legacy_key`` (the
exact same normalisation ``data_validator.guess_canonical_column`` uses), so
a staged entry's ``phrase_norm`` is directly comparable against the runtime
dictionary's exact-lookup index without introducing a second normalisation
scheme. The staged entry shape mirrors the schema documented in
``scripts/build_dictionary_json.py`` (``phrase_raw``, ``phrase_norm``,
``kind``, ``semantic_label``, ``target_canonical``, ``language``, ``source``,
``verification_status``, ``provenance``) plus import-specific provenance
fields (``source_platform``, ``source_url``, ``industry_module``,
``verification_note``).

Usage
-----
    python scripts/import_headers.py
    python scripts/import_headers.py --input PATH.csv --out-dir PATH
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.column_dictionary import _legacy_exact, legacy_key  # noqa: E402

REPO_ROOT = BACKEND.parent
DEFAULT_INPUT = REPO_ROOT / "SENOVA_real_world_header_starter_pack" / "verified_header_starter.csv"
DEFAULT_OUT_DIR = BACKEND / "app" / "data" / "staged"

#: The 19 canonical fields (MAPPABLE_FIELDS). Fixed — never extended here.
CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        "Category", "Cost Price", "Date", "Item", "Quantity", "Selling Price",
        "Discount", "Line Total", "MRP", "Stock On Hand", "Tax", "Branch",
        "Brand", "Colour", "Customer", "Invoice No", "Payment Mode",
        "Salesperson", "Size",
    }
)

#: The 17 semantic labels. Fixed — never extended here.
SEMANTIC_LABELS: frozenset[str] = frozenset(
    {
        "date", "quantity", "unit_price", "mrp", "cost", "revenue", "discount",
        "tax", "product", "currency", "category", "customer", "region",
        "status", "notes", "id", "other",
    }
)

ALLOWED_TARGETS: frozenset[str] = CANONICAL_FIELDS | SEMANTIC_LABELS

#: ─────────────────────────────────────────────────────────────────────────
#: Explicit proposed_role -> repo role crosswalk.
#:
#: Only genuinely unambiguous roles are mapped. Each value is either a
#: canonical field (from CANONICAL_FIELDS) or a semantic label (from
#: SEMANTIC_LABELS) — never a new vocabulary word. Anything not listed here
#: maps to None and is reported as unmapped/ambiguous, with candidates where
#: there is a sensible (but not safe-to-commit) guess.
#:
#: Rationale for exclusions is given inline for every role NOT mapped that
#: might look mappable at a glance.
#: ─────────────────────────────────────────────────────────────────────────
PROPOSED_ROLE_CROSSWALK: dict[str, str] = {
    # Dates
    "date": "Date",
    "delivery_date": "Date",  # only one plausible SENOVA field: Date
    # "due_date" excluded: a due date is not the transaction date (ambiguous intent).

    # Quantities
    "quantity": "Quantity",
    "incoming_quantity": "Quantity",
    "unavailable_quantity": "Quantity",
    "committed_quantity": "Quantity",
    # "unit_of_measure" / "unit_of_measure_basis" excluded: UOM is metadata, not a measure.

    # Prices
    "unit_price": "Selling Price",
    "cost_price": "Cost Price",
    "mrp": "MRP",

    # Totals / discounts / tax amounts
    "line_total": "Line Total",
    "discount": "Discount",
    "tax_amount": "Tax",
    # "tax_rate", "tax_type", "tax_name", "tax_category", "taxable_amount",
    # "tax_amount_or_type" excluded: rate/type/name/category are not a tax
    # money amount, and "tax_amount_or_type" is explicitly ambiguous in the
    # source note.
    # "invoice_total" excluded: a grand/invoice total is NOT the same thing as
    # a line total (it can include multiple lines + tax); mapping it to
    # "Line Total" would silently double-count tax into revenue.

    # Product / category identity
    "item": "Item",
    "item_description": "Item",
    "category": "Category",
    # "product_code" / "product_id" excluded: a SKU/code identifies the
    # product but is not the product NAME field "Item" expects.

    # People / parties
    "customer": "Customer",
    "salesperson": "Salesperson",
    # "customer_or_supplier" excluded by name: explicitly ambiguous in source.
    # "contact_person" excluded: a contact at an org, not the customer itself.

    # Location
    "location": "Branch",
    "warehouse": "Branch",
    # "bin_location", "source_location", "destination_location" excluded:
    # these are intra-warehouse location detail, not the shop Branch concept.

    # Stock
    "stock_on_hand": "Stock On Hand",

    # Payment
    "payment_method": "Payment Mode",

    # Identifiers that are genuinely invoice/document numbers
    "document_id": "Invoice No",
    "order_id": "Invoice No",

    # Semantic-only labels
    "currency": "currency",
    "status": "status",
}

#: Roles with NO safe mapping, annotated with *why* plus plausible candidates
#: for the human reviewer — never auto-applied.
AMBIGUOUS_ROLE_NOTES: dict[str, dict[str, Any]] = {
    "amount": {
        "reason": "Context-dependent: can be a line total or a transaction amount; "
        "source note for Shopify explicitly says currency context is required.",
        "candidates": ["Line Total"],
    },
    "invoice_total": {
        "reason": "A grand/invoice total is not a line total; mapping it there would "
        "double count tax/multi-line invoices into revenue.",
        "candidates": ["Line Total"],
    },
    "document_type": {
        "reason": "Describes the kind of document (voucher type), not a SENOVA field.",
        "candidates": [],
    },
    "customer_or_supplier": {
        "reason": "Explicitly ambiguous in source verification_note; depends on "
        "transaction direction.",
        "candidates": ["Customer"],
    },
    "tax_rate": {
        "reason": "A percentage rate, not a tax money amount.",
        "candidates": [],
    },
    "tax_type": {
        "reason": "Describes which tax (CGST/SGST/IGST), not an amount.",
        "candidates": [],
    },
    "tax_name": {
        "reason": "A label for the tax line, not an amount.",
        "candidates": [],
    },
    "tax_category": {
        "reason": "A classification used for tax reporting, not an amount.",
        "candidates": [],
    },
    "taxable_amount": {
        "reason": "The base the tax is computed on, not the tax itself nor the line total.",
        "candidates": ["Line Total", "tax"],
    },
    "tax_amount_or_type": {
        "reason": "Source note says 'ambiguous; inspect export schema'.",
        "candidates": ["Tax"],
    },
    "due_date": {
        "reason": "A payment due date is not the transaction/sale date.",
        "candidates": ["Date"],
    },
    "bin_location": {
        "reason": "Intra-warehouse bin, finer-grained than the Branch concept.",
        "candidates": ["Branch"],
    },
    "source_location": {
        "reason": "Transfer source godown/location, not a shop Branch.",
        "candidates": ["Branch"],
    },
    "destination_location": {
        "reason": "Transfer destination godown/location, not a shop Branch.",
        "candidates": ["Branch"],
    },
    "product_code": {
        "reason": "A SKU/code identifies a product but is not the Item name field.",
        "candidates": ["Item"],
    },
    "product_id": {
        "reason": "An internal identifier, not the Item name field.",
        "candidates": ["Item"],
    },
    "contact_person": {
        "reason": "A contact at an organisation, not the Customer field itself.",
        "candidates": ["Customer"],
    },
    "name": {
        "reason": "Bare 'Name' is context-dependent (could be customer, product, contact).",
        "candidates": ["Customer", "Item"],
    },
    "order_name": {
        "reason": "Source note says ambiguous in other contexts.",
        "candidates": ["Invoice No"],
    },
    "unit_of_measure": {
        "reason": "UOM metadata describing a quantity's unit, not a measure itself.",
        "candidates": [],
    },
    "unit_of_measure_basis": {
        "reason": "UOM metadata, needs review per source note.",
        "candidates": [],
    },
    "ledger": {
        "reason": "Accounting ledger name; role depends on the specific report.",
        "candidates": [],
    },
    "debit_amount": {
        "reason": "An accounting-side amount; not a sales-domain SENOVA field.",
        "candidates": [],
    },
    "credit_amount": {
        "reason": "An accounting-side amount; not a sales-domain SENOVA field.",
        "candidates": [],
    },
}


def _normalize_proposed_role(role: str) -> str:
    return role.strip().lower()


def _crosswalk(proposed_role: str) -> tuple[str | None, str]:
    """
    Map one proposed_role to a repo role.

    Returns ``(target_or_none, target_kind)`` where ``target_kind`` is
    ``"canonical"``, ``"semantic"``, or ``"unmapped"``.
    """
    normalized = _normalize_proposed_role(proposed_role)
    target = PROPOSED_ROLE_CROSSWALK.get(normalized)
    if target is None:
        return None, "unmapped"
    if target in CANONICAL_FIELDS:
        return target, "canonical"
    if target in SEMANTIC_LABELS:
        return target, "semantic"
    # Defensive: a crosswalk entry pointing outside the allowed vocabulary is
    # a bug in this script, not a legitimate mapping. Never happens if the
    # dict above is kept honest, but fail loudly rather than invent a role.
    raise ValueError(
        f"PROPOSED_ROLE_CROSSWALK['{normalized}'] = {target!r} is outside the "
        "allowed canonical/semantic vocabulary"
    )


def _detect_schema(fieldnames: list[str]) -> str:
    """
    Detect which of the two accepted input schemas this CSV uses.

    Returns ``"starter_pack"`` or ``"simple"``.
    """
    starter_cols = {"header_original", "proposed_role"}
    simple_cols = {"header", "role"}
    field_set = set(fieldnames)
    if starter_cols.issubset(field_set):
        return "starter_pack"
    if simple_cols.issubset(field_set):
        return "simple"
    raise ValueError(
        f"Unrecognised input schema. Columns found: {fieldnames!r}. "
        "Expected either the starter-pack schema (header_original, "
        "proposed_role, industry_module, source_platform, source_url, "
        "verification_note, verification_status) or the simple schema "
        "(header, role, industry, language, source, source_url)."
    )


def _read_rows(input_path: Path) -> list[dict[str, Any]]:
    """Read the input CSV and normalise both accepted schemas into one shape."""
    with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        schema = _detect_schema(fieldnames)
        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            if schema == "starter_pack":
                rows.append(
                    {
                        "header": (raw_row.get("header_original") or "").strip(),
                        "proposed_role": (raw_row.get("proposed_role") or "").strip(),
                        "industry": (raw_row.get("industry_module") or "").strip(),
                        "source": (raw_row.get("source_platform") or "").strip(),
                        "source_url": (raw_row.get("source_url") or "").strip(),
                        "verification_note": (raw_row.get("verification_note") or "").strip(),
                        "verification_status": (raw_row.get("verification_status") or "").strip(),
                    }
                )
            else:  # "simple"
                rows.append(
                    {
                        "header": (raw_row.get("header") or "").strip(),
                        "proposed_role": (raw_row.get("role") or "").strip(),
                        "industry": (raw_row.get("industry") or "").strip(),
                        "source": (raw_row.get("source") or "").strip(),
                        "source_url": (raw_row.get("source_url") or "").strip(),
                        "verification_note": "",
                        "verification_status": (raw_row.get("verification_status") or "candidate").strip(),
                    }
                )
    return rows


def _is_devanagari_or_kannada(text: str) -> bool:
    for ch in text:
        codepoint = ord(ch)
        if 0x0900 <= codepoint <= 0x097F or 0x0C80 <= codepoint <= 0x0CFF:
            return True
    return False


def _language_for(text: str) -> str:
    return "hi" if _is_devanagari_or_kannada(text) else "en"


def build_staged_import(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Core transform: crosswalk + dedupe + runtime-dictionary comparison.

    Returns a dict with keys ``staged_entries``, ``conflicts``,
    ``runtime_conflicts``, ``unmapped``, ``already_present``, ``summary``.
    """
    runtime_index = _legacy_exact()  # phrase_norm -> runtime JSON entry

    # phrase_norm -> mapped_target -> list of source rows (for merge/conflict detection)
    by_phrase_target: dict[str, dict[str | None, list[dict]]] = defaultdict(lambda: defaultdict(list))

    unmapped_rows: list[dict[str, Any]] = []

    for row in rows:
        header = row["header"]
        if not header:
            continue
        phrase_norm = legacy_key(header)
        target, target_kind = _crosswalk(row["proposed_role"])

        if target_kind == "unmapped":
            normalized_role = _normalize_proposed_role(row["proposed_role"])
            note = AMBIGUOUS_ROLE_NOTES.get(normalized_role)
            unmapped_rows.append(
                {
                    "header": header,
                    "phrase_norm": phrase_norm,
                    "proposed_role": row["proposed_role"],
                    "industry": row["industry"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "verification_note": row["verification_note"],
                    "reason": note["reason"] if note else "No entry in PROPOSED_ROLE_CROSSWALK for this proposed_role.",
                    "candidate_roles": note["candidates"] if note else [],
                }
            )
            continue

        by_phrase_target[phrase_norm][target].append(
            {
                "header": header,
                "proposed_role": row["proposed_role"],
                "target_kind": target_kind,
                "industry": row["industry"],
                "source": row["source"],
                "source_url": row["source_url"],
                "verification_note": row["verification_note"],
                "verification_status": row["verification_status"],
            }
        )

    staged_entries: list[dict[str, Any]] = []
    same_phrase_conflicts: list[dict[str, Any]] = []
    runtime_conflicts: list[dict[str, Any]] = []
    already_present: list[dict[str, Any]] = []
    merged_count = 0

    for phrase_norm, by_target in by_phrase_target.items():
        if len(by_target) > 1:
            # Same phrase_norm maps to more than one DIFFERENT target across
            # input rows -> conflict. Record both/all, pick neither.
            same_phrase_conflicts.append(
                {
                    "phrase_norm": phrase_norm,
                    "targets": {
                        (target if target is not None else "<none>"): rows_for_target
                        for target, rows_for_target in by_target.items()
                    },
                }
            )
            continue

        # Exactly one target for this phrase_norm across all input rows.
        ((target, rows_for_target),) = by_target.items()

        if len(rows_for_target) > 1:
            merged_count += 1

        sample = rows_for_target[0]
        target_kind = sample["target_kind"]

        runtime_entry = runtime_index.get(phrase_norm)
        if runtime_entry is not None:
            runtime_target = runtime_entry.get("target_canonical")
            if target_kind == "canonical" and runtime_target == target:
                already_present.append(
                    {
                        "phrase_norm": phrase_norm,
                        "header": sample["header"],
                        "target_canonical": target,
                        "runtime_source": runtime_entry.get("source"),
                    }
                )
                continue
            if target_kind == "canonical" and runtime_target != target:
                runtime_conflicts.append(
                    {
                        "phrase_norm": phrase_norm,
                        "header": sample["header"],
                        "incoming_target_canonical": target,
                        "runtime_target_canonical": runtime_target,
                        "runtime_source": runtime_entry.get("source"),
                    }
                )
                continue
            if target_kind == "semantic":
                # Runtime dictionary has an exact legacy_alias entry for this
                # phrase but the incoming row proposes a semantic-only label.
                # Legacy-alias precedence means runtime wins; report as a
                # runtime conflict rather than silently dropping the semantic
                # candidate or overwriting the canonical entry.
                runtime_conflicts.append(
                    {
                        "phrase_norm": phrase_norm,
                        "header": sample["header"],
                        "incoming_target_semantic_label": target,
                        "runtime_target_canonical": runtime_target,
                        "runtime_source": runtime_entry.get("source"),
                    }
                )
                continue

        provenance = [
            {
                "origin": "starter_pack_import",
                "header": r["header"],
                "proposed_role": r["proposed_role"],
                "industry": r["industry"],
                "source_platform": r["source"],
                "source_url": r["source_url"],
                "verification_note": r["verification_note"],
                "source_verification_status": r["verification_status"],
            }
            for r in rows_for_target
        ]

        entry = {
            "phrase_raw": sample["header"],
            "phrase_norm": phrase_norm,
            "kind": "staged_candidate",
            "semantic_label": target if target_kind == "semantic" else None,
            "target_canonical": target if target_kind == "canonical" else None,
            "language": _language_for(sample["header"]),
            "source": "starter_pack",
            # Never "verified" — this script only ever stages candidates.
            "verification_status": "documented-source; staged-candidate; not promoted",
            "provenance": provenance,
        }
        staged_entries.append(entry)

    summary = {
        "input_rows": len(rows),
        "unmapped_rows": len(unmapped_rows),
        "distinct_phrase_norms_mapped": len(by_phrase_target),
        "staged_entries": len(staged_entries),
        "merged_provenance_groups": merged_count,
        "same_phrase_different_target_conflicts": len(same_phrase_conflicts),
        "runtime_conflicts": len(runtime_conflicts),
        "already_present_in_runtime": len(already_present),
    }

    return {
        "staged_entries": staged_entries,
        "same_phrase_conflicts": same_phrase_conflicts,
        "runtime_conflicts": runtime_conflicts,
        "unmapped": unmapped_rows,
        "already_present": already_present,
        "summary": summary,
    }


def write_outputs(result: dict[str, Any], out_dir: Path, input_path: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    staged_payload = {
        "metadata": {
            "generated_at": generated_at,
            "generator": "backend/scripts/import_headers.py",
            "input_file": str(input_path),
            "policy": (
                "STAGED ONLY. Not imported by the application. Not auto-promoted "
                "into app/data/column_dictionary.json. A human must review and "
                "run a separate, explicit promotion step before any entry here "
                "affects runtime behaviour."
            ),
            "entry_count": len(result["staged_entries"]),
        },
        "entries": result["staged_entries"],
    }

    conflict_payload = {
        "metadata": {
            "generated_at": generated_at,
            "generator": "backend/scripts/import_headers.py",
            "input_file": str(input_path),
        },
        "same_phrase_different_target_conflicts": result["same_phrase_conflicts"],
        "runtime_conflicts": result["runtime_conflicts"],
        "unmapped_or_ambiguous": result["unmapped"],
        "already_present_in_runtime": result["already_present"],
    }

    summary_payload = {
        "generated_at": generated_at,
        "generator": "backend/scripts/import_headers.py",
        "input_file": str(input_path),
        "out_dir": str(out_dir),
        "counts": result["summary"],
    }

    (out_dir / "staged_dictionary.json").write_text(
        json.dumps(staged_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "conflict_report.json").write_text(
        json.dumps(conflict_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "import_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_import(input_path: Path, out_dir: Path) -> dict[str, Any]:
    rows = _read_rows(input_path)
    result = build_staged_import(rows)
    write_outputs(result, out_dir, input_path)
    return result


def _print_summary(result: dict[str, Any], out_dir: Path) -> None:
    print(f"Staged-only import complete. Wrote outputs to: {out_dir}")
    print("NOTE: app/data/column_dictionary.json was NOT touched (no auto-promote).")
    for key, value in result["summary"].items():
        print(f"  {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Staged, source-backed header import. Never writes to the runtime "
            "dictionary; never invents aliases. See module docstring."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV path (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory for staged files (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args()

    result = run_import(args.input, args.out_dir)
    _print_summary(result, args.out_dir)


if __name__ == "__main__":
    main()
