"""
Comprehensive test suite for Module 2.3 — Safe Mapping Memory.

Tests:
1. Normalization rules (BOM, whitespace, punctuation, case, brackets, empty/unnamed).
2. Multiset template signatures (order-invariant, preserves multiplicity).
3. Collision detection for duplicate raw headers and distinct headers normalizing to same token.
4. Strict owner isolation (User A vs User B).
5. Explicit opt-in persistence and double-gating.
6. Ignore/unmapped invalidation.
7. Precedence hierarchy:
   - PII protection
   - Memory settling ambiguous columns
   - Decisive evidence overriding contradicting memory
8. One-target-per-field canonical collision resolution.
9. Concurrency: simultaneous atomic writes preserving all mappings without lost updates.
10. Corrupted storage resilience (zero HTTP 500 guarantee).
11. Authenticated API management routes.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import tempfile
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from app.core.config import MAPPING_MEMORY_DIR
from app.main import app
from app.services import column_understanding, mapping_memory


@pytest.fixture(autouse=True)
def isolated_memory_dir(monkeypatch, tmp_path):
    """Ensure each test runs with an isolated mapping memory directory."""
    mem_dir = tmp_path / "mapping_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mapping_memory, "MAPPING_MEMORY_DIR", str(mem_dir))
    return mem_dir


# ── 1. Normalization Tests ───────────────────────────────────────────────────

def test_normalize_header_variations():
    assert mapping_memory.normalize_header("\ufeffInvoice_No.") == "invoice no"
    assert mapping_memory.normalize_header("  [Rate] #  ") == "rate"
    assert mapping_memory.normalize_header("Bill-Date (Voucher)") == "bill date voucher"
    assert mapping_memory.normalize_header("Net   Amount") == "net amount"
    assert mapping_memory.normalize_header("`Item`") == "item"
    assert mapping_memory.normalize_header("") == "__empty__"
    assert mapping_memory.normalize_header("   ") == "__empty__"
    assert mapping_memory.normalize_header("Unnamed: 2") == "__empty__"
    assert mapping_memory.normalize_header("unnamed") == "__empty__"
    assert mapping_memory.normalize_header(None) == "__empty__"


# ── 2. Template Signature Multiset & Order Invariance ───────────────────────

def test_template_signature_invariance_and_multiplicity():
    # Order invariance
    cols1 = ["Date", "Item", "Rate", "Amount"]
    cols2 = ["Amount", "Rate", "Date", "Item"]
    sig1 = mapping_memory.compute_template_signature(cols1)
    sig2 = mapping_memory.compute_template_signature(cols2)
    assert sig1 == sig2
    assert len(sig1) == 16

    # Normalization invariance
    cols3 = [" date ", "[ITEM]", "Rate_#", "amount"]
    assert mapping_memory.compute_template_signature(cols3) == sig1

    # Multiplicity preservation: schemas with different duplicate counts must NOT collide
    cols_single = ["Date", "Rate", "Amount"]
    cols_double = ["Date", "Rate", "Rate", "Amount"]
    assert mapping_memory.compute_template_signature(cols_single) != mapping_memory.compute_template_signature(cols_double)


def test_template_signature_delimiter_safety():
    """
    Assert that delimiter characters like '|' within a header do not cause
    accidental collisions with separate columns: e.g. ["a|b"] vs ["a", "b"].
    """
    cols_joined = ["a|b"]
    cols_split = ["a", "b"]
    sig_joined = mapping_memory.compute_template_signature(cols_joined)
    sig_split = mapping_memory.compute_template_signature(cols_split)
    assert sig_joined != sig_split


# ── 3. Duplicate and Colliding Header Exclusion ──────────────────────────────

def test_colliding_header_tokens():
    # Duplicate raw headers
    headers_dup = ["Date", "Item", "Rate", "Rate", "Amount"]
    colliding = mapping_memory.get_colliding_tokens(headers_dup)
    assert "rate" in colliding
    assert "date" not in colliding

    # Distinct raw headers that normalize to the same token
    headers_distinct_colliding = ["Date", "Rate", " Rate ", "Amount"]
    colliding2 = mapping_memory.get_colliding_tokens(headers_distinct_colliding)
    assert "rate" in colliding2

    # Verify colliding tokens are excluded from memory recording and loading
    owner = "user1@example.com"
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers_dup,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Rate"],
        remember_mapping=True,
    )
    sig = mapping_memory.compute_template_signature(headers_dup)
    loaded = mapping_memory.load_template_mappings(owner, sig, colliding)
    assert "rate" not in loaded


# ── 4. Strict Owner Isolation ────────────────────────────────────────────────

def test_owner_isolation():
    user_a = "user_a@example.com"
    user_b = "user_b@example.com"
    headers = ["Invoice Date", "Rate", "Amount"]

    # User A records mapping
    mapping_memory.record_confirmed_mappings(
        owner=user_a,
        raw_headers=headers,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Rate"],
        remember_mapping=True,
    )

    sig = mapping_memory.compute_template_signature(headers)

    # User A sees it
    assert mapping_memory.load_template_mappings(user_a, sig).get("rate") == "Selling Price"

    # User B does NOT see it
    assert mapping_memory.load_template_mappings(user_b, sig) == {}

    # User B's list is empty
    assert mapping_memory.list_user_memories(user_b) == []


# ── 5. Explicit Opt-in Persistence ───────────────────────────────────────────

def test_opt_in_persistence_rules():
    owner = "test_optin@example.com"
    headers = ["Invoice Date", "Rate", "Amount"]
    sig = mapping_memory.compute_template_signature(headers)

    # 1. remember_mapping = False -> nothing saved
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Rate"],
        remember_mapping=False,
    )
    assert mapping_memory.load_template_mappings(owner, sig) == {}

    # 2. remember_mapping = True, but Rate not in user_selected_columns -> nothing saved
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Amount"],
        remember_mapping=True,
    )
    assert mapping_memory.load_template_mappings(owner, sig) == {}

    # 3. remember_mapping = True AND Rate in user_selected_columns -> saved!
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Rate"],
        remember_mapping=True,
    )
    assert mapping_memory.load_template_mappings(owner, sig).get("rate") == "Selling Price"


# ── 6. Ignore Invalidation ───────────────────────────────────────────────────

def test_ignore_invalidation():
    owner = "test_ignore@example.com"
    headers = ["Invoice Date", "Rate", "Amount"]
    sig = mapping_memory.compute_template_signature(headers)

    # Save mapping first
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"Rate": "Selling Price"},
        user_selected_columns=["Rate"],
        remember_mapping=True,
    )
    assert mapping_memory.load_template_mappings(owner, sig).get("rate") == "Selling Price"

    # User explicitly ignores Rate
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"Rate": ""},
        user_selected_columns=["Rate"],
        remember_mapping=True,
    )
    assert "rate" not in mapping_memory.load_template_mappings(owner, sig)


import asyncio

# ── 7. Precedence & Evidence Contradiction ───────────────────────────────────

def test_precedence_memory_settles_neutral_evidence():
    owner = "precedence_user@example.com"
    # Create DataFrame with ambiguous header where evidence is inconclusive
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "ColX": [10.0, 20.0, 30.0],
    })

    headers = list(df.columns)
    # Save memory: ColX -> Selling Price
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"ColX": "Selling Price"},
        user_selected_columns=["ColX"],
        remember_mapping=True,
    )

    reports, timings, notice, reason_code = asyncio.run(
        column_understanding.analyse(df, ai_consent=False, run_tier2=False, owner=owner)
    )

    colx_report = next(r for r in reports if r["raw_column"] == "ColX")
    assert colx_report["suggested_field"] == "Selling Price"
    assert colx_report["source"] == "memory"
    assert colx_report["needs_review"] is False
    assert colx_report["route"] == "local"


def test_precedence_decisive_evidence_overrides_memory_conflict():
    owner = "conflict_user@example.com"
    # GST % with Indian GST slab values {5, 12, 18} -> Module 2.1 evidence decisively says Tax
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 10,
        "Quantity": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
        "Rate": [100, 200, 300, 150, 250, 100, 200, 300, 150, 250],
        "GST %": [18, 12, 18, 5, 18, 12, 18, 18, 12, 5],
    })

    headers = list(df.columns)
    # Stale/contradictory memory claims GST % is "Discount"
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=headers,
        confirmed_mapping={"GST %": "Discount"},
        user_selected_columns=["GST %"],
        remember_mapping=True,
    )

    reports, timings, notice, reason_code = asyncio.run(
        column_understanding.analyse(df, ai_consent=False, run_tier2=False, owner=owner)
    )

    gst_report = next(r for r in reports if r["raw_column"] == "GST %")
    # Decisive evidence must NOT be overridden by contradictory memory
    assert gst_report["suggested_field"] == "Tax"
    assert gst_report["source"] == "evidence"
    # Contradiction flags the column for user review
    assert gst_report["needs_review"] is True
    assert "Tax" in gst_report["reason"] or "Discount" in gst_report["reason"]


def test_pii_shield_not_overridden_by_memory():
    owner = "pii_user@example.com"
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Customer Phone": ["9876543210", "9876543211"],
    })
    # Attempting to save PII to memory is blocked
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=list(df.columns),
        confirmed_mapping={"Customer Phone": "Selling Price"},
        user_selected_columns=["Customer Phone"],
        remember_mapping=True,
    )
    sig = mapping_memory.compute_template_signature(df.columns)
    assert mapping_memory.load_template_mappings(owner, sig) == {}

    reports, _, _, _ = asyncio.run(
        column_understanding.analyse(df, ai_consent=False, run_tier2=False, owner=owner)
    )
    phone_report = next(r for r in reports if r["raw_column"] == "Customer Phone")
    assert phone_report["suggested_field"] is None
    assert phone_report["semantic_label"] == "personal"


def test_cell_level_pii_shield_blocks_memory_and_storage():
    """
    Assert that ambiguous, non-PII headers whose cell values contain personal
    data (phones, emails):
    1. Are rejected by record_confirmed_mappings when df is provided.
    2. Cannot be mapped by memory or deterministic evidence.
    3. Are preserved as stored-only personal data with suggested_field=None.
    """
    owner = "cell_pii_user@example.com"
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "Misc_Ref": ["user1@example.com", "user2@corp.org", "user3@domain.in"],
        "Details_7": ["Call 9876543210", "Phone 9123456789", "Mob 9988776655"],
    })

    # Attempt to record mapping memory with remember_mapping=True
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=list(df.columns),
        confirmed_mapping={"Misc_Ref": "Customer", "Details_7": "Line Total"},
        user_selected_columns=["Misc_Ref", "Details_7"],
        remember_mapping=True,
        df=df,
    )

    sig = mapping_memory.compute_template_signature(df.columns)
    # Both columns contain PII in cells: memory must refuse to store them
    stored = mapping_memory.load_template_mappings(owner, sig)
    assert "misc ref" not in stored
    assert "details 7" not in stored

    # Even if an entry was forcibly inserted into the database, analyse must not apply it
    with mapping_memory.transaction(owner) as conn:
        conn.execute(
            """
            INSERT INTO template_mappings (template_signature, normalized_header, canonical_field, confirmed_at)
            VALUES (?, ?, ?, ?)
            """,
            (sig, "details 7", "Line Total", 1000.0),
        )

    reports, _, _, _ = asyncio.run(
        column_understanding.analyse(df, ai_consent=False, run_tier2=False, owner=owner)
    )
    details_report = next(r for r in reports if r["raw_column"] == "Details_7")
    misc_report = next(r for r in reports if r["raw_column"] == "Misc_Ref")

    assert details_report["suggested_field"] is None
    assert details_report["semantic_label"] == "personal"
    assert details_report["recognised_unused"] is True

    assert misc_report["suggested_field"] is None
    assert misc_report["semantic_label"] == "personal"
    assert misc_report["recognised_unused"] is True


def test_ignore_action_deletes_existing_memory_even_when_current_values_trigger_pii():
    """
    Assert that when an existing mapping is stored in memory, and the user
    subsequently uploads a file where that column contains cell-level PII values
    and explicitly marks it as Ignore (""):
    1. The previous memory entry is successfully deleted from SQLite memory.
    2. Zero cell values are persisted or exposed.
    3. The column is not recalled in future memory lookups.
    """
    owner = "pii_ignore_user@example.com"
    raw_headers = ["Date", "Notes_Ref", "Amount"]
    sig = mapping_memory.compute_template_signature(raw_headers)

    # 1. Pre-seed memory with an existing mapping for "Notes_Ref" -> "Selling Price"
    with mapping_memory.transaction(owner) as conn:
        conn.execute(
            """
            INSERT INTO template_mappings (template_signature, normalized_header, canonical_field, confirmed_at)
            VALUES (?, ?, ?, ?)
            """,
            (sig, "notes ref", "Selling Price", 1000.0),
        )

    # Verify pre-seeded mapping is present
    initial_mappings = mapping_memory.load_template_mappings(owner, sig)
    assert initial_mappings.get("notes ref") == "Selling Price"

    # 2. User uploads a file where "Notes_Ref" contains cell-level PII (phone numbers)
    df_with_pii = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "Notes_Ref": ["Call 9876543210", "Phone 9123456789", "Mob 9988776655"],
        "Amount": [100.0, 200.0, 300.0],
    })

    # 3. User explicitly marks "Notes_Ref" as Ignore ("") with remember_mapping=True
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=raw_headers,
        confirmed_mapping={"Notes_Ref": "", "Amount": "Line Total"},
        user_selected_columns=["Notes_Ref", "Amount"],
        remember_mapping=True,
        df=df_with_pii,
    )

    # 4. Verify that the previous memory entry for "notes ref" was purged!
    updated_mappings = mapping_memory.load_template_mappings(owner, sig)
    assert "notes ref" not in updated_mappings
    assert updated_mappings.get("amount") == "Line Total"


# ── 8. Canonical Role Collision ──────────────────────────────────────────────

def test_canonical_role_collision_demotes_second_column():
    owner = "collision_user@example.com"
    # Two columns in template: Rate1 and Rate2
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Rate1": [10.0, 20.0],
        "Rate2": [15.0, 25.0],
    })

    # Both mapped to Selling Price in memory
    mapping_memory.record_confirmed_mappings(
        owner=owner,
        raw_headers=list(df.columns),
        confirmed_mapping={"Rate1": "Selling Price", "Rate2": "Selling Price"},
        user_selected_columns=["Rate1", "Rate2"],
        remember_mapping=True,
    )

    reports, _, _, _ = asyncio.run(
        column_understanding.analyse(df, ai_consent=False, run_tier2=False, owner=owner)
    )

    r1 = next(r for r in reports if r["raw_column"] == "Rate1")
    r2 = next(r for r in reports if r["raw_column"] == "Rate2")

    # One keeps it, the other is demoted to unmapped
    suggested = [r1["suggested_field"], r2["suggested_field"]]
    assert "Selling Price" in suggested
    assert None in suggested


# ── 9. Concurrency: Simultaneous Atomic Writes ───────────────────────────────

def test_concurrent_updates_no_lost_updates():
    owner = "concurrent_user@example.com"
    headers = ["Date", "ColA", "ColB", "Total"]
    sig = mapping_memory.compute_template_signature(headers)

    def update_col(col_name, field):
        mapping_memory.record_confirmed_mappings(
            owner=owner,
            raw_headers=headers,
            confirmed_mapping={col_name: field},
            user_selected_columns=[col_name],
            remember_mapping=True,
        )

    # Run simultaneous updates for ColA and ColB
    with ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(update_col, "ColA", "Selling Price")
        f2 = executor.submit(update_col, "ColB", "Cost Price")
        f1.result()
        f2.result()

    loaded = mapping_memory.load_template_mappings(owner, sig)
    assert loaded.get("cola") == "Selling Price"
    assert loaded.get("colb") == "Cost Price"


# ── 10. Corrupted Storage Resilience ─────────────────────────────────────────

def test_corrupted_storage_fallback():
    owner = "corrupted_user@example.com"
    headers = ["Date", "Rate", "Amount"]

    # Write corrupt junk directly into user's db file
    db_path = mapping_memory._get_db_path(owner)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"CORRUPTED_SQLITE_JUNK_HEADER_12345")

    # load_template_mappings returns {} without crashing
    sig = mapping_memory.compute_template_signature(headers)
    assert mapping_memory.load_template_mappings(owner, sig) == {}

    # list_user_memories returns [] without crashing
    assert mapping_memory.list_user_memories(owner) == []


# ── 11. API Endpoints ────────────────────────────────────────────────────────

def test_mapping_memory_api_endpoints():
    client = TestClient(app)
    headers = ["Date", "Item", "Price"]
    user = "dev-user@localhost"

    # Pre-populate memory
    mapping_memory.record_confirmed_mappings(
        owner=user,
        raw_headers=headers,
        confirmed_mapping={"Price": "Selling Price"},
        user_selected_columns=["Price"],
        remember_mapping=True,
    )
    sig = mapping_memory.compute_template_signature(headers)

    # 1. GET /mapping-memory/
    res = client.get("/mapping-memory/")
    assert res.status_code == 200
    memories = res.json()
    assert len(memories) >= 1
    target_mem = next(m for m in memories if m["template_signature"] == sig)
    assert target_mem["mappings"]["price"] == "Selling Price"

    # 2. DELETE /mapping-memory/entry
    del_res = client.request(
        "DELETE",
        "/mapping-memory/entry",
        json={"template_signature": sig, "normalized_header": "price"},
    )
    assert del_res.status_code == 200
    assert mapping_memory.load_template_mappings(user, sig) == {}

    # 3. DELETE /mapping-memory/entry on non-existent returns 404
    del_res_404 = client.request(
        "DELETE",
        "/mapping-memory/entry",
        json={"template_signature": sig, "normalized_header": "non_existent"},
    )
    assert del_res_404.status_code == 404

    # 4. DELETE /mapping-memory/ (clear all)
    clear_res = client.delete("/mapping-memory/")
    assert clear_res.status_code == 200
    assert client.get("/mapping-memory/").json() == []
