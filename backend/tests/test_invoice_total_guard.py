"""
Module 2.4 — Invoice Total Repeat Guard (regression suite).

Playbook §2.4 (page 6) requires: a repeating invoice-level total must never be
summed row-wise ("counted five times"); use a line-level amount when present,
otherwise aggregate once per invoice OR mark the role ambiguous/ask.

These tests assert OBSERVABLE behaviour at three layers, not just internal
labels:

  * Upload gate        -> ``check_required_columns`` accept / reject
  * Column classification -> ``ambiguity_engine.evaluate`` decision + canonical
  * Actual money       -> ``sales_calculations.compute_summary_between`` revenue

Scope note: this suite is test-only. It documents the current, safe behaviour
and additionally pins the known manual-override edge case (a user may force an
invoice-total column to ``Line Total``) so any future regression is caught.
No production thresholds or formulas are changed by this file.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import ambiguity_engine as ae
from app.services import sales_calculations as sc
from app.utils.data_validator import check_required_columns, normalize_dataframe


# ── helpers ──────────────────────────────────────────────────────────────────

def _revenue(df: pd.DataFrame) -> float:
    """Actual revenue the engine reports for ``df`` (empty 'previous' frame)."""
    summary = sc.compute_summary_between(df, df.iloc[0:0])
    assert summary.revenue.available is True
    return float(summary.revenue.value)


def _normalize(raw: pd.DataFrame, mapping: dict[str, str]):
    """Run the real upload normalisation with an explicit user mapping."""
    return normalize_dataframe(raw, soft_fail=True, column_mapping=mapping)


# ── S1: one invoice, total repeated across five item rows, no line amount ──────

def test_s1_single_invoice_repeated_total_is_not_accepted_as_revenue():
    """
    A lone 'Amount' column that is actually a bill-level total repeated on 5
    rows must NOT silently become revenue. With no line-level amount and no
    Qty×Price, the upload gate must reject it (ask for a valid amount path),
    and the engine must NOT auto-map it to Line Total.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": ["INV-1"] * 5,
        "Item": [f"SKU{i}" for i in range(5)],
        "Amount": [1000, 1000, 1000, 1000, 1000],
    })

    accepted, missing = check_required_columns(df.columns)
    assert accepted is False
    assert "Line Total or (Quantity and Selling Price)" in missing

    res = ae.evaluate("Amount", df["Amount"], df, {"Invoice No": "Invoice No"})
    # Single invoice cannot be auto-proven -> must ask, never auto Line Total.
    assert res.decision == "ask"
    assert res.canonical != "Line Total"
    assert res.canonical is None


# ── S2: genuine Line Total present alongside a repeated invoice total ──────────

def test_s2_line_total_present_revenue_uses_line_level_not_invoice_total():
    """
    When a real per-row Line Total exists, revenue must come from it (sum=1000),
    and the sibling invoice-total column must not be auto-mapped to Line Total.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": ["INV-1"] * 5,
        "Item": [f"SKU{i}" for i in range(5)],
        "Line Total": [200, 200, 200, 200, 200],   # real per-row amounts, sum=1000
        "Invoice Amount": [1000, 1000, 1000, 1000, 1000],
    })

    accepted, missing = check_required_columns(df.columns)
    assert accepted is True and missing == []

    # Compute revenue through the real upload path (normalise parses dates and
    # keeps the genuine Line Total; the invoice-total column stays an extra).
    mapping = {
        "Date": "Date",
        "Invoice No": "Invoice No",
        "Item": "Item",
        "Line Total": "Line Total",
    }
    valid_df, _ = _normalize(df, mapping)
    assert _revenue(valid_df) == 1000.0

    res = ae.evaluate(
        "Invoice Amount", df["Invoice Amount"], df,
        {"Invoice No": "Invoice No", "Line Total": "Line Total"},
    )
    # Line Total already claimed -> engine must not hand a second Line Total out.
    assert res.canonical != "Line Total"


# ── S3: invoice total is the only amount candidate ────────────────────────────

def test_s3_invoice_total_only_candidate_is_gated_not_summed():
    """
    If the only amount-looking column is a repeated invoice total, the upload
    gate must reject (nothing to sum), both before and after applying whatever
    the engine concludes (canonical stays None).
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": ["INV-1"] * 5,
        "Item": [f"SKU{i}" for i in range(5)],
        "Bill Total": [1000, 1000, 1000, 1000, 1000],
    })

    accepted, missing = check_required_columns(df.columns)
    assert accepted is False
    assert "Line Total or (Quantity and Selling Price)" in missing

    res = ae.evaluate("Bill Total", df["Bill Total"], df, {"Invoice No": "Invoice No"})
    assert res.canonical is None  # never auto-confirmed as a revenue basis

    mapped_cols = {"Date"}
    if res.canonical:
        mapped_cols.add(res.canonical)
    accepted_after, missing_after = check_required_columns(mapped_cols)
    assert accepted_after is False


# ── S4: multiple invoices with different repeated totals ───────────────────────

