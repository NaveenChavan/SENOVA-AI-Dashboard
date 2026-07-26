"""
Data validation and normalisation layer.

What this module does
---------------------
Turns *any* shop's export — Tally, Vyapar, Marg, Busy, a hand-typed Excel
sheet, a Shopify/Amazon/Flipkart order dump — into one predictable
DataFrame, while reporting every bad cell instead of crashing on it.

Two groups of columns are understood:

**Required (6)** — ``Date``, ``Category``, ``Item``, ``Quantity``,
``Selling Price``, ``Cost Price``. A row missing any of these is not
analysable, so it is reported as an error and dropped.

**Optional** — extra measures (``Line Total``, ``Discount``, ``Tax``,
``Stock On Hand``) and extra dimensions (``Branch``, ``Payment Mode``,
``Customer``, ``Salesperson``, ``Brand``, ``Size``, ``Colour``,
``Invoice No``). These are never required; when a shop's file happens to
contain them they unlock extra analysis — slicing every chart by branch or
payment mode, net-of-discount revenue, and real days-of-cover / reorder
alerts from stock on hand.

Why ``Line Total`` matters (a real correctness fix)
--------------------------------------------------
Many exports have an ``Amount`` / ``Net Amount`` / ``Taxable Value`` column
holding the *line total* (``Quantity × Rate``), not a unit price. Mapping
that to ``Selling Price`` makes revenue come out as ``Quantity × line
total`` — inflated by the quantity factor on every single row. ``Amount``
and its variants therefore map to ``Line Total``, and when no unit
``Selling Price`` column exists the unit price is *derived* as
``Line Total / Quantity``.

Safe coercion pipeline (never crashes on bad values)
----------------------------------------------------
1. Rename columns via the user-confirmed mapping, or the alias map.
2. Derive ``Selling Price`` from ``Line Total`` when only the total exists.
3. Assert the 6 required columns exist (hard error, or soft-fail report).
4. ``pd.to_numeric(errors="coerce")`` on every numeric column.
5. Retry values that are still NaN with currency symbols/commas stripped.
6. Replace ``inf`` / ``-inf`` with ``NaN`` so ``.astype(int)`` is safe.
7. ``pd.to_datetime`` twice: ``dayfirst=True`` for DD-MM-YYYY, then ISO.
8. Blank ``Category`` / ``Item`` → ``NaN`` so ``dropna`` catches them.
9. Collect row-level errors from the coerced frame.
10. ``dropna`` on the 6 required columns → only fully valid rows remain.
11. Cast types, then apply business rules (quantity > 0, no negative prices).
"""

import pandas as pd
import numpy as np

# ── Canonical column names ──────────────────────────────────────────────────

#: The 6 fields every uploaded file must provide for analysis to be possible.
REQUIRED_COLUMNS: set[str] = {
    "Date",
    "Category",
    "Item",
    "Quantity",
    "Selling Price",
    "Cost Price",
}

#: Kept under the original name so older imports/tests keep working.
EXPECTED_COLUMNS = REQUIRED_COLUMNS

#: Optional numeric fields. Each unlocks extra analysis when present:
#: Line Total → unit-price derivation, Discount → net revenue,
#: Tax → GST line in the P&L, Stock On Hand → days-of-cover + reorder alerts.
OPTIONAL_MEASURE_COLUMNS: set[str] = {"Line Total", "Discount", "Tax", "Stock On Hand"}

#: Optional text fields. Every one becomes a slice-able dimension in the
#: chart engine and the filter panel (e.g. revenue by Branch, by Payment Mode).
OPTIONAL_DIMENSION_COLUMNS: set[str] = {
    "Branch",
    "Payment Mode",
    "Customer",
    "Salesperson",
    "Brand",
    "Size",
    "Colour",
    "Invoice No",
}

