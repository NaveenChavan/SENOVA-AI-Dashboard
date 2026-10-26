"""Baseline audit script for Phase 1 of SENOVA Dictionary Improvement."""
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import pandas as pd
from app.utils.data_validator import COLUMN_ALIAS_MAP, _FUZZY_KEYWORDS, normalize_dataframe
from app.services.column_catalog import SEMANTIC_FIELDS, SEMANTIC_TO_CANONICAL
from app.services.column_understanding import analyse
from app.services.sales_calculations import _prepare
from app.services.discount_calculations import compute_discount

repo_root = backend_dir.parent

def run_baseline_audit():
    results = {}

    # 1. Dictionary structure & counts
    alias_map_count = len(COLUMN_ALIAS_MAP)
    fuzzy_count = len(_FUZZY_KEYWORDS)
    semantic_fields_count = len(SEMANTIC_FIELDS)
    catalog_synonyms_count = sum(len(f.synonyms) for f in SEMANTIC_FIELDS)
    unique_catalog_synonyms = len(set(s.lower().strip() for f in SEMANTIC_FIELDS for s in f.synonyms))

    alias_phrases = set(COLUMN_ALIAS_MAP.keys())
    fuzzy_phrases = set(_FUZZY_KEYWORDS.keys())
    overlap_alias_fuzzy = alias_phrases & fuzzy_phrases
    conflicts_alias_fuzzy = {
        p: {"alias_role": COLUMN_ALIAS_MAP[p], "fuzzy_role": _FUZZY_KEYWORDS[p]}
        for p in overlap_alias_fuzzy
        if COLUMN_ALIAS_MAP[p] != _FUZZY_KEYWORDS[p]
    }

    results["dictionary_counts"] = {
        "alias_map_entries": alias_map_count,
        "fuzzy_entries": fuzzy_count,
        "semantic_catalog_fields": semantic_fields_count,
        "semantic_catalog_synonyms": catalog_synonyms_count,
        "unique_semantic_synonyms": unique_catalog_synonyms,
        "alias_fuzzy_overlap": len(overlap_alias_fuzzy),
        "alias_fuzzy_role_conflicts": conflicts_alias_fuzzy,
    }

    # 2. Starter pack inventory
    starter_pack_csv = repo_root / "SENOVA_real_world_header_starter_pack" / "verified_header_starter.csv"
    starter_rows = []
    if starter_pack_csv.exists():
        with open(starter_pack_csv, encoding="utf-8") as f:
            starter_rows = list(csv.DictReader(f))
    
    source_reg_csv = repo_root / "SENOVA_real_world_header_starter_pack" / "source_register.csv"
    source_rows = []
    if source_reg_csv.exists():
        with open(source_reg_csv, encoding="utf-8") as f:
            source_rows = list(csv.DictReader(f))

    results["starter_pack_inventory"] = {
        "verified_header_starter_rows": len(starter_rows),
        "verified_header_starter_fields": list(starter_rows[0].keys()) if starter_rows else [],
        "source_register_rows": len(source_rows),
    }

    # 3. Electronics dataset regression check
    elec_csv = repo_root / "testing2" / "03_electronics_shopify_orders.csv"
    elec_df = pd.read_csv(elec_csv)
    reports, timings, notice, reason = asyncio.run(analyse(elec_df, ai_consent=False, run_tier2=False))
    elec_mapping = {r["raw_column"]: r["suggested_field"] for r in reports if r.get("suggested_field")}
    
    valid_elec, errors_elec = normalize_dataframe(elec_df, column_mapping=elec_mapping)
    prepped_elec = _prepare(valid_elec)
    disc_elec = compute_discount(valid_elec)
    
    results["electronics_regression"] = {
        "rows": len(elec_df),
        "valid_rows": len(valid_elec),
        "errors": len(errors_elec),
        "revenue": float(prepped_elec["_row_revenue"].sum()),
        "cost": float(prepped_elec["_row_cost"].sum()),
        "profit": float(prepped_elec["_row_profit"].sum()),
        "units": int(prepped_elec["Quantity"].sum()),
        "discount_given": float(disc_elec["discount_given"]),
        "discount_pct": round(float(disc_elec["discount_pct"]), 2),
    }

    # 4. Representative datasets audit
    rep_files = [
        "01_garment_tally_export.csv",
        "02_grocery_gst_invoice.csv",
        "03_electronics_shopify_orders.csv",
        "04_pharmacy_marg_stock.xlsx",
        "05_restaurant_pos_semicolon.csv",
        "06_footwear_boutique_wide.csv",
    ]
    rep_audit = {}
    for filename in rep_files:
        filepath = repo_root / "testing2" / filename
        if not filepath.exists():
            continue
        if filename.endswith(".xlsx"):
            df = pd.read_excel(filepath)
        elif "semicolon" in filename:
            df = pd.read_csv(filepath, sep=";")
        else:
            df = pd.read_csv(filepath)

        rep_reports, rep_timings, _, _ = asyncio.run(analyse(df, ai_consent=False, run_tier2=False))
        cols_summary = []
        for r in rep_reports:
            cols_summary.append({
                "header": r["raw_column"],
                "suggested_field": r.get("suggested_field"),
                "confidence": r.get("confidence"),
                "confidence_score": r.get("confidence_score"),
                "route": r.get("route"),
                "source": r.get("source"),
                "semantic_label": r.get("semantic_label"),
                "recognised_unused": r.get("recognised_unused"),
                "needs_review": r.get("needs_review"),
            })
        rep_audit[filename] = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": cols_summary
        }

    results["representative_datasets"] = rep_audit

    out_file = backend_dir / "app" / "data_baseline_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("Baseline audit completed successfully.")
    print("Report written to:", out_file)
    print("Electronics results:")
    print("  Revenue:", results["electronics_regression"]["revenue"])
    print("  Cost:", results["electronics_regression"]["cost"])
    print("  Profit:", results["electronics_regression"]["profit"])
    print("  Units:", results["electronics_regression"]["units"])
    print("  Discount Given:", results["electronics_regression"]["discount_given"])
    print("  Discount %:", results["electronics_regression"]["discount_pct"])

if __name__ == "__main__":
    run_baseline_audit()
