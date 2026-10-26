"""
Module 2.1 — Deterministic Evidence Rules Engine.

Purpose
-------
After Tier 1 classifies headers and Tier 2 (Gemini) optionally resolves
ambiguous ones, a third class of problem remains: columns whose *header* is
genuinely ambiguous between two or more canonical roles, but whose *values*
contain statistical evidence strong enough to settle the question without AI.

Examples the engine resolves deterministically:
- ``Rate`` or ``Unit Price`` — is it a unit selling price, or an invoice total?
  If ``Rate × Quantity ≈ Line Total`` in ≥ 90 % of rows, it is a unit price.
  If it stays constant within each Invoice No group, it is more likely a tax
  rate or list price.
- ``Amount`` / ``Total`` / ``Value`` — is it a line total, or a repeating
  invoice total?  If it is identical across all rows that share an Invoice No,
  it is an invoice-level field and must NOT be summed row-wise.
- ``GST %`` / ``Rate %`` — values all lie within the Indian GST slab set
  {0, 5, 12, 18, 28} or their decimal equivalents {0.05, 0.12, 0.18, 0.28}?
  Then it is a tax-rate column, not a discount or selling-price column.
- ``Name`` — does the file also have phone, email, address, or GSTIN neighbours?
  Then it is a Customer column.  Does it have SKU, HSN, or Category neighbours?
  Then it is an Item column.

The engine never fabricates numbers.  Every verdict cites the statistical
evidence that produced it.  When evidence is insufficient or contradictory the
engine returns ``decision="ask"`` so the caller (Grouped Clarification Dialog in
Module 2.2) can surface the question to the user.

Integration contract
--------------------
* Input:  a raw ``pd.DataFrame`` plus the column name to be evaluated, plus
  (optionally) the set of columns that are already mapped.
* Output: an ``EvidenceResult`` dataclass with:
    - ``decision``:   "auto" | "ask" | "conflict"
    - ``canonical``:  str | None      (the resolved canonical field, if auto)
    - ``semantic``:   str | None      (internal label)
    - ``confidence``: float 0–1
    - ``reason``:     str             (written for a shop owner, not a developer)
    - ``evidence``:   list[str]       (bullet-point facts that drove the verdict)
    - ``candidates``: list[str]       (canonical fields still in play for "ask")

* This module is called from ``column_understanding.analyse()`` before Tier 2
  so that cleanly settled columns never consume a Gemini slot.
* It never modifies the DataFrame, never raises, and never makes a network call.

Test isolation note
-------------------
All statistical helpers are pure functions of their arguments; no global state
is mutated.  The module is fully testable without FastEmbed or Gemini.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import pandas as pd


# ── Constants ─────────────────────────────────────────────────────────────────

#: Minimum fraction of row-level cross-checks that must pass to declare
#: ``Qty × value ≈ Line Total`` (and therefore label value as unit_price).
UNIT_PRICE_MATCH_THRESHOLD = 0.90

#: Absolute tolerance as a fraction of the computed product when comparing
#: ``Qty × Rate`` to a known Line Total column.
UNIT_PRICE_ABS_TOL_FRACTION = 0.01   # 1 % rounding tolerance

#: If a column repeats the same value across ≥ this share of Invoice-No groups,
#: it is an invoice-level field, not a line-level one.
INVOICE_REPEAT_THRESHOLD = 0.90

#: GST slab values that unambiguously identify a tax-rate column.
_GST_SLABS_PCT: frozenset[float] = frozenset({0.0, 5.0, 12.0, 18.0, 28.0})
#: Same as decimal fractions (e.g. 0.18 instead of 18).
_GST_SLABS_DEC: frozenset[float] = frozenset({0.0, 0.05, 0.12, 0.18, 0.28})

#: Minimum fraction of non-null rows whose value lies in the GST slab set.
GST_SLAB_COVERAGE = 0.90

#: Header token sets for Name-column disambiguation.
_CUSTOMER_CONTEXT_TOKENS: frozenset[str] = frozenset(
    {"phone", "mobile", "email", "address", "gstin", "gst", "contact", "pincode", "city"}
)
_ITEM_CONTEXT_TOKENS: frozenset[str] = frozenset(
    {"sku", "hsn", "barcode", "code", "style", "category", "size", "colour", "color", "brand", "unit"}
)

#: Discount-percentage header keywords.  If the header itself says "%" or "pct"
#: and the values are in [0, 100], the column is a percentage, not a unit price.
_DISCOUNT_PCT_TOKENS: frozenset[str] = frozenset({"%", "pct", "percent", "discount%", "disc%"})

#: Maximum cardinality for a column whose values are GST amounts (not rates).
#: A column with only {0, 5, 12, 18, 28} as distinct values is almost certainly
#: a slab column, not a free-form amount.
_MAX_DISTINCT_TAX_SLABS = 6

#: Minimum rows needed to run any statistical test.  Below this the sample is
#: too small to trust and we return ``decision="ask"``.
MIN_ROWS_FOR_EVIDENCE = 5

#: Minimum number of distinct invoice groups required to trust the repeat-guard
#: verdict.  Two groups is the minimum meaningful comparison: one group alone
#: is trivially "constant within itself".
MIN_GROUPS_FOR_INVOICE_EVIDENCE = 2


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class EvidenceResult:
    """
    Verdict from the evidence rules engine for one ambiguous column.

    ``decision``:
        * ``"auto"``     — evidence is strong enough; ``canonical`` is set.
        * ``"ask"``      — not enough information; show the user a dialog.
        * ``"conflict"`` — multiple strong but contradictory signals; ask.

    ``canonical`` and ``semantic`` are ``None`` when ``decision != "auto"``.
    ``candidates`` lists the roles still in play for "ask" / "conflict" cases.
    ``evidence`` is a human-readable list of bullet points shown in the dialog.
    """

    decision: str                    # "auto" | "ask" | "conflict"
    canonical: str | None            # e.g. "Selling Price", "Tax", "Item"
    semantic: str | None             # internal label e.g. "unit_price", "tax"
    confidence: float                # 0–1; only meaningful when decision="auto"
    reason: str                      # one sentence for the UI banner
    evidence: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)


# ── Public entry point ────────────────────────────────────────────────────────

def evaluate(
    raw_column: str,
    series: pd.Series,
    df: pd.DataFrame,
    already_mapped: set[str] | None = None,
) -> EvidenceResult:
    """
    Run the deterministic evidence rules on ``raw_column`` in ``df``.

    ``series`` is ``df[raw_column]``.
    ``already_mapped`` is the set of raw column names whose canonical role is
    already known, so ``evaluate`` can look for helpful neighbour columns.

    Never raises.  Returns ``decision="ask"`` on any unexpected exception.
    """
    try:
        return _evaluate_safe(raw_column, series, df, already_mapped or set())
    except Exception as exc:  # defensive — must never break an upload
        import logging
        logging.getLogger("senova.ambiguity").warning(
            "Evidence engine failed on %r: %s: %s", raw_column, type(exc).__name__, exc
        )
        return EvidenceResult(
            decision="ask",
            canonical=None,
            semantic=None,
            confidence=0.0,
            reason="Could not gather enough evidence automatically — please choose.",
            evidence=[],
            candidates=[],
        )


def evaluate_batch(
    candidates: list[str],
    df: pd.DataFrame,
    already_mapped: set[str] | dict[str, str] | None = None,
) -> dict[str, EvidenceResult]:
    """
    Evaluate every column in ``candidates`` and return a results dict.

    Columns are evaluated in the order given; ``already_mapped`` accumulates
    auto-resolved columns within the batch so later evaluations can see them as
    context neighbours.
    """
    if isinstance(already_mapped, dict):
        mapped: dict[str, str] = dict(already_mapped)
    elif isinstance(already_mapped, (set, list, tuple)):
        mapped = {col: col for col in already_mapped}
    else:
        mapped = {}

    results: dict[str, EvidenceResult] = {}
    for raw_column in candidates:
        if raw_column not in df.columns:
            continue
        result = evaluate(raw_column, df[raw_column], df, mapped)
        results[raw_column] = result
        if result.decision == "auto" and result.canonical:
            mapped[raw_column] = result.canonical
    return results


# ── Internal dispatcher ───────────────────────────────────────────────────────

def _evaluate_safe(
    raw_column: str,
    series: pd.Series,
    df: pd.DataFrame,
    already_mapped: set[str] | dict[str, str],
) -> EvidenceResult:
    """Route to the appropriate rule set based on the column's header tokens."""
    norm = _norm(raw_column)
    tokens = set(re.split(r"[^a-z0-9]+", norm))

    non_null = series.dropna()
    n = len(non_null)
    if n < MIN_ROWS_FOR_EVIDENCE:
        return _ask(raw_column, reason="Too few rows to gather reliable evidence.")

    numeric_ratio = _numeric_ratio(non_null)
    is_mostly_numeric = numeric_ratio >= 0.80

    # ── Rule family 1: Percentage / rate identifiers in header ─────────────
    if _has_pct_token(norm, tokens):
        return _rule_percentage_column(raw_column, non_null, is_mostly_numeric)

    # ── Rule family 2: Amount / Total / Value ───────────────────────────────
    if _is_amount_like(norm, tokens):
        return _rule_amount_column(raw_column, non_null, series, df, already_mapped)

    # ── Rule family 3: Rate / Price / Unit Price ─────────────────────────────
    if _is_rate_like(norm, tokens):
        return _rule_rate_column(raw_column, non_null, series, df, already_mapped)

    # ── Rule family 4: Name-column disambiguation ────────────────────────────
    if _is_name_like(norm, tokens):
        return _rule_name_column(raw_column, series, df, already_mapped)

    # ── Rule family 5: Multiple Date-like columns ───────────────────────────
    if _is_auxiliary_date_like(norm, tokens):
        return _rule_auxiliary_date(raw_column)

    # No rule matched: insufficient header evidence.
    return _ask(raw_column, reason="Header doesn't match a known ambiguity pattern — please map manually.")