#: Everything the column-mapping screen may offer as a target field.
MAPPABLE_FIELDS: list[str] = (
    sorted(REQUIRED_COLUMNS) + sorted(OPTIONAL_MEASURE_COLUMNS) + sorted(OPTIONAL_DIMENSION_COLUMNS)
)

STRICT_SCHEMA: dict[str, str] = {
    "Date": "Date",
    "Category": "Text",
    "Item": "Text",
    "Quantity": "Integer",
    "Selling Price": "Number",
    "Cost Price": "Number",
    "Line Total": "Number",
    "Discount": "Number",
    "Tax": "Number",
    "Stock On Hand": "Number",
}

#: Value written into an optional dimension when a row leaves it blank.
#: A visible label is better than dropping the row or showing an empty axis.
UNSPECIFIED = "Unspecified"

# ── Alias → canonical name mapping (exact, case-insensitive) ────────────────
# Sourced from the header names real Indian retail/garment exports use:
# Tally ("Voucher Date", "Particulars"), Vyapar/Marg/Busy ("Bill Date",
# "Item Name", "Taxable Value"), GST invoice registers ("Invoice Date",
# "HSN"), and marketplace dumps (Shopify "Lineitem quantity", Amazon
# "quantity-purchased", Flipkart "Ordered On").
COLUMN_ALIAS_MAP: dict[str, str] = {
    # ── Date ──
    "date": "Date",
    "dates": "Date",
    "date_sold": "Date",
    "sold date": "Date",
    "sale date": "Date",
    "sale_date": "Date",
    "sales date": "Date",
    "transaction date": "Date",
    "transaction_date": "Date",
    "txn date": "Date",
    "txn_date": "Date",
    "invoice date": "Date",
    "invoice_date": "Date",
    "bill date": "Date",
    "bill_date": "Date",
    "billing date": "Date",
    "voucher date": "Date",
    "voucher_date": "Date",
    "entry date": "Date",
    "order date": "Date",
    "order_date": "Date",
    "ordered on": "Date",
    "purchase-date": "Date",
    "posting date": "Date",
    "day": "Date",
    "dt": "Date",
    "datetime": "Date",
    "timestamp": "Date",
    # ── Category ──
    "category": "Category",
    "categories": "Category",
    "cat": "Category",
    "product category": "Category",
    "product_category": "Category",
    "item category": "Category",
    "item_category": "Category",
    "item group": "Category",
    "stock group": "Category",
    "stock_group": "Category",
    "product type": "Category",
    "product_type": "Category",
    "dept": "Category",
    "department": "Category",
    "type": "Category",
    "group": "Category",
    "segment": "Category",
    "class": "Category",
    "sub category": "Category",
    "sub-category": "Category",
    "subcategory": "Category",
    "collection": "Category",
    # ── Item ──
    "item": "Item",
    "items": "Item",
    "item name": "Item",
    "item_name": "Item",
    "itemname": "Item",
    "product": "Item",
    "product name": "Item",
    "product_name": "Item",
    "products": "Item",
    "description": "Item",
    "item description": "Item",
    "item_description": "Item",
    "product_description": "Item",
    "particulars": "Item",
    "stock item": "Item",
    "stock_item": "Item",
    "style": "Item",
    "style name": "Item",
    "style code": "Item",
    "design": "Item",
    "design no": "Item",
    "prod": "Item",
    "name": "Item",
    "goods": "Item",
    "sku": "Item",
    "sku code": "Item",
    "item code": "Item",
    "item_code": "Item",
    "product code": "Item",
    "barcode": "Item",
    "article": "Item",
    "lineitem name": "Item",
    "title": "Item",
    # ── Quantity ──
    "quantity": "Quantity",
    "quantities": "Quantity",
    "qty": "Quantity",
    "qty.": "Quantity",
    "qnty": "Quantity",
    "nos": "Quantity",
    "no of units": "Quantity",
    "units": "Quantity",
    "unit": "Quantity",
    "pcs": "Quantity",
    "pieces": "Quantity",
    "units sold": "Quantity",
    "units_sold": "Quantity",
    "quantity sold": "Quantity",
    "quantity_sold": "Quantity",
    "qty sold": "Quantity",
    "qty_sold": "Quantity",
    "billed qty": "Quantity",
    "billed_qty": "Quantity",
    "sold qty": "Quantity",
    "actual qty": "Quantity",
    "no.": "Quantity",
    "count": "Quantity",
    "sold": "Quantity",
    "num": "Quantity",
    "lineitem quantity": "Quantity",
    "quantity-purchased": "Quantity",
    "order quantity": "Quantity",
    # ── Selling Price (per unit) ──
    "selling price": "Selling Price",
    "selling_price": "Selling Price",
    "sale price": "Selling Price",
    "sales price": "Selling Price",
    "sell price": "Selling Price",
    "price": "Selling Price",
    "unit price": "Selling Price",
    "unit_price": "Selling Price",
    "price per unit": "Selling Price",
    "price/unit": "Selling Price",
    "rate": "Selling Price",
    "rate/unit": "Selling Price",
    "rate per unit": "Selling Price",
    "unit rate": "Selling Price",
    "retail price": "Selling Price",
    "retail_price": "Selling Price",
    "mrp": "Selling Price",
    "sp": "Selling Price",
    "lineitem price": "Selling Price",
    "item-price": "Selling Price",
    # ── Cost Price (per unit) ──
    "cost price": "Cost Price",
    "cost_price": "Cost Price",
    "cost": "Cost Price",
    "unit cost": "Cost Price",
    "unit_cost": "Cost Price",
    "cost per unit": "Cost Price",
    "purchase price": "Cost Price",
    "purchase_price": "Cost Price",
    "purchase rate": "Cost Price",
    "buying price": "Cost Price",
    "buying_price": "Cost Price",
    "wholesale price": "Cost Price",
    "wholesale_price": "Cost Price",
    "landing cost": "Cost Price",
    "landed cost": "Cost Price",
    "cp": "Cost Price",
    "cogs": "Cost Price",
    # ── Line Total (Quantity × Selling Price, NOT a unit price) ──
    "amount": "Line Total",
    "amt": "Line Total",
    "net amount": "Line Total",
    "net_amount": "Line Total",
    "gross amount": "Line Total",
    "total": "Line Total",
    "total amount": "Line Total",
    "total_amount": "Line Total",
    "line total": "Line Total",
    "line_total": "Line Total",
    "line amount": "Line Total",
    "row total": "Line Total",
    "sale amount": "Line Total",
    "sales amount": "Line Total",
    "sales value": "Line Total",
    "invoice amount": "Line Total",
    "bill amount": "Line Total",
    "taxable value": "Line Total",
    "taxable amount": "Line Total",
    "revenue": "Line Total",
    "turnover": "Line Total",
    "item-total": "Line Total",
    "lineitem total": "Line Total",
    "value": "Line Total",
    # ── Discount ──
    "discount": "Discount",
    "discount amount": "Discount",
    "discount_amount": "Discount",
    "disc": "Discount",
    "disc amt": "Discount",
    "rebate": "Discount",
    "less discount": "Discount",
    "lineitem discount": "Discount",
    # ── Tax / GST ──
    "tax": "Tax",
    "tax amount": "Tax",
    "tax_amount": "Tax",
    "gst": "Tax",
    "gst amount": "Tax",
    "gst_amount": "Tax",
    "total gst": "Tax",
    "cgst+sgst": "Tax",
    "vat": "Tax",
    "igst": "Tax",
    # ── Stock On Hand ──
    "stock": "Stock On Hand",
    "stock on hand": "Stock On Hand",
    "stock_on_hand": "Stock On Hand",
    "on hand": "Stock On Hand",
    "in stock": "Stock On Hand",
    "closing stock": "Stock On Hand",
    "closing_stock": "Stock On Hand",
    "closing balance": "Stock On Hand",
    "balance qty": "Stock On Hand",
    "balance_qty": "Stock On Hand",
    "available qty": "Stock On Hand",
    "current stock": "Stock On Hand",
    "inventory": "Stock On Hand",
    "inventory qty": "Stock On Hand",
    # ── Optional dimensions ──
    "branch": "Branch",
    "store": "Branch",
    "store name": "Branch",
    "shop": "Branch",
    "outlet": "Branch",
    "location": "Branch",
    "godown": "Branch",
    "warehouse": "Branch",
    "city": "Branch",
    "payment mode": "Payment Mode",
    "payment_mode": "Payment Mode",
    "payment method": "Payment Mode",
    "mode of payment": "Payment Mode",
    "paid via": "Payment Mode",
    "payment type": "Payment Mode",
    "tender": "Payment Mode",
    "customer": "Customer",
    "customer name": "Customer",
    "customer_name": "Customer",
    "buyer": "Customer",
    "party": "Customer",
    "party name": "Customer",
    "client": "Customer",
    "salesperson": "Salesperson",
    "sales person": "Salesperson",
    "sales_person": "Salesperson",
    "salesman": "Salesperson",
    "staff": "Salesperson",
    "employee": "Salesperson",
    "cashier": "Salesperson",
    "biller": "Salesperson",
    "brand": "Brand",
    "brand name": "Brand",
    "make": "Brand",
    "manufacturer": "Brand",
    "size": "Size",
    "sizes": "Size",
    "item size": "Size",
    "variant": "Size",
    "colour": "Colour",
    "color": "Colour",
    "shade": "Colour",
    "invoice no": "Invoice No",
    "invoice_no": "Invoice No",
    "invoice number": "Invoice No",
    "invoice": "Invoice No",
    "bill no": "Invoice No",
    "bill_no": "Invoice No",
    "bill number": "Invoice No",
    "voucher no": "Invoice No",
    "receipt no": "Invoice No",
    "order id": "Invoice No",
    "order_id": "Invoice No",
    "order no": "Invoice No",
    "txn id": "Invoice No",
}

