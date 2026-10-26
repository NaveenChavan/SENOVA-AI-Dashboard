"""
Deterministic classification and per-file registry for extra columns.

Phase 1 requirements:
- Deterministic classification into Date-like, ID-like, Personal/PII, Numeric,
  Low-cardinality text, and Other text.
- Cap extra columns at 30 per file.
- Keep original header as display label.
- Safe deterministic keys: x_dim:<slug>, x_meas:<slug>, x_col:<slug>.
- Strict collision handling for duplicate/odd headers.
- No eval/code/SQL generation from headers.
"""

from __future__ import annotations

import re
from typing import Any
import numpy as np
import pandas as pd

from app.services.pii_mask import _EMAIL_RE, _PHONE_RE, _LONG_NUMBER_RE

# Maximum unmapped extra columns classified and preserved per file
MAX_EXTRA_COLUMNS = 30

_ID_HEADER_SUBSTRINGS = ("id", "no", "number", "code", "ref")
_AVERAGE_HEADER_SUBSTRINGS = ("%", "pct", "percent", "rate", "ratio", "margin")


def make_safe_slug(header: str) -> str:
    """
    Produce a deterministic, alphanumeric lowercase identifier from a header name.
    Does not allow dynamic code or SQL characters.
    """
    cleaned = header.replace("%", "_pct_")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", cleaned.strip().lower()).strip("_")
    # Collapse multiple consecutive underscores
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = "col"
    return slug


def is_date_like(series: pd.Series) -> bool:
    """True if parse ratio as datetime >= 0.80."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    # Numeric series without delimiters are not dates
    if pd.api.types.is_numeric_dtype(non_null):
        return False
    sample = non_null.head(100)
    sample_str = sample.astype(str)
    # Require at least some date delimiter (-, /, .) before attempting datetime parsing
    if not sample_str.str.contains(r"[-/\.]", regex=True).any():
        return False
    try:
        parsed = pd.to_datetime(sample_str, errors="coerce", format="mixed")
        valid_ratio = parsed.notna().sum() / len(sample)
        return valid_ratio >= 0.80
    except Exception:
        return False


def is_id_like(header: str, series: pd.Series) -> bool:
    """
    Header contains id/no/number/code/ref;
    OR integer-looking unique ratio >= 0.90;
    OR constant column (1 distinct value).
    """
    h_lower = header.strip().lower()
    # Check substring tokens
    tokens = re.split(r"[^a-z0-9]+", h_lower)
    if any(tok in _ID_HEADER_SUBSTRINGS for tok in tokens) or any(
        sub in h_lower for sub in ("order_id", "order id", "invoice_no", "doc_no", "ref_no", "code", "number")
    ):
        return True

    non_null = series.dropna()
    if non_null.empty:
        return False

    n_distinct = non_null.nunique()
    if n_distinct == 1:
        return True

    # Check integer-looking high uniqueness
    if len(non_null) > 0:
        unique_ratio = n_distinct / len(non_null)
        if unique_ratio >= 0.90:
            # Check if values look like integers or codes
            sample = non_null.head(50).astype(str)
            digits_count = sum(1 for s in sample if s.strip().isdigit())
            if digits_count / len(sample) >= 0.80:
                return True

    return False


def is_personal_pii(header: str, series: pd.Series) -> bool:
    """Header indicates customer/contact, or values match email/phone patterns."""
    h_lower = header.strip().lower()
    tokens = set(re.split(r"[^a-z0-9]+", h_lower))
    # These headers identify direct or high-risk personal information. The
    # exception for product-like names prevents harmless catalogue labels such
    # as "Product Name" from being treated as a person's identity.
    personal_terms = (
        "phone", "mobile", "email", "contact", "aadhaar", "ssn", "pan",
        "address", "customer", "client", "recipient", "patient", "dob",
        "birth", "personal", "account holder", "taxpayer",
    )
    if any(term in h_lower for term in personal_terms):
        return True
    product_name_context = {"product", "item", "brand", "style", "model", "design", "sku"}
    if "name" in tokens and not tokens.intersection(product_name_context):
        return True

    non_null = series.dropna().astype(str)
    if non_null.empty:
        return False

    sample = non_null.head(50)
    email_hits = sum(1 for s in sample if _EMAIL_RE.search(s))
    phone_hits = sum(1 for s in sample if _PHONE_RE.search(s) or _LONG_NUMBER_RE.search(s))
    if (email_hits / len(sample) >= 0.30) or (phone_hits / len(sample) >= 0.30):
        return True

    return False


def is_numeric_column(series: pd.Series) -> bool:
    """Returns True if a safe numeric conversion can be measured on >= 80% of rows."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    sample = non_null.head(100)
    cleaned = sample.astype(str).str.replace(r"[₹$€£,\s]", "", regex=True)
    converted = pd.to_numeric(cleaned, errors="coerce")
    return (converted.notna().sum() / len(sample)) >= 0.80