# ── Rule family 1: Percentage columns ────────────────────────────────────────

def _rule_percentage_column(
    raw_column: str,
    non_null: pd.Series,
    is_mostly_numeric: bool,
) -> EvidenceResult:
    """
    Resolve a header that explicitly contains a percentage marker.

    * Values in the Indian GST slab set → ``Tax`` (tax rate column).
    * Values in 0–100 range and non-slab → likely Discount % — return "ask"
      with both Tax and Discount as candidates so the user can confirm.
    * Non-numeric → "ask".
    """
    if not is_mostly_numeric:
        return _ask(raw_column, reason="Header suggests a percentage but values don't look numeric.")

    numeric_vals = _to_float_series(non_null)
    evidence: list[str] = []

    # Test GST slab membership
    slab_pct_mask = numeric_vals.isin(_GST_SLABS_PCT)
    slab_dec_mask = numeric_vals.isin(_GST_SLABS_DEC)
    slab_pct_ratio = slab_pct_mask.mean() if len(numeric_vals) > 0 else 0.0
    slab_dec_ratio = slab_dec_mask.mean() if len(numeric_vals) > 0 else 0.0

    # Prefer the representation that covers more values
    best_slab_ratio = max(slab_pct_ratio, slab_dec_ratio)
    distinct = numeric_vals.nunique()

    if best_slab_ratio >= GST_SLAB_COVERAGE and distinct <= _MAX_DISTINCT_TAX_SLABS:
        evidence.append(
            f"{best_slab_ratio * 100:.0f}% of values match Indian GST slabs "
            f"({', '.join(str(int(v) if v == int(v) else v) for v in sorted(_GST_SLABS_PCT))})."
        )
        evidence.append(f"Only {distinct} distinct value(s) — consistent with a fixed-rate slab column.")
        return EvidenceResult(
            decision="auto",
            canonical="Tax",
            semantic="tax",
            confidence=round(best_slab_ratio, 4),
            reason="Values match Indian GST slabs — treating as a tax-rate column.",
            evidence=evidence,
            candidates=["Tax"],
        )

    # Range check: most discount percentages are between 0 and 100
    in_range = ((numeric_vals >= 0) & (numeric_vals <= 100)).mean()
    if in_range >= 0.90:
        evidence.append(f"{in_range * 100:.0f}% of values are in the 0–100 range.")
        evidence.append("Header contains a percentage marker (% / pct / percent).")
        return _ask(
            raw_column,
            reason="This looks like a percentage, but could be a Discount % or a Tax rate — please confirm.",
            evidence=evidence,
            candidates=["Discount", "Tax"],
        )

    return _ask(raw_column, reason="Percentage column detected but values are out of the expected range.")