def test_s4_multiple_invoices_detected_as_invoice_total_not_revenue():
    """
    Two invoices, each with its own total repeated across lines, provide enough
    evidence to auto-classify as an invoice total (canonical=None), so the
    column never becomes a summable revenue field.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 6,
        "Invoice No": ["INV-1", "INV-1", "INV-1", "INV-2", "INV-2", "INV-2"],
        "Item": [f"SKU{i}" for i in range(6)],
        "Amount": [1500, 1500, 1500, 900, 900, 900],
    })

    res = ae.evaluate("Amount", df["Amount"], df, {"Invoice No": "Invoice No"})
    assert res.decision == "auto"
    assert res.semantic == "invoice_total"
    assert res.canonical is None  # cannot be summed row-wise


# ── S5: missing / blank invoice identifiers ────────────────────────────────────

def test_s5_missing_invoice_ids_do_not_fabricate_invoice_grouping():
    """
    With blank/placeholder invoice ids there is no trustworthy grouping, so the
    engine must fall back to 'ask' rather than inventing an invoice-total verdict.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": [None, "", "  ", "nan", "n/a"],
        "Item": [f"SKU{i}" for i in range(5)],
        "Amount": [1000, 1000, 1000, 1000, 1000],
    })

    res = ae.evaluate("Amount", df["Amount"], df, {"Invoice No": "Invoice No"})
    assert res.decision == "ask"
    assert res.canonical is None


# ── S6: mixed line-level and invoice-level amount candidates ───────────────────

def test_s6_mixed_candidates_do_not_auto_map_invoice_total_to_line_total():
    """
    A file with a genuine line total (Col A ≈ Qty×SP) and an invoice total
    (Col B, repeats per invoice), both unmapped. The invoice-total column must
    never be auto-mapped to Line Total; the safe outcome is 'ask' (user picks).
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 4,
        "Invoice No": ["INV-1", "INV-1", "INV-2", "INV-2"],
        "Quantity": [2, 3, 1, 4],
        "Selling Price": [100, 100, 50, 50],
        "Col A": [200, 300, 50, 200],     # == Qty*SP -> genuine line total
        "Col B": [500, 500, 250, 250],    # repeats within invoice -> invoice total
    })

    batch = ae.evaluate_batch(["Col A", "Col B"], df, {"Invoice No": "Invoice No"})
    # Col B must never be auto-confirmed as Line Total.
    assert batch["Col B"].canonical != "Line Total"


# ── Module 2.4 guard: unit-level (assess_forced_line_total) ────────────────────

def test_guard_rejects_strong_multi_invoice_repeat():
    """
    A forced Line Total that repeats across the lines of ≥2 invoices is strong
    evidence of an invoice-level total -> verdict 'reject'.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 6,
        "Invoice No": ["INV-1", "INV-1", "INV-1", "INV-2", "INV-2", "INV-2"],
        "Amount": [1500, 1500, 1500, 900, 900, 900],
    })
    a = ae.assess_forced_line_total("Amount", df, {"Invoice No": "Invoice No", "Amount": "Line Total"})
    assert a.verdict == "reject"
    assert a.groups_tested >= ae.MIN_GROUPS_FOR_INVOICE_EVIDENCE
    assert "invoice" in a.message.lower()


def test_guard_warns_single_invoice_constant():
    """
    A single invoice whose amount is constant across its lines is ambiguous:
    verdict 'warn' (non-blocking), WITHOUT lowering MIN_GROUPS_FOR_INVOICE_EVIDENCE.
    """
    assert ae.MIN_GROUPS_FOR_INVOICE_EVIDENCE == 2  # threshold unchanged
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": ["INV-1"] * 5,
        "Amount": [1000] * 5,
    })
    a = ae.assess_forced_line_total("Amount", df, {"Invoice No": "Invoice No", "Amount": "Line Total"})
    assert a.verdict == "warn"
    assert a.message


def test_guard_ok_when_invoice_ids_missing():
    """Blank/placeholder invoice ids give no trustworthy grouping -> 'ok'."""
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 5,
        "Invoice No": [None, "", "  ", "nan", "n/a"],
        "Amount": [1000] * 5,
    })
    a = ae.assess_forced_line_total("Amount", df, {"Invoice No": "Invoice No", "Amount": "Line Total"})
    assert a.verdict == "ok"


def test_guard_ok_for_genuine_per_line_amounts():
    """Per-line amounts that vary within invoices are a real Line Total -> 'ok'."""
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 6,
        "Invoice No": ["INV-1", "INV-1", "INV-1", "INV-2", "INV-2", "INV-2"],
        "Amount": [200, 300, 150, 90, 400, 120],  # varies within each invoice
    })
    a = ae.assess_forced_line_total("Amount", df, {"Invoice No": "Invoice No", "Amount": "Line Total"})
    assert a.verdict == "ok"