def classify_single_column(header: str, series: pd.Series) -> dict[str, Any]:
    """
    Classify one unmapped extra column deterministically according to Phase 1 rules.
    """
    h_lower = header.strip().lower()

    # 1. Personal / PII must take precedence over data shape. For example,
    # a Customer DOB column is date-like too, but treating it as ordinary
    # date-like data would leave the original birth dates readable in analytics.
    if is_personal_pii(header, series):
        return {
            "class_name": "personal",
            "role": "stored_only",
            "aggregation": None,
            "how_used": "Stored-only",
            "reason": "Personal / contact data preserved as stored-only; values redacted and never offered as filter or axis.",
        }

    # 2. Date-like
    if is_date_like(series):
        return {
            "class_name": "date_like",
            "role": "stored_only",
            "aggregation": None,
            "how_used": "Stored-only",
            "reason": "Date-like column preserved as stored-only; not designated primary sales date.",
        }

    # 3. ID-like
    if is_id_like(header, series):
        return {
            "class_name": "id_like",
            "role": "stored_only",
            "aggregation": None,
            "how_used": "Stored-only",
            "reason": "Identifier / reference column preserved as stored-only; leading zeroes preserved.",
        }

    # 4. Numeric -> Extra Measure
    if is_numeric_column(series):
        is_avg = any(sub in h_lower for sub in _AVERAGE_HEADER_SUBSTRINGS)
        agg = "average" if is_avg else "sum"
        return {
            "class_name": "numeric",
            "role": "extra_measure",
            "aggregation": agg,
            "how_used": f"Extra measure ({agg})",
            "reason": None,
        }

    # 5. Low-cardinality text vs Free text / Other text
    non_null = series.dropna()
    n_distinct = non_null.nunique()
    unique_ratio = (n_distinct / len(non_null)) if len(non_null) > 0 else 1.0

    # Indicators of free text / notes / comments
    is_free_text_header = any(sub in h_lower for sub in ("note", "comment", "desc", "remark", "address", "msg", "message", "memo"))
    is_high_uniqueness = (unique_ratio > 0.60 and len(non_null) > 5)

    if not is_free_text_header and not is_high_uniqueness and n_distinct <= 50 and n_distinct > 0:
        return {
            "class_name": "low_cardinality_text",
            "role": "extra_dimension",
            "aggregation": None,
            "how_used": "Extra dimension",
            "reason": None,
        }

    # 6. Other text -> Stored-only
    return {
        "class_name": "other_text",
        "role": "stored_only",
        "aggregation": None,
        "how_used": "Stored-only",
        "reason": "High-cardinality or free text preserved as stored-only.",
    }


def classify_extra_columns(
    df: pd.DataFrame,
    mapped_raw_columns: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """
    Classify unmapped columns in df, capped at MAX_EXTRA_COLUMNS (30).
    
    Returns:
    - registry: {safe_key: {key, display_label, class_name, role, aggregation, how_used, reason}}
    - raw_to_safe: {raw_column: safe_key}
    """
    mapped = mapped_raw_columns if mapped_raw_columns is not None else set()
    unmapped = [col for col in df.columns if col not in mapped]
    # Cap at MAX_EXTRA_COLUMNS
    selected_extras = unmapped[:MAX_EXTRA_COLUMNS]

    registry: dict[str, dict[str, Any]] = {}
    raw_to_safe: dict[str, str] = {}
    used_slugs: dict[str, int] = {}

    for raw_col in selected_extras:
        series = df[raw_col]
        classification = classify_single_column(raw_col, series)
        role = classification["role"]

        prefix = "x_col"
        if role == "extra_measure":
            prefix = "x_meas"
        elif role == "extra_dimension":
            prefix = "x_dim"

        base_slug = make_safe_slug(raw_col)
        # Collision handling for duplicate/odd headers
        count = used_slugs.get(base_slug, 0) + 1
        used_slugs[base_slug] = count
        safe_name = base_slug if count == 1 else f"{base_slug}_{count}"
        safe_key = f"{prefix}:{safe_name}"

        info = {
            "key": safe_key,
            "display_label": str(raw_col),
            "class_name": classification["class_name"],
            "role": role,
            "aggregation": classification["aggregation"],
            "how_used": classification["how_used"],
            "reason": classification["reason"],
        }
        registry[safe_key] = info
        raw_to_safe[raw_col] = safe_key

    return registry, raw_to_safe