# ── Rule family 2: Amount / Total / Value ────────────────────────────────────

def _rule_amount_column(
    raw_column: str,
    non_null: pd.Series,
    series: pd.Series,
    df: pd.DataFrame,
    already_mapped: set[str] | dict[str, str],
) -> EvidenceResult:
    """
    Distinguish Line Total (a per-row amount) from an Invoice Total (repeated).

    * If Line Total is already mapped to another column in the file, ask to prevent duplicate mapping.
    * If the column value is *identical* across all rows sharing an Invoice No in multi-row
      invoices, it is an invoice-level field — must NOT be summed row-by-row.
    * If ``Qty × SP ≈ value`` in ≥ UNIT_PRICE_MATCH_THRESHOLD of rows, it is
      a line total already confirmed by the data.
    * Otherwise ask.
    """
    evidence: list[str] = []

    # ── Guard: Line Total already claimed by another column ──────────────────
    existing_lt = _is_claimed_by_another(already_mapped, "Line Total", raw_column, df)
    if existing_lt is not None:
        evidence.append(f"Line Total is already mapped to '{existing_lt}'.")
        return _ask(
            raw_column,
            reason=f"Line Total is already mapped to '{existing_lt}' — please confirm this total.",
            evidence=evidence,
            candidates=["Line Total"],
        )

    # ── Test 1: Invoice-repeat guard ─────────────────────────────────────────
    invoice_col = _find_canonical_neighbour(df, already_mapped, "Invoice No", exclude=raw_column)
    if invoice_col is not None:
        repeat_result = _check_invoice_repeat(series, df[invoice_col])
        if repeat_result["is_repeating"] and repeat_result["groups_tested"] >= MIN_GROUPS_FOR_INVOICE_EVIDENCE:
            pct = repeat_result["repeat_ratio"] * 100
            evidence.append(
                f"This column's value is constant within {pct:.0f}% of multi-row invoice groups "
                f"(tested {repeat_result['groups_tested']} invoices)."
            )
            evidence.append(
                "A repeating total cannot be summed row-by-row — it would multiply the total "
                "by the number of line items per invoice."
            )
            return EvidenceResult(
                decision="auto",
                canonical=None,   # Invoice Total has no canonical field in SENOVA's schema
                semantic="invoice_total",
                confidence=round(repeat_result["repeat_ratio"], 4),
                reason="This appears to be an invoice-level total that repeats across line items — it will not be summed.",
                evidence=evidence,
                candidates=[],
            )

    # ── Test 2: Qty × Selling Price ≈ this column → Line Total ───────────────
    qty_col = _find_canonical_neighbour(df, already_mapped, "Quantity", exclude=raw_column)
    sp_col  = _find_canonical_neighbour(df, already_mapped, "Selling Price", exclude=raw_column)
    if qty_col is not None and sp_col is not None:
        match = _check_product_match(df[qty_col], df[sp_col], series)
        if match["match_ratio"] >= UNIT_PRICE_MATCH_THRESHOLD and match["rows_tested"] >= MIN_ROWS_FOR_EVIDENCE:
            evidence.append(
                f"Qty × Selling Price ≈ this column in {match['match_ratio'] * 100:.0f}% of rows."
            )
            return EvidenceResult(
                decision="auto",
                canonical="Line Total",
                semantic="revenue",
                confidence=round(match["match_ratio"], 4),
                reason="Values match Quantity × Selling Price — confirmed as Line Total.",
                evidence=evidence,
                candidates=["Line Total"],
            )

    # ── Fallback: insufficient contextual columns ─────────────────────────────
    evidence.append("Could not find an Invoice No or Qty/Price pair to cross-check this column.")
    return _ask(
        raw_column,
        reason="This could be a Line Total or an Invoice Total — please confirm.",
        evidence=evidence,
        candidates=["Line Total"],
    )


