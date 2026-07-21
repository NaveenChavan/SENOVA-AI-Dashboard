"""
Data validation and normalisation layer.

Safe coercion pipeline (never crashes on bad values):
1. Rename columns via alias map.
2. Assert all 6 canonical columns exist (hard error).
3. ``pd.to_numeric(..., errors='coerce')`` on Quantity / Selling Price / Cost Price.
4. Retry with currency symbols stripped for values still NaN.
5. Replace ``inf`` / ``-inf`` with ``NaN`` — critical so ``.astype(int)`` never sees them.
6. ``pd.to_datetime(..., errors='coerce')`` on Date.
7. Convert empty Category / Item to ``NaN`` so ``dropna`` catches them.
8. Collect row-level errors from the coerced DataFrame.
9. ``dropna(subset=[all 6 columns])`` → only fully valid rows remain.
10. ``.astype(int)`` / ``.astype(float)`` — guaranteed NaN-free, guaranteed safe.
"""

import pandas as pd
import numpy as np

# ── Canonical column names ──────────────────────────────────────────────────
EXPECTED_COLUMNS = {"Date", "Category", "Item", "Quantity", "Selling Price", "Cost Price"}

STRICT_SCHEMA: dict[str, str] = {
    "Date": "Date",
    "Category": "Text",
    "Item": "Text",
    "Quantity": "Integer",
    "Selling Price": "Number",
    "Cost Price": "Number",
}

# ── Alias → canonical name mapping (case-insensitive) ──────────────────────
COLUMN_ALIAS_MAP: dict[str, str] = {
    "date": "Date",
    "date_sold": "Date",
    "transaction date": "Date",
    "sale date": "Date",
    "transaction_date": "Date",
    "sale_date": "Date",
    "sold date": "Date",
    "category": "Category",
    "cat": "Category",
    "categories": "Category",
    "product category": "Category",
    "product_category": "Category",
    "item category": "Category",
    "item_category": "Category",
    "dept": "Category",
    "type": "Category",
    "group": "Category",
    "segment": "Category",
    "item": "Item",
    "item name": "Item",
    "item_name": "Item",
    "product": "Item",
    "product name": "Item",
    "product_name": "Item",
    "description": "Item",
    "item description": "Item",
    "item_description": "Item",
    "product_description": "Item",
    "prod": "Item",
    "name": "Item",
    "goods": "Item",
    "sku": "Item",
    "article": "Item",
    "quantity": "Quantity",
    "qty": "Quantity",
    "qty.": "Quantity",
    "units": "Quantity",
    "unit": "Quantity",
    "units sold": "Quantity",
    "quantity sold": "Quantity",
    "qty sold": "Quantity",
    "qty_sold": "Quantity",
    "units_sold": "Quantity",
    "quantity_sold": "Quantity",
    "no.": "Quantity",
    "count": "Quantity",
    "sold": "Quantity",
    "num": "Quantity",
    "selling price": "Selling Price",
    "price": "Selling Price",
    "amount": "Selling Price",
    "sale price": "Selling Price",
    "unit price": "Selling Price",
    "price per unit": "Selling Price",
    "rate": "Selling Price",
    "selling_price": "Selling Price",
    "unit_price": "Selling Price",
    "retail price": "Selling Price",
    "retail_price": "Selling Price",
    "sales price": "Selling Price",
    "mrp": "Selling Price",
    "sp": "Selling Price",
    "rev": "Selling Price",
    "revenue": "Selling Price",
    "cost price": "Cost Price",
    "cost": "Cost Price",
    "unit cost": "Cost Price",
    "purchase price": "Cost Price",
    "cost_price": "Cost Price",
    "unit_cost": "Cost Price",
    "buying price": "Cost Price",
    "buying_price": "Cost Price",
    "wholesale price": "Cost Price",
    "wholesale_price": "Cost Price",
    "cp": "Cost Price",
    "cogs": "Cost Price",
}