# ── Fuzzy keyword mapping (last-resort substring heuristic) ─────────────────
# Order matters: the first key found *inside* the column name wins, so the
# more specific keywords are listed before the generic ones ("net amount"
# must resolve to Line Total before "amount" is even considered, and
# "purchase rate" must not be caught by "rate" → Selling Price).
_FUZZY_KEYWORDS: dict[str, str] = {
    "invoice date": "Date",
    "bill date": "Date",
    "voucher date": "Date",
    "order date": "Date",
    "date": "Date",
    "stock": "Stock On Hand",
    "on hand": "Stock On Hand",
    "closing": "Stock On Hand",
    "balance": "Stock On Hand",
    "payment": "Payment Mode",
    "salesman": "Salesperson",
    "salesperson": "Salesperson",
    "cashier": "Salesperson",
    "customer": "Customer",
    "party": "Customer",
    "branch": "Branch",
    "outlet": "Branch",
    "store": "Branch",
    "godown": "Branch",
    "warehouse": "Branch",
    "brand": "Brand",
    "colour": "Colour",
    "color": "Colour",
    "size": "Size",
    "invoice": "Invoice No",
    "bill no": "Invoice No",
    "voucher": "Invoice No",
    "order id": "Invoice No",
    # "discount" must stay ahead of the quantity keywords below, because
    # "discount" literally contains the substring "count".
    "discount": "Discount",
    "gst": "Tax",
    "tax": "Tax",
    # Quantity before the money keywords so "Total Qty" / "Purchase Qty"
    # resolve to Quantity rather than to Line Total / Cost Price.
    "qty": "Quantity",
    "quant": "Quantity",
    "units": "Quantity",
    "pcs": "Quantity",
    "count": "Quantity",
    "purchase": "Cost Price",
    "cogs": "Cost Price",
    "buying": "Cost Price",
    "wholesale": "Cost Price",
    "landing": "Cost Price",
    "cost": "Cost Price",
    "taxable": "Line Total",
    "net amount": "Line Total",
    "line total": "Line Total",
    "total": "Line Total",
    "amount": "Line Total",
    "turnover": "Line Total",
    "revenue": "Line Total",
    "mrp": "Selling Price",
    "selling": "Selling Price",
    "unit price": "Selling Price",
    "rate": "Selling Price",
    "price": "Selling Price",
    "categ": "Category",
    "dept": "Category",
    "segment": "Category",
    "group": "Category",
    "item": "Item",
    "product": "Item",
    "particular": "Item",
    "style": "Item",
    "sku": "Item",
    "goods": "Item",
    "article": "Item",
}