# ── Rule family 3: Rate / Price / Unit Price ──────────────────────────────────

def _rule_rate_column(
    raw_column: str,
    non_null: pd.Series,
    series: pd.Series,
    df: pd.DataFrame,
    already_mapped: set[str] | dict[str, str],
) -> EvidenceResult:
    """
    Distinguish ``unit_price`` (per-piece selling price) from other numeric roles.

    * If Selling Price is already mapped to another column in the file, ask to prevent collision.
    * If ``value × Qty ≈ Line Total`` in ≥ UNIT_PRICE_MATCH_THRESHOLD and ≥ MIN_ROWS_FOR_EVIDENCE → unit price.
    * If column is constant within each Invoice No group → likely a fixed fee / tax rate.
    * If values lie in the GST slab set → Tax rate.
    * Otherwise: ask between Selling Price, MRP, and Cost Price.
    """
    evidence: list[str] = []
    numeric_vals = _to_float_series(non_null)

    if len(numeric_vals) < MIN_ROWS_FOR_EVIDENCE:
        return _ask(raw_column, reason="Too few numeric rows for evidence-based classification.")

    # ── Guard: Selling Price already claimed by another column ───────────────
    existing_sp = _is_claimed_by_another(already_mapped, "Selling Price", raw_column, df)
    if existing_sp is not None:
        evidence.append(f"Selling Price is already mapped to '{existing_sp}'.")
        return _ask(
            raw_column,
            reason=f"Selling Price is already mapped to '{existing_sp}' — please confirm if this is MRP, Cost Price, or an alternate price.",
            evidence=evidence,
            candidates=["MRP", "Cost Price", "Selling Price"],
        )

    # ── Test 1: Qty × this ≈ Line Total ──────────────────────────────────────
    qty_col   = _find_canonical_neighbour(df, already_mapped, "Quantity", exclude=raw_column)
    total_col = _find_canonical_neighbour(df, already_mapped, "Line Total", exclude=raw_column)
    if qty_col is not None and total_col is not None:
        match = _check_product_match(df[qty_col], series, df[total_col])
        if match["match_ratio"] >= UNIT_PRICE_MATCH_THRESHOLD and match["rows_tested"] >= MIN_ROWS_FOR_EVIDENCE:
            evidence.append(
                f"This value × Quantity ≈ Line Total in {match['match_ratio'] * 100:.0f}% of rows."
            )
            return EvidenceResult(
                decision="auto",
                canonical="Selling Price",
                semantic="unit_price",
                confidence=round(match["match_ratio"], 4),
                reason="Values times Quantity match the Line Total — confirmed as Selling Price (unit price).",
                evidence=evidence,
                candidates=["Selling Price"],
            )

    # ── Test 2: Constant within invoice group → not a line-level unit price ──
    invoice_col = _find_canonical_neighbour(df, already_mapped, "Invoice No", exclude=raw_column)
    if invoice_col is not None:
        repeat_result = _check_invoice_repeat(series, df[invoice_col])
        if repeat_result["is_repeating"] and repeat_result["groups_tested"] >= MIN_GROUPS_FOR_INVOICE_EVIDENCE:
            evidence.append(
                f"Value is constant within {repeat_result['repeat_ratio'] * 100:.0f}% of multi-row invoice groups — "
                "likely a fixed rate or fee per order, not a per-unit selling price."
            )
            return _ask(
                raw_column,
                reason="This value is the same for all line items in an invoice — might be MRP, Tax rate, or a fixed fee.",
                evidence=evidence,
                candidates=["MRP", "Tax", "Discount"],
            )

    # ── Test 3: GST slab membership ──────────────────────────────────────────
    slab_pct_ratio = numeric_vals.isin(_GST_SLABS_PCT).mean()
    slab_dec_ratio = numeric_vals.isin(_GST_SLABS_DEC).mean()
    best_slab = max(slab_pct_ratio, slab_dec_ratio)
    if best_slab >= GST_SLAB_COVERAGE and numeric_vals.nunique() <= _MAX_DISTINCT_TAX_SLABS:
        evidence.append(f"{best_slab * 100:.0f}% of values are standard Indian GST slabs.")
        return EvidenceResult(
            decision="auto",
            canonical="Tax",
            semantic="tax",
            confidence=round(best_slab, 4),
            reason="Values match Indian GST slabs — treating as a tax-rate column.",
            evidence=evidence,
            candidates=["Tax"],
        )

    # ── Fallback ──────────────────────────────────────────────────────────────
    evidence.append("Header suggests a price or rate, but no cross-check column was available.")
    return _ask(
        raw_column,
        reason="This could be a Selling Price, MRP, or Cost Price — please confirm.",
        evidence=evidence,
        candidates=["Selling Price", "MRP", "Cost Price"],
    )


# ── Rule family 4: Name-column disambiguation ─────────────────────────────────