# ── Fuzzy keyword mapping for unknown column names (last-resort heuristic) ─
_FUZZY_KEYWORDS: dict[str, str] = {
    "date": "Date",
    "sold": "Date",
    "sell": "Date",
    "cat": "Category",
    "dept": "Category",
    "segment": "Category",
    "group": "Category",
    "item": "Item",
    "prod": "Item",
    "goods": "Item",
    "sku": "Item",
    "article": "Item",
    "qty": "Quantity",
    "quant": "Quantity",
    "units": "Quantity",
    "count": "Quantity",
    "price": "Selling Price",
    "selling": "Selling Price",
    "mrp": "Selling Price",
    "rate": "Selling Price",
    "amount": "Selling Price",
    "revenue": "Selling Price",
    "rev": "Selling Price",
    "cost": "Cost Price",
    "cogs": "Cost Price",
    "buying": "Cost Price",
    "wholesale": "Cost Price",
    "purchase": "Cost Price",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_col_name(col: str) -> str:
    """Strip whitespace and BOM, then lowercase, for alias lookup."""
    return col.strip().lstrip("\ufeff").lower()


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        cleaned = _normalize_col_name(col)
        if cleaned in COLUMN_ALIAS_MAP:
            renamed[col] = COLUMN_ALIAS_MAP[cleaned]
            continue
        # Fuzzy last-resort: first keyword in the column name wins.
        for keyword, canonical in _FUZZY_KEYWORDS.items():
            if keyword in cleaned:
                renamed[col] = canonical
                break
        else:
            renamed[col] = col
    return df.rename(columns=renamed)


def _validate_columns_exist(df: pd.DataFrame) -> None:
    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns after normalisation: {', '.join(sorted(missing))}. "
            f"Your file has: {', '.join(sorted(df.columns))}. "
            f"Expected one of: {', '.join(sorted(EXPECTED_COLUMNS))}."
        )


# ── Public entry point ─────────────────────────────────────────────────────