# ── Column-name helpers ─────────────────────────────────────────────────────


def _normalize_col_name(col: str) -> str:
    """Strip whitespace/BOM and lowercase a raw header for alias lookup."""
    return col.strip().lstrip("\ufeff").lower()


def guess_canonical_column(raw_col: str) -> tuple[str | None, str]:
    """
    Best-guess a single raw column name to one of the canonical fields.

    Returns ``(canonical_name_or_None, confidence)`` where confidence is
    ``"exact"`` (alias-map hit), ``"fuzzy"`` (keyword substring match — the
    UI asks the user to confirm these) or ``"none"`` (no match; the column
    is simply ignored, e.g. "Notes", "HSN", "Remarks").
    """
    cleaned = _normalize_col_name(raw_col)

    if cleaned in COLUMN_ALIAS_MAP:
        return COLUMN_ALIAS_MAP[cleaned], "exact"

    for keyword, canonical in _FUZZY_KEYWORDS.items():
        if keyword in cleaned:
            return canonical, "fuzzy"

    return None, "none"


def detect_column_mapping(df: pd.DataFrame) -> list[dict]:
    """
    Build a best-guess mapping report for every column in the uploaded file
    **without** renaming or mutating anything. This is what the frontend
    shows on the "confirm your columns" screen — every shopkeeper's export
    format differs, so we never assume our guess is right.

    One subtlety handled here: two different raw columns can plausibly map
    to the same field (e.g. "Rate" and "MRP" both look like Selling Price).
    Only the first is kept as a suggestion; later duplicates are downgraded
    to "no guess" so the user explicitly picks the right one instead of us
    silently overwriting a column during the rename step.
    """
    report: list[dict] = []
    already_suggested: set[str] = set()

    for raw_col in df.columns:
        canonical, confidence = guess_canonical_column(str(raw_col))
        if canonical and canonical in already_suggested:
            canonical, confidence = None, "none"
        if canonical:
            already_suggested.add(canonical)
        report.append(
            {
                "raw_column": str(raw_col),
                "suggested_field": canonical,
                "confidence": confidence,
            }
        )
    return report