def _rule_name_column(
    raw_column: str,
    series: pd.Series,
    df: pd.DataFrame,
    already_mapped: set[str],
) -> EvidenceResult:
    """
    Decide if a ``Name`` column is a Customer name or an Item name.

    Uses *neighbour column headers* as the deciding evidence — not the values,
    which may contain personal data.
    """
    evidence: list[str] = []
    neighbour_tokens = _all_neighbour_tokens(df, raw_column)

    customer_score = len(neighbour_tokens & _CUSTOMER_CONTEXT_TOKENS)
    item_score     = len(neighbour_tokens & _ITEM_CONTEXT_TOKENS)

    customer_hits = neighbour_tokens & _CUSTOMER_CONTEXT_TOKENS
    item_hits     = neighbour_tokens & _ITEM_CONTEXT_TOKENS

    if customer_hits:
        evidence.append(
            f"Neighbours include customer-context columns: {', '.join(sorted(customer_hits))}."
        )
    if item_hits:
        evidence.append(
            f"Neighbours include item-context columns: {', '.join(sorted(item_hits))}."
        )

    if customer_score > 0 and item_score == 0:
        return EvidenceResult(
            decision="auto",
            canonical="Customer",
            semantic="customer",
            confidence=min(0.90 + 0.02 * customer_score, 0.99),
            reason=f"Neighbour columns ({', '.join(sorted(customer_hits))}) indicate this is a customer name.",
            evidence=evidence,
            candidates=["Customer"],
        )

    if item_score > 0 and customer_score == 0:
        return EvidenceResult(
            decision="auto",
            canonical="Item",
            semantic="product",
            confidence=min(0.90 + 0.02 * item_score, 0.99),
            reason=f"Neighbour columns ({', '.join(sorted(item_hits))}) indicate this is a product name.",
            evidence=evidence,
            candidates=["Item"],
        )

    if customer_score > 0 and item_score > 0:
        evidence.append("Both customer-context and item-context neighbours found — ambiguous.")
        return _ask(
            raw_column,
            reason="Both customer-context and item-context columns are present — please confirm which Name this is.",
            evidence=evidence,
            candidates=["Customer", "Item"],
        )

    # No neighbours with disambiguating context.
    return _ask(
        raw_column,
        reason="This is a Name column, but neighbouring columns don't clarify whether it's a customer or product name.",
        evidence=["No phone, email, SKU, or HSN neighbours found to disambiguate."],
        candidates=["Customer", "Item"],
    )


# ── Rule family 5: Auxiliary date columns ────────────────────────────────────

def _rule_auxiliary_date(raw_column: str) -> EvidenceResult:
    """
    An extra date-like column that is NOT the primary sales transaction date.

    The primary Date is already mapped before this engine runs.  A second
    date-like column (Due Date, Delivery Date, Expiry Date, Supplier ETA…)
    should be stored as a metadata column, not remapped to Date.
    """
    return EvidenceResult(
        decision="auto",
        canonical=None,             # stored-only; no canonical field
        semantic="date_like",
        confidence=0.95,
        reason=(
            "A primary Date column is already mapped.  This appears to be an auxiliary date "
            "(e.g. Due Date, Delivery Date) and will be stored as metadata."
        ),
        evidence=[
            "Primary Date column is already confirmed.",
            "This column looks date-like — treating as auxiliary / stored-only.",
        ],
        candidates=[],
    )


# ── Statistical helpers ───────────────────────────────────────────────────────

def _check_product_match(
    qty: pd.Series,
    price: pd.Series,
    total: pd.Series,
    tol_fraction: float = UNIT_PRICE_ABS_TOL_FRACTION,
) -> dict:
    """
    Check whether ``qty × price ≈ total`` row-by-row.

    Returns:
        {"match_ratio": float, "rows_tested": int}
    """
    df_check = pd.DataFrame({"qty": qty, "price": price, "total": total}).dropna()
    if df_check.empty:
        return {"match_ratio": 0.0, "rows_tested": 0}

    # Coerce to numeric, drop non-numeric rows
    for col in ("qty", "price", "total"):
        df_check[col] = pd.to_numeric(
            df_check[col].astype(str).str.replace(r"[₹$€£,\s]", "", regex=True),
            errors="coerce",
        )
    df_check = df_check.dropna()
    # Filter to eligible positive transactions: zero or negative quantities/prices
    # provide no valid statistical evidence of unit-price multiplication.
    df_check = df_check[(df_check["qty"] > 0) & (df_check["price"] > 0)]
    if df_check.empty:
        return {"match_ratio": 0.0, "rows_tested": 0}

    computed = df_check["qty"] * df_check["price"]
    actual   = df_check["total"]

    # Avoid division by zero: use absolute tolerance based on actual value
    tol = (actual.abs() * tol_fraction).clip(lower=0.01)
    matches = (computed - actual).abs() <= tol

    return {
        "match_ratio": round(float(matches.mean()), 4),
        "rows_tested": int(len(df_check)),
    }