def test_guard_ok_when_no_invoice_column():
    """No invoice column at all -> cannot prove invoice-level -> 'ok' (no guessing)."""
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 6,
        "Amount": [1000, 1000, 1000, 900, 900, 900],
    })
    a = ae.assess_forced_line_total("Amount", df, {"Amount": "Line Total"})
    assert a.verdict == "ok"


# ── Module 2.4 guard: API-level (confirm-mapping) ──────────────────────────────

def _upload_csv(client, csv_text: str) -> str:
    """Upload a CSV via the real endpoint and return its file_id."""
    resp = client.post(
        "/upload/",
        files={"file": ("invoice_total.csv", csv_text.encode(), "text/csv")},
        data={"ai_consent": "false"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["file_id"]


_MULTI_INVOICE_CSV = (
    "Bill No,Sale Date,Product,Amount\n"
    "INV-1,2026-01-01,SKU1,1500\n"
    "INV-1,2026-01-01,SKU2,1500\n"
    "INV-1,2026-01-01,SKU3,1500\n"
    "INV-2,2026-01-02,SKU4,900\n"
    "INV-2,2026-01-02,SKU5,900\n"
    "INV-2,2026-01-02,SKU6,900\n"
)

_SINGLE_INVOICE_CSV = (
    "Bill No,Sale Date,Product,Amount\n"
    "INV-1,2026-01-01,SKU1,1000\n"
    "INV-1,2026-01-01,SKU2,1000\n"
    "INV-1,2026-01-01,SKU3,1000\n"
    "INV-1,2026-01-01,SKU4,1000\n"
    "INV-1,2026-01-01,SKU5,1000\n"
)

_GENUINE_LINE_CSV = (
    "Bill No,Sale Date,Product,Amount\n"
    "INV-1,2026-01-01,SKU1,200\n"
    "INV-1,2026-01-01,SKU2,300\n"
    "INV-2,2026-01-02,SKU3,90\n"
    "INV-2,2026-01-02,SKU4,400\n"
    "INV-2,2026-01-02,SKU5,120\n"
)

_FORCE_MAPPING = {
    "Sale Date": "Date",
    "Bill No": "Invoice No",
    "Product": "Item",
    "Amount": "Line Total",
}


def test_api_rejects_forced_invoice_total_multi_invoice(client):
    """
    Strong multi-invoice evidence: confirm-mapping must reject with HTTP 400
    and NOT inflate revenue. The acknowledge flag must NOT bypass this.
    """
    file_id = _upload_csv(client, _MULTI_INVOICE_CSV)

    resp = client.post(
        f"/upload/{file_id}/confirm-mapping",
        json={"mapping": _FORCE_MAPPING},
    )
    assert resp.status_code == 400, resp.text
    assert "invoice" in resp.json()["detail"].lower()

    # Even with acknowledgement, a hard rejection is never bypassed.
    resp2 = client.post(
        f"/upload/{file_id}/confirm-mapping",
        json={"mapping": _FORCE_MAPPING, "acknowledge_warnings": True},
    )
    assert resp2.status_code == 400, resp2.text


def test_api_single_invoice_warns_then_proceeds_on_acknowledge(client):
    """
    Single-invoice ambiguous case: first confirm returns HTTP 409 with a visible
    warning and does NOT commit; re-confirming with acknowledge_warnings=True
    succeeds and the warning is echoed in the response.
    """
    file_id = _upload_csv(client, _SINGLE_INVOICE_CSV)

    resp = client.post(
        f"/upload/{file_id}/confirm-mapping",
        json={"mapping": _FORCE_MAPPING},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["requires_acknowledgement"] is True
    assert detail["warnings"] and any("per-line" in w.lower() or "bill-level" in w.lower()
                                      for w in detail["warnings"])

    resp2 = client.post(
        f"/upload/{file_id}/confirm-mapping",
        json={"mapping": _FORCE_MAPPING, "acknowledge_warnings": True},
    )
    assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    assert body["valid_count"] == 5
    assert body["warnings"], "acknowledged warning should still be surfaced"


def test_api_genuine_line_total_passes_without_warning(client):
    """Genuine per-line amounts confirm cleanly (HTTP 200, no warnings, correct rows)."""
    file_id = _upload_csv(client, _GENUINE_LINE_CSV)

    resp = client.post(
        f"/upload/{file_id}/confirm-mapping",
        json={"mapping": _FORCE_MAPPING},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid_count"] == 5
    assert body["warnings"] == []


def test_api_automatic_classification_still_detects_invoice_total():
    """
    Regression: the automatic engine still flags a multi-invoice repeated total
    as invoice_total (canonical=None), independent of the new manual guard.
    """
    df = pd.DataFrame({
        "Date": ["2026-01-01"] * 6,
        "Invoice No": ["INV-1", "INV-1", "INV-1", "INV-2", "INV-2", "INV-2"],
        "Amount": [1500, 1500, 1500, 900, 900, 900],
    })
    res = ae.evaluate("Amount", df["Amount"], df, {"Invoice No": "Invoice No"})
    assert res.decision == "auto"
    assert res.semantic == "invoice_total"
    assert res.canonical is None