def apply_column_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    Rename columns using an EXPLICIT, user-confirmed mapping instead of the
    automatic guesser. ``mapping`` is ``{raw_column: canonical_field}`` as
    returned (and possibly corrected) by the mapping screen.

    Unmapped columns pass through untouched — they simply never match a
    canonical name, so the rest of the pipeline ignores them. Values that
    aren't recognised canonical fields are skipped rather than trusted,
    since this mapping arrives from the client.
    """
    rename = {
        raw: canonical
        for raw, canonical in mapping.items()
        if raw in df.columns and canonical in set(MAPPABLE_FIELDS)
    }
    return df.rename(columns=rename)


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Auto-detect renaming, used when no confirmed mapping exists (quick
    previews, programmatic/test calls, or a file whose headers already match
    our aliases). The main upload flow always goes through
    ``apply_column_mapping`` instead.
    """
    guesses = detect_column_mapping(df)
    renamed = {
        g["raw_column"]: g["suggested_field"]
        for g in guesses
        if g["suggested_field"]
    }
    return df.rename(columns=renamed)


def _derive_selling_price_from_line_total(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill in a per-unit ``Selling Price`` from ``Line Total ÷ Quantity`` when
    the file only carries a line-total column.

    This is the fix for the double-counting bug described in the module
    docstring: without it, a file with ``Amount`` but no unit rate would
    report revenue as ``Quantity × Amount``.
    """
    if "Selling Price" in df.columns or "Line Total" not in df.columns:
        return df
    if "Quantity" not in df.columns:
        return df

    out = df.copy()
    total = pd.to_numeric(out["Line Total"], errors="coerce")
    qty = pd.to_numeric(out["Quantity"], errors="coerce")
    # Only divide where quantity is a usable positive number; everywhere else
    # the result stays NaN and the row is reported as missing Selling Price.
    usable = qty.notna() & (qty > 0)
    derived = pd.Series(np.nan, index=out.index, dtype="float64")
    derived[usable] = total[usable] / qty[usable]
    out["Selling Price"] = derived
    return out


def _validate_columns_exist(df: pd.DataFrame) -> None:
    """Raise a user-readable ``ValueError`` listing any missing required column."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns after normalisation: {', '.join(sorted(missing))}. "
            f"Your file has: {', '.join(str(c) for c in sorted(df.columns))}. "
            f"Expected one of: {', '.join(sorted(REQUIRED_COLUMNS))}."
        )