def _check_invoice_repeat(
    series: pd.Series,
    invoice_series: pd.Series,
) -> dict:
    """
    Check whether ``series`` is constant within each multi-row Invoice No group.

    A column that never varies within an invoice (e.g. a bill-level total) will
    score high here.  Only invoice groups with ≥ 2 line items provide evidence
    of repeating values across lines.
    """
    val_series = series.copy()
    num_series = pd.to_numeric(
        val_series.astype(str).str.replace(r"[₹$€£,\s]", "", regex=True),
        errors="coerce",
    )
    if num_series.notna().mean() >= 0.80:
        val_series = num_series

    inv_cleaned = invoice_series.astype(str).str.strip()
    is_missing_inv = (
        invoice_series.isna()
        | inv_cleaned.eq("")
        | inv_cleaned.str.lower().isin({"nan", "none", "null", "n/a", "na", "<na>"})
    )
    df_check = pd.DataFrame({"val": val_series, "inv": inv_cleaned})
    df_check = df_check[~is_missing_inv].dropna(subset=["val", "inv"])
    if df_check.empty:
        return {"is_repeating": False, "repeat_ratio": 0.0, "groups_tested": 0}

    # Only multi-row invoices can provide evidence of within-invoice repetition
    grouped = df_check.groupby("inv")["val"]
    multi_row_groups = [g for _, g in grouped if len(g) >= 2]

    if len(multi_row_groups) < MIN_GROUPS_FOR_INVOICE_EVIDENCE:
        return {"is_repeating": False, "repeat_ratio": 0.0, "groups_tested": len(multi_row_groups)}

    all_same = [g.nunique() == 1 for g in multi_row_groups]
    repeat_ratio = float(np.mean(all_same))
    groups_tested = len(multi_row_groups)

    return {
        "is_repeating": repeat_ratio >= INVOICE_REPEAT_THRESHOLD,
        "repeat_ratio": round(repeat_ratio, 4),
        "groups_tested": groups_tested,
    }


# ── Header classification helpers ─────────────────────────────────────────────

def _norm(text: str) -> str:
    """Lowercase, collapse whitespace and BOM, strip leading/trailing spaces."""
    return re.sub(r"\s+", " ", str(text).replace("\ufeff", "").strip().lower())


def _has_pct_token(norm: str, tokens: set[str]) -> bool:
    """True when the header explicitly signals a percentage / rate value."""
    if "%" in norm:
        return True
    pct_words = {"pct", "percent", "percentage", "gst", "vat", "discount%", "disc%"}
    return bool(tokens & pct_words)


def _is_amount_like(norm: str, tokens: set[str]) -> bool:
    """True when the header suggests a monetary total (line or invoice level)."""
    amount_words = {
        "amount", "amt", "total", "value", "net", "gross",
        "invoice amount", "bill amount", "taxable value", "line total",
    }
    return bool(tokens & amount_words) or any(w in norm for w in amount_words)


def _is_rate_like(norm: str, tokens: set[str]) -> bool:
    """True when the header suggests a per-unit monetary rate."""
    rate_words = {
        "rate", "price", "unit price", "selling price", "sp",
        "cost", "cp", "mrp", "purchase rate", "buying price",
    }
    return bool(tokens & rate_words) or any(w in norm for w in rate_words)


def _is_name_like(norm: str, tokens: set[str]) -> bool:
    """True when the header is 'name' or ends with 'name' without a product qualifier."""
    product_qualifiers = {"product", "item", "brand", "style", "model", "sku", "article"}
    if tokens & product_qualifiers:
        return False
    return "name" in tokens


def _is_auxiliary_date_like(norm: str, tokens: set[str]) -> bool:
    """
    True for date headers that suggest an auxiliary (non-primary) date:
    due date, delivery date, expiry date, supplier ETA, etc.
    """
    auxiliary_keywords = {
        "due", "delivery", "delivered", "ship", "shipped", "dispatch",
        "eta", "expiry", "expiration", "expected", "promised", "return",
        "refund", "manufacture", "mfg", "best before", "supplier",
    }
    return bool(tokens & auxiliary_keywords)


# ── Neighbour-column helpers ──────────────────────────────────────────────────

def _all_neighbour_tokens(df: pd.DataFrame, raw_column: str) -> frozenset[str]:
    """
    Collect all whitespace-split lowercase tokens from every column header in
    ``df`` *except* ``raw_column`` itself.
    """
    tokens: set[str] = set()
    for col in df.columns:
        if col == raw_column:
            continue
        for tok in re.split(r"[^a-z0-9]+", _norm(col)):
            if tok:
                tokens.add(tok)
    return frozenset(tokens)


def _is_claimed_by_another(
    already_mapped: set[str] | dict[str, str] | None,
    canonical_target: str,
    raw_column: str,
    df: pd.DataFrame,
) -> str | None:
    """
    Check if ``canonical_target`` is already claimed by a column other than ``raw_column``.
    Returns the name of the claiming column, or None.
    """
    if not already_mapped:
        return None

    target_norm = _norm(canonical_target)

    if isinstance(already_mapped, dict):
        for raw_col, can_field in already_mapped.items():
            if raw_col != raw_column and can_field and _norm(can_field) == target_norm:
                return raw_col
        return None

    if isinstance(already_mapped, (set, list, tuple)):
        for item in already_mapped:
            if item != raw_column and item in df.columns:
                if _norm(item) == target_norm:
                    return item
                try:
                    from app.utils.data_validator import guess_canonical_column
                    guess, _ = guess_canonical_column(item)
                    if guess and _norm(guess) == target_norm:
                        return item
                except Exception:
                    pass

        if any(_norm(item) == target_norm for item in already_mapped):
            for col in df.columns:
                if col != raw_column:
                    if _norm(col) == target_norm:
                        return col
                    try:
                        from app.utils.data_validator import guess_canonical_column
                        guess, _ = guess_canonical_column(col)
                        if guess and _norm(guess) == target_norm:
                            return col
                    except Exception:
                        pass
            return canonical_target

    return None