def normalize_dataframe(df: pd.DataFrame, soft_fail: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """
    Clean, type, and validate a raw DataFrame.

    Returns
    -------
    (clean_valid_df, errors)
        ``clean_valid_df`` contains only rows that passed **every** type check.
        ``errors`` is a list of ``{"row": int, "column": str, "error": str}``
        dicts describing every cell-level failure.

    Parameters
    ----------
    soft_fail : bool, default False
        When True, missing required columns do not raise ``ValueError``.
        Instead, every row is reported as an error and an empty valid_df
        is returned. Use this in upload flows so the endpoint always
        returns a structured response instead of an HTTP 500.

    Raises
    ------
    ValueError
        If any required column is entirely missing after the renaming step
        AND ``soft_fail`` is False.
    """
    df = _rename_columns(df)
    try:
        _validate_columns_exist(df)
    except ValueError as e:
        if soft_fail:
            return (
                df.iloc[0:0].copy(),
                [{"row": 0, "column": "schema", "error": str(e)}],
            )
        raise
    df = df.copy()

    # ── 1. Snapshot originals for error messages ──
    raw = {col: df[col].copy() for col in df.columns}
    errors: list[dict] = []

    # ── 2. Safe coercion (errors='coerce' never crashes) ──
    for col in ("Quantity", "Selling Price", "Cost Price"):
        num = pd.to_numeric(df[col], errors="coerce")
        # Retry with currency / comma symbols for values still NaN
        still_bad = num.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
        if still_bad.any():
            cleaned = df[col].astype(str).str.replace(r'[\$,€,£,₹,]', "", regex=True).str.strip()
            retry = pd.to_numeric(cleaned, errors="coerce")
            num[still_bad] = retry[still_bad]
        # ── inf / -inf → NaN so .astype(int) never chokes ──
        num = num.replace([np.inf, -np.inf], np.nan)
        df[col] = num

    # Two-pass date parsing: dayfirst=True handles DD-MM-YYYY (Indian format);
    # fallback without dayfirst handles YYYY-MM-DD (ISO 8601) for any rows
    # that the first pass rejected.
    parsed = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    still_nat = parsed.isna() & df["Date"].notna()
    if still_nat.any():
        fallback = pd.to_datetime(df["Date"][still_nat], errors="coerce")
        parsed[still_nat] = fallback
    df["Date"] = parsed

    # ── 3. Normalise text columns: empty → NaN so dropna catches them ──
    for col in ("Category", "Item"):
        df.loc[raw[col].apply(_is_empty), col] = np.nan

    # ── 4. Collect all row-level errors from the coerced DataFrame ──
    _collect_all_errors(df, raw, errors)

    # ── 5. dropna — every remaining row has all 6 required fields valid ──
    required_cols = ["Quantity", "Selling Price", "Cost Price", "Date", "Category", "Item"]
    valid_df = df.dropna(subset=required_cols).copy()

    if valid_df.empty:
        return valid_df, errors

    # ── 6. Safe .astype() — zero NaN / inf in these columns ──
    valid_df["Quantity"] = valid_df["Quantity"].astype(int)
    valid_df["Selling Price"] = valid_df["Selling Price"].astype(float)
    valid_df["Cost Price"] = valid_df["Cost Price"].astype(float)
    for col in ("Category", "Item"):
        valid_df[col] = valid_df[col].fillna("").astype(str)

    # ── 7. Business rule validation ──
    # Physical constraints that make data physically impossible.
    # NOTE: Cost Price > Selling Price is NOT flagged — negative
    # profit (clearance sales) is a legitimate retail scenario.
    valid_df, business_errors = _validate_business_rules(valid_df)
    errors.extend(business_errors)

    return valid_df, errors


def _is_empty(val) -> bool:
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
    Inspect the *coerced* DataFrame and report every cell that is NaN / NaT
    in a required column, plus non-integer Quantity values.
    """
    for col in ("Quantity", "Selling Price", "Cost Price"):
        is_nan = df[col].isna()
        for idx in df.index[is_nan]:
            orig = raw[col].loc[idx]
            if _is_empty(orig):
                errors.append({
                    "row": int(idx),
                    "column": col,
                    "error": f"Missing {col}",
                })
            else:
                errors.append({
                    "row": int(idx),
                    "column": col,
                    "error": f"Invalid {col}: Expected Number, received '{str(orig)[:80]}'",
                })

    # Non-integer Quantity (value is numeric but not a whole number)
    qty_ok = df["Quantity"].notna()
    not_whole = pd.Series(False, index=df.index)
    if qty_ok.any():
        valid_qty = df.loc[qty_ok, "Quantity"]
        not_whole.loc[qty_ok] = valid_qty != valid_qty.astype(int)
    for idx in df.index[not_whole]:
        orig = raw["Quantity"].loc[idx]
        errors.append({
            "row": int(idx),
            "column": "Quantity",
            "error": f"Invalid Quantity: Expected Integer, received Number ('{orig}')",
        })

    # Date
    is_nat = df["Date"].isna()
    for idx in df.index[is_nat]:
        orig = raw["Date"].loc[idx]
        if _is_empty(orig):
            errors.append({"row": int(idx), "column": "Date", "error": "Missing Date"})
        else:
            errors.append({
                "row": int(idx),
                "column": "Date",
                "error": f"Invalid Date: Expected Valid Date, received '{str(orig)[:80]}'",
            })

    # Category / Item (now NaN thanks to step 3)
    for col in ("Category", "Item"):
        is_missing = df[col].isna()
        for idx in df.index[is_missing]:
            orig = raw[col].loc[idx]
            if _is_empty(orig):
                errors.append({"row": int(idx), "column": col, "error": f"Missing {col}"})
            else:
                errors.append({
                    "row": int(idx),
                    "column": col,
                    "error": f"Invalid {col}: Expected Text, received '{str(orig)[:80]}'",
                })


def _validate_business_rules(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Enforce physical constraints on the clean, typed DataFrame.

    The following are flagged as impossible data and removed:
    - Quantity <= 0
    - Selling Price < 0
    - Cost Price < 0

    NOT flagged (legitimate retail scenarios):
    - Cost Price > Selling Price  (clearance sale = negative profit)
    """
    errors: list[dict] = []
    valid = pd.Series(True, index=df.index)

    bad_qty = df["Quantity"] <= 0
    for idx in df.index[bad_qty]:
        errors.append({
            "row": int(idx),
            "column": "Quantity",
            "error": "Quantity must be greater than zero.",
        })
    valid[bad_qty] = False

    bad_sp = df["Selling Price"] < 0
    for idx in df.index[bad_sp]:
        errors.append({
            "row": int(idx),
            "column": "Selling Price",
            "error": "Selling Price cannot be negative.",
        })
    valid[bad_sp] = False

    bad_cp = df["Cost Price"] < 0
    for idx in df.index[bad_cp]:
        errors.append({
            "row": int(idx),
            "column": "Cost Price",
            "error": "Cost Price cannot be negative.",
        })
    valid[bad_cp] = False

    return df[valid].copy(), errors