# ── Introspection helpers used by the query/chart layer ─────────────────────


def available_dimensions(df: pd.DataFrame) -> list[str]:
    """
    List the canonical text dimensions actually present in a normalised
    frame — always ``Category``/``Item``, plus whichever optional dimensions
    this particular shop's file provided. The chart engine and filter panel
    are built from this list, which is why an unmapped column can never
    become a selectable filter.
    """
    base = [c for c in ("Category", "Item") if c in df.columns]
    extras = [c for c in sorted(OPTIONAL_DIMENSION_COLUMNS) if c in df.columns]
    return base + extras


def available_measures(df: pd.DataFrame) -> list[str]:
    """List the optional numeric fields present in a normalised frame."""
    return [c for c in sorted(OPTIONAL_MEASURE_COLUMNS) if c in df.columns]


# ── Public entry point ─────────────────────────────────────────────────────


def normalize_dataframe(
    df: pd.DataFrame,
    soft_fail: bool = False,
    column_mapping: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean, type, and validate a raw DataFrame.

    Parameters
    ----------
    soft_fail : bool, default False
        When True a missing required column does not raise; instead a single
        schema error is returned with an empty frame, so upload endpoints
        can answer with a structured response rather than an HTTP 500.
    column_mapping : dict | None
        Explicit ``{raw_column: canonical_field}`` map confirmed by the user.
        When ``None``, the automatic alias/fuzzy guesser is used.

    Returns
    -------
    (clean_valid_df, errors)
        ``clean_valid_df`` holds only rows that passed every check, with
        required columns typed and any mapped optional columns preserved.
        ``errors`` is a list of ``{"row", "column", "error"}`` dicts.
    """
    df = apply_column_mapping(df, column_mapping) if column_mapping else _rename_columns(df)

    # Drop duplicate canonical columns before anything else: two raw columns
    # mapped to one field would make df["Quantity"] a DataFrame, not a
    # Series, and every downstream ``.astype`` would fail cryptically.
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

    df = _derive_selling_price_from_line_total(df)

    try:
        _validate_columns_exist(df)
    except ValueError as e:
        if soft_fail:
            return df.iloc[0:0].copy(), [{"row": 0, "column": "schema", "error": str(e)}]
        raise

    df = df.copy()

    # Keep only canonical columns from here on. Unmapped extras are dropped
    # so nothing unexpected (e.g. a huge free-text notes column) is carried
    # into the cache, the JSON responses, or the PDF.
    keep = [c for c in df.columns if c in set(MAPPABLE_FIELDS)]
    df = df[keep]

    # ── 1. Snapshot originals so error messages can quote what the user typed ──
    raw = {col: df[col].copy() for col in df.columns}
    errors: list[dict] = []

    # ── 2. Safe numeric coercion (errors="coerce" never raises) ──
    numeric_cols = [c for c in df.columns if STRICT_SCHEMA.get(c) in ("Number", "Integer")]
    for col in numeric_cols:
        num = pd.to_numeric(df[col], errors="coerce")
        # Retry the failures after stripping currency symbols, thousands
        # separators and stray spaces ("₹ 1,299.00" is a perfectly normal
        # value in an Indian retail export).
        still_bad = num.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
        if still_bad.any():
            cleaned = (
                df[col].astype(str).str.replace(r"[₹$€£,\s]", "", regex=True).str.strip()
            )
            retry = pd.to_numeric(cleaned, errors="coerce")
            num[still_bad] = retry[still_bad]
        # inf / -inf → NaN so the later .astype(int) can never choke.
        df[col] = num.replace([np.inf, -np.inf], np.nan)

    # ── 3. Two-pass date parsing ──
    # dayfirst handles DD-MM-YYYY (the Indian convention); the second pass
    # catches ISO 8601 rows the first pass rejected.
    parsed = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    still_nat = parsed.isna() & df["Date"].notna()
    if still_nat.any():
        parsed[still_nat] = pd.to_datetime(df["Date"][still_nat], errors="coerce")
    df["Date"] = parsed

    # ── 4. Required text columns: blank → NaN so dropna removes the row ──
    for col in ("Category", "Item"):
        df.loc[raw[col].apply(_is_empty), col] = np.nan

    # ── 5. Row-level error collection from the coerced frame ──
    _collect_all_errors(df, raw, errors)

    # ── 6. Drop rows missing any required field ──
    valid_df = df.dropna(subset=sorted(REQUIRED_COLUMNS)).copy()
    if valid_df.empty:
        return valid_df, errors

    # ── 7. Final typing — guaranteed NaN/inf-free by the steps above ──
    valid_df["Quantity"] = valid_df["Quantity"].astype(int)
    valid_df["Selling Price"] = valid_df["Selling Price"].astype(float)
    valid_df["Cost Price"] = valid_df["Cost Price"].astype(float)
    for col in ("Category", "Item"):
        valid_df[col] = valid_df[col].fillna("").astype(str).str.strip()

    # Optional measures: a blank discount/tax means "none charged", so 0 is
    # the correct fill. Stock On Hand is deliberately left as NaN when
    # unknown — filling it with 0 would fake a stockout that isn't real.
    for col in ("Discount", "Tax", "Line Total"):
        if col in valid_df.columns:
            valid_df[col] = valid_df[col].fillna(0.0).astype(float).clip(lower=0.0)
    if "Stock On Hand" in valid_df.columns:
        valid_df["Stock On Hand"] = valid_df["Stock On Hand"].astype(float)

    # Optional dimensions: blank → "Unspecified" so grouping stays complete
    # and no row is silently excluded from a branch/payment-mode breakdown.
    for col in OPTIONAL_DIMENSION_COLUMNS:
        if col in valid_df.columns:
            values = valid_df[col].astype(str).str.strip()
            valid_df[col] = values.mask(values.isin(("", "nan", "None", "NaT")), UNSPECIFIED)

    # ── 8. Business rules (physically impossible values) ──
    valid_df, business_errors = _validate_business_rules(valid_df)
    errors.extend(business_errors)

    return valid_df, errors


def _is_empty(val) -> bool:
    """True for ``None``, ``NaN``/``NaT``, and whitespace-only strings."""
    if val is None:
        return True
    if isinstance(val, (float, np.floating)) and np.isnan(val):
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    try:
        return bool(pd.isna(val))
    except Exception:
        return False


def _collect_all_errors(df: pd.DataFrame, raw: dict, errors: list) -> None:
    """
    Inspect the *coerced* frame and report every cell that failed: NaN/NaT in
    a required column, non-integer quantities, and unparseable values in an
    optional numeric column (reported, but never a reason to drop the row).
    """
    # Required numeric columns — a failure here drops the row.
    for col in ("Quantity", "Selling Price", "Cost Price"):
        for idx in df.index[df[col].isna()]:
            orig = raw[col].loc[idx] if col in raw else None
            if _is_empty(orig):
                errors.append({"row": int(idx), "column": col, "error": f"Missing {col}"})
            else:
                errors.append(
                    {
                        "row": int(idx),
                        "column": col,
                        "error": f"Invalid {col}: Expected Number, received '{str(orig)[:80]}'",
                    }
                )

    # Quantity must be a whole number of pieces.
    qty_ok = df["Quantity"].notna()
    not_whole = pd.Series(False, index=df.index)
    if qty_ok.any():
        valid_qty = df.loc[qty_ok, "Quantity"]
        not_whole.loc[qty_ok] = valid_qty != valid_qty.astype(int)
    for idx in df.index[not_whole]:
        errors.append(
            {
                "row": int(idx),
                "column": "Quantity",
                "error": f"Invalid Quantity: Expected Integer, received Number ('{raw['Quantity'].loc[idx]}')",
            }
        )

    # Date
    for idx in df.index[df["Date"].isna()]:
        orig = raw["Date"].loc[idx]
        if _is_empty(orig):
            errors.append({"row": int(idx), "column": "Date", "error": "Missing Date"})
        else:
            errors.append(
                {
                    "row": int(idx),
                    "column": "Date",
                    "error": f"Invalid Date: Expected Valid Date, received '{str(orig)[:80]}'",
                }
            )

    # Required text columns
    for col in ("Category", "Item"):
        for idx in df.index[df[col].isna()]:
            orig = raw[col].loc[idx]
            if _is_empty(orig):
                errors.append({"row": int(idx), "column": col, "error": f"Missing {col}"})
            else:
                errors.append(
                    {
                        "row": int(idx),
                        "column": col,
                        "error": f"Invalid {col}: Expected Text, received '{str(orig)[:80]}'",
                    }
                )

    # Optional numeric columns — reported for transparency, row still counts.
    for col in sorted(OPTIONAL_MEASURE_COLUMNS):
        if col not in df.columns:
            continue
        bad = df[col].isna() & raw[col].apply(lambda v: not _is_empty(v))
        for idx in df.index[bad]:
            errors.append(
                {
                    "row": int(idx),
                    "column": col,
                    "error": (
                        f"Ignored {col}: Expected Number, received "
                        f"'{str(raw[col].loc[idx])[:80]}' (row still analysed)"
                    ),
                }
            )


def _validate_business_rules(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Enforce physical constraints on the clean, typed frame. Rows that break
    them are removed and reported:

    - ``Quantity <= 0``      — a sale of zero or negative pieces
    - ``Selling Price < 0``  — negative price
    - ``Cost Price < 0``     — negative cost

    Deliberately **not** flagged: ``Cost Price > Selling Price``. Selling
    below cost is a real clearance-sale scenario, and flagging it would
    delete exactly the rows a margin-leak insight needs to find.
    """
    errors: list[dict] = []
    valid = pd.Series(True, index=df.index)

    checks = (
        ("Quantity", df["Quantity"] <= 0, "Quantity must be greater than zero."),
        ("Selling Price", df["Selling Price"] < 0, "Selling Price cannot be negative."),
        ("Cost Price", df["Cost Price"] < 0, "Cost Price cannot be negative."),
    )
    for column, failed_mask, message in checks:
        for idx in df.index[failed_mask]:
            errors.append({"row": int(idx), "column": column, "error": message})
        valid[failed_mask] = False

    return df[valid].copy(), errors