def _find_canonical_neighbour(
    df: pd.DataFrame,
    already_mapped: set[str] | dict[str, str] | None,
    canonical_target: str,
    exclude: str | None = None,
) -> str | None:
    """
    Find the raw column name that is mapped to or aliases to ``canonical_target``.

    Lookup precedence:
    1. Mapping dictionary: ``{raw_col: canonical_field}`` (Tier 1 resolved mappings).
    2. Explicit set/list/tuple: raw column names or canonical target name directly.
    3. Direct exact match in ``df.columns`` (post-normalisation).
    4. Canonical alias fallback via ``guess_canonical_column``.
    """
    target_norm = _norm(canonical_target)
    committed_to_other: set[str] = set()

    # 1. Mapping dictionary: {raw_col: canonical_field}
    if isinstance(already_mapped, dict):
        for raw_col, can_field in already_mapped.items():
            if raw_col == exclude:
                continue
            if can_field and _norm(can_field) == target_norm and raw_col in df.columns:
                return raw_col
            elif can_field and _norm(can_field) != target_norm and raw_col in df.columns:
                committed_to_other.add(raw_col)

        # Inverted dict check: {canonical_field: raw_col}
        for can_field, raw_col in already_mapped.items():
            if raw_col == exclude:
                continue
            if _norm(can_field) == target_norm and raw_col in df.columns:
                return raw_col

    # 2. Explicit set/list/tuple: raw column names or canonical target names
    elif isinstance(already_mapped, (set, list, tuple)):
        # 2a. Check if any item in already_mapped is a raw column in df matching target
        for item in already_mapped:
            if item == exclude:
                continue
            if item in df.columns:
                if _norm(item) == target_norm:
                    return item
                try:
                    from app.utils.data_validator import guess_canonical_column
                    guess, _ = guess_canonical_column(item)
                    if guess and _norm(guess) == target_norm:
                        return item
                except Exception:
                    pass

        # 2b. Check if canonical_target itself is in already_mapped
        target_in_set = any(_norm(item) == target_norm for item in already_mapped)
        if target_in_set:
            for col in df.columns:
                if col == exclude:
                    continue
                if _norm(col) == target_norm:
                    return col
            try:
                from app.utils.data_validator import guess_canonical_column
                alias_candidates = []
                for col in df.columns:
                    if col == exclude:
                        continue
                    guess, _ = guess_canonical_column(col)
                    if guess and _norm(guess) == target_norm:
                        alias_candidates.append(col)
                if len(alias_candidates) == 1:
                    return alias_candidates[0]
            except Exception:
                pass

    # 3. Direct match on normalized column name (excluding columns committed to other roles or excluded)
    exact_matches = [
        col for col in df.columns
        if col != exclude and col not in committed_to_other and _norm(col) == target_norm
    ]
    if len(exact_matches) >= 1:
        return exact_matches[0]

    # 4. Canonical alias fallback via guess_canonical_column
    try:
        from app.utils.data_validator import guess_canonical_column
        alias_matches = []
        for col in df.columns:
            if col == exclude or col in committed_to_other:
                continue
            guess, _ = guess_canonical_column(col)
            if guess and _norm(guess) == target_norm:
                alias_matches.append(col)

        if len(alias_matches) == 1:
            return alias_matches[0]
        # If len(alias_matches) > 1, multiple unmapped candidates exist — ambiguous!
        # Do not return an arbitrary candidate to prevent false matches.
    except Exception as exc:
        import logging
        logging.getLogger("senova.ambiguity").warning(
            "Canonical neighbour alias lookup failed for %r: %s", canonical_target, exc
        )

    return None


# ── Misc helpers ──────────────────────────────────────────────────────────────

def _to_float_series(series: pd.Series) -> pd.Series:
    """
    Convert a Series to float, stripping currency noise.  Non-parseable values
    become NaN and are then dropped.
    """
    cleaned = (
        series.astype(str)
        .str.replace(r"[₹$€£,\s]", "", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce").dropna()


def _numeric_ratio(non_null: pd.Series) -> float:
    """Share of non-null values that parse as a number (with currency noise stripped)."""
    if len(non_null) == 0:
        return 0.0
    numeric = _to_float_series(non_null)
    return round(len(numeric) / len(non_null), 4)


def _ask(
    raw_column: str,
    reason: str = "Please choose the correct meaning for this column.",
    evidence: list[str] | None = None,
    candidates: list[str] | None = None,
) -> EvidenceResult:
    """Convenience constructor for an "ask the user" result."""
    return EvidenceResult(
        decision="ask",
        canonical=None,
        semantic=None,
        confidence=0.0,
        reason=reason,
        evidence=evidence or [],
        candidates=candidates or [],
    )



# ── Module 2.4: confirmation-time guard for a user-forced Line Total ─────────

@dataclass
class ForcedLineTotalAssessment:
    """
    Verdict for a column a user has explicitly mapped to ``Line Total``.

    ``verdict``:
        * ``"ok"``      — no invoice-level repetition detected; safe to proceed.
        * ``"reject"``  — strong multi-invoice repeat evidence; summation would
                          inflate revenue. The endpoint must refuse (HTTP 400).
        * ``"warn"``    — a weaker single-invoice signal: the value is constant
                          across several rows of the *one* invoice present, so it
                          *might* be a bill-level total. Non-blocking; the user may
                          proceed intentionally.
    """
    verdict: str                     # "ok" | "reject" | "warn"
    message: str = ""
    repeat_ratio: float = 0.0
    groups_tested: int = 0
    invoice_column: str | None = None


def assess_forced_line_total(
    raw_column: str,
    df: pd.DataFrame,
    mapping: dict[str, str] | None = None,
) -> ForcedLineTotalAssessment:
    """
    Decide whether a column the user has mapped to ``Line Total`` is really an
    invoice-level total that repeats across the line items of a bill.

    Reuses the exact Module 2.1 detector (``_find_canonical_neighbour`` +
    ``_check_invoice_repeat``) and the same ``INVOICE_REPEAT_THRESHOLD`` /
    ``MIN_GROUPS_FOR_INVOICE_EVIDENCE`` constants — no second heuristic.

    * Strong evidence (``is_repeating`` with ≥ MIN_GROUPS_FOR_INVOICE_EVIDENCE
      multi-row invoices) → ``reject``.
    * A single invoice whose value is constant across ≥ 2 of its own line rows
      → ``warn`` (ambiguous; user decides).
    * Everything else (no invoice column, missing ids, varying amounts,
      genuine per-line totals) → ``ok``.

    Never raises: any unexpected error degrades to ``ok`` so a confirmation is
    never blocked by a defect in this advisory check.
    """
    try:
        if raw_column not in df.columns:
            return ForcedLineTotalAssessment(verdict="ok")

        invoice_col = _find_canonical_neighbour(df, mapping, "Invoice No", exclude=raw_column)
        if invoice_col is None or invoice_col not in df.columns:
            return ForcedLineTotalAssessment(verdict="ok")

        series = df[raw_column]
        # Strong, multi-invoice evidence → reject (same bar as the auto verdict).
        repeat = _check_invoice_repeat(series, df[invoice_col])
        if repeat["is_repeating"] and repeat["groups_tested"] >= MIN_GROUPS_FOR_INVOICE_EVIDENCE:
            pct = repeat["repeat_ratio"] * 100
            return ForcedLineTotalAssessment(
                verdict="reject",
                message=(
                    f"'{raw_column}' looks like an invoice-level total: it is constant within "
                    f"{pct:.0f}% of multi-line invoices (checked {repeat['groups_tested']}). "
                    "Mapping it to Line Total would multiply revenue by the number of line items "
                    "per invoice. Map a genuine per-line amount to Line Total, or map "
                    "Quantity and Selling Price instead."
                ),
                repeat_ratio=repeat["repeat_ratio"],
                groups_tested=repeat["groups_tested"],
                invoice_column=invoice_col,
            )

        # Weaker single-invoice signal → non-blocking warning.
        single = _single_invoice_constant_signal(series, df[invoice_col])
        if single["is_constant_single_invoice"]:
            return ForcedLineTotalAssessment(
                verdict="warn",
                message=(
                    f"'{raw_column}' is the same value on every line of the only invoice in this "
                    "file. If it is a bill-level total rather than a per-line amount, revenue will "
                    "be counted once per line. Please confirm it really is a per-line amount before "
                    "proceeding."
                ),
                repeat_ratio=1.0,
                groups_tested=1,
                invoice_column=invoice_col,
            )

        return ForcedLineTotalAssessment(verdict="ok", invoice_column=invoice_col)
    except Exception as exc:  # advisory only — never block a confirmation
        import logging
        logging.getLogger("senova.ambiguity").warning(
            "assess_forced_line_total failed on %r: %s: %s", raw_column, type(exc).__name__, exc
        )
        return ForcedLineTotalAssessment(verdict="ok")


def _single_invoice_constant_signal(series: pd.Series, invoice_series: pd.Series) -> dict:
    """
    Detect the single-invoice ambiguous case: exactly ONE valid invoice group,
    with ≥ 2 line rows, whose amount value is identical on every row.

    This deliberately does NOT meet ``MIN_GROUPS_FOR_INVOICE_EVIDENCE`` (so it
    never triggers an automatic rejection); it only powers the non-blocking
    warning. Missing/blank invoice ids yield no signal.
    """
    val_series = series.copy()
    num_series = pd.to_numeric(
        val_series.astype(str).str.replace(r"[₹$€£,\s]", "", regex=True),
        errors="coerce",
    )
    if num_series.notna().mean() >= 0.80:
        val_series = num_series

    inv_cleaned = invoice_series.astype(str).str.strip()
    is_missing_inv = (
        invoice_series.isna()
        | inv_cleaned.eq("")
        | inv_cleaned.str.lower().isin({"nan", "none", "null", "n/a", "na", "<na>"})
    )
    df_check = pd.DataFrame({"val": val_series, "inv": inv_cleaned})
    df_check = df_check[~is_missing_inv].dropna(subset=["val", "inv"])
    if df_check.empty:
        return {"is_constant_single_invoice": False}

    grouped = df_check.groupby("inv")["val"]
    multi_row_groups = [g for _, g in grouped if len(g) >= 2]

    # Exactly one multi-row invoice, constant across its lines.
    if len(multi_row_groups) == 1 and multi_row_groups[0].nunique() == 1:
        return {"is_constant_single_invoice": True}
    return {"is_constant_single_invoice": False}
