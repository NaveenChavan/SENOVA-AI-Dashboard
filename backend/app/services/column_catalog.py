"""
The canonical *semantic* field catalog for the 2-tier column-understanding
pipeline.

Why this layer exists at all
----------------------------
The rest of SENOVA already has a canonical vocabulary — 17 field names in
``app/utils/data_validator.py`` (``Date``, ``Item``, ``Quantity``,
``Selling Price``, …). This module deliberately does **not** replace it.

Instead it introduces an internal vocabulary of *meanings* — 16 labels that
describe what a column is for — and translates those onto the existing 17
fields at the very end (``SEMANTIC_TO_CANONICAL``). Two reasons:

1. The meaning vocabulary is richer than the analysis vocabulary. ``mrp``,
   ``status``, ``notes`` and ``region`` are real concepts a shopkeeper's export
   contains, but none of them is a canonical field today. Keeping them here
   means Tier 1 can still *recognise* ("this is an MRP column") and report it
   to the user as "recognised, not analysed" — instead of either silently
   dropping it or force-fitting it onto ``Selling Price``, which is how MRP used
   to be handled and was simply wrong (an MRP is a list price, not a realised
   selling price).
2. Nothing downstream changes. ``normalize_dataframe`` still drops anything not
   in ``MAPPABLE_FIELDS``; the query engine, insight engine, chart studio, PDF
   generator and every existing test keep seeing exactly the same field names.

The catalog doubles as the anchor corpus for Tier 1's embedding model: each
label's ``description`` plus every ``synonym`` becomes one embedded anchor text
(see ``app/services/embedder.py``), and a column header is scored by cosine
similarity against them. Synonyms therefore carry real weight — they are not
documentation, they are what the classifier matches on. They include Hindi and
Hinglish spellings because shop exports are routinely bilingual
(``तारीख``, ``मात्रा``, ``Kitne``, ``Paisa``).

Privacy note
------------
``PII_SENSITIVE_LABELS`` lists meanings whose *values* must never leave the
server, no matter what the client asks for. ``app/services/pii_mask.py``
enforces it. ``notes`` is included alongside ``customer`` because a free-text
remarks column routinely carries a person's name ("damaged return — Mr. Sharma")
alongside the business content, which is exactly the kind of value an
unmasked sample would leak.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.column_dictionary import semantic_synonyms_by_label
from app.utils.data_validator import (
    OPTIONAL_MEASURE_COLUMNS,
    REQUIRED_COLUMNS,
)


@dataclass(frozen=True)
class SemanticField:
    """
    One meaning the classifier can assign to a column.

    ``description`` is the natural-language anchor the embedding model scores
    against, so it is written as a definition rather than a one-word label —
    "the number of units sold" retrieves far better than "quantity".

    ``synonyms`` are literal header spellings. Each becomes its own anchor, so
    an exact-ish alias like ``"Qty."`` gets a direct hit instead of relying on
    the description to happen to sit nearby in vector space.
    """

    label: str
    description: str
    synonyms: tuple[str, ...]


#: Every meaning the pipeline can assign, paired with its natural-language
#: anchor description. ``other`` is the deliberate "we recognised this as
#: *not* one of our concepts" bucket — never a synonym for "unmapped", because
#: Tier 2 can still take a run at an ``other`` column and move it to a real
#: label.
#:
#: Phase 3: only the ``(label, description)`` pairs live here now. The literal
#: synonym tuples (359 entries total) moved to ``app/data/column_dictionary.json``
#: and are loaded back in below via ``semantic_synonyms_by_label()`` — see
#: ``SEMANTIC_FIELDS`` immediately after this definition. Descriptions stay as
#: code literals because they are prose written for the embedding model, not
#: dictionary data.
_FIELD_DEFINITIONS: tuple[tuple[str, str], ...] = (
    (
        "date",
        "The calendar date or timestamp on which a transaction happened — "
        "bill date, invoice date, voucher date, order date, sale date.",
    ),
    (
        "quantity",
        "How many individual pieces or units were sold on a line — pieces, "
        "pcs, stock quantity, units sold, billed quantity.",
    ),
    (
        "unit_price",
        "The selling price of ONE single piece — the retail rate per unit, "
        "not the total for the whole line.",
    ),
    (
        "mrp",
        "The maximum retail price — the printed list price shown to a "
        "customer before any discount. This is NOT the price actually "
        "charged and NOT the cost price.",
    ),
    (
        "cost",
        "What the shop paid for ONE piece — purchase rate, cost price, "
        "buying price, wholesale rate, landed cost, COGS.",
    ),
    (
        "revenue",
        "The total amount for a whole invoice line — quantity multiplied "
        "by the unit price, i.e. the line total, net amount or taxable "
        "value. This is a LINE TOTAL, not a per-unit price.",
    ),
    (
        "discount",
        "A reduction given off the line — a discount amount, rebate or "
        "less-discount value, usually in rupees.",
    ),
    (
        "tax",
        "Government tax collected on the line — GST, CGST, SGST, IGST or "
        "VAT, reported separately and never counted as profit.",
    ),
    (
        "product",
        "The name of the individual product, garment, style or article that "
        "was sold — the specific thing, not the group it belongs to.",
    ),
    (
        "currency",
        "The currency code or symbol for the money amounts on this row — "
        "INR, USD, EUR, Rs, etc.",
    ),
    (
        "category",
        "The group or department a product belongs to — Kurta, Saree, "
        "Shirt, Grocery, Beverages. A classification of the product, not "
        "the product itself.",
    ),
    (
        "customer",
        "The person or business the sale was made to — customer name, "
        "buyer, party, client. Personal data.",
    ),
    (
        "region",
        "A geographical or organisational location the sale happened at — "
        "branch, store, shop, outlet, godown, warehouse, city.",
    ),
    (
        "status",
        "The state of the order or transaction — pending, shipped, delivered, "
        "cancelled, returned, paid or unpaid.",
    ),
    (
        "notes",
        "Free-text remarks written by staff about the transaction — "
        "delivery instructions, damage reports, supplier notes, anything "
        "typed in a remarks or observation box.",
    ),
    (
        "id",
        "A unique reference number identifying a transaction or document — "
        "invoice number, bill number, voucher number, receipt number or "
        "order id.",
    ),
    (
        "other",
        "A column that matches none of the known business meanings — an "
        "unrecognised extra, a technical artefact, or free text we cannot "
        "place.",
    ),
)

#: Synonym lists loaded from ``app/data/column_dictionary.json``, keyed by
#: semantic label, in the exact order the hardcoded tuples used to carry —
#: see ``build_dictionary_json.py``'s ``semantic_order`` field and
#: ``column_dictionary._synonyms_by_label`` for how that order survives the
#: round-trip through JSON.
_SYNONYMS_FROM_DICT: dict[str, list[str]] = semantic_synonyms_by_label()

#: Every meaning the pipeline can assign. Combines the code-literal
#: descriptions above with the JSON-loaded synonym lists. The synonym ORDER
#: per label must stay identical to the pre-migration hardcoded order because
#: ``catalog_anchors()`` produces anchors in this order and the cached
#: ``catalog_embeddings.npz`` is index-matched against it.
SEMANTIC_FIELDS: tuple[SemanticField, ...] = tuple(
    SemanticField(
        label=label,
        description=description,
        synonyms=tuple(_SYNONYMS_FROM_DICT.get(label, ())),
    )
    for label, description in _FIELD_DEFINITIONS
)



#: Label → its definition. Ordered like ``SEMANTIC_FIELDS`` so anchor indices
#: line up with it.
LABEL_BY_NAME: dict[str, SemanticField] = {f.label: f for f in SEMANTIC_FIELDS}

#: Every label the classifier may return, in catalog order.
SEMANTIC_LABELS: tuple[str, ...] = tuple(f.label for f in SEMANTIC_FIELDS)

#: Labels that mean "we don't know what this is". Kept explicit so callers
#: never compare against a bare string literal.
UNKNOWN_LABEL = "other"
UNKNOWN_LABELS: frozenset[str] = frozenset({"", UNKNOWN_LABEL})

#: Meanings whose *values* must never be sent to an external model, whatever
#: the client asks for. ``pii_mask.should_suppress_values`` enforces this.
#:
#: ``customer`` is obvious. ``notes`` is here because staff remarks routinely
#: contain a person's name — "damaged return, Mr. Sharma called" — so a remarks
#: sample is personal data even though "notes" is not a name column.
PII_SENSITIVE_LABELS: frozenset[str] = frozenset({"customer", "notes"})


# ── Semantic → canonical translation ─────────────────────────────────────────

#: Maps a meaning onto the field name the rest of SENOVA uses, or ``None`` for
#: meanings we recognise but do not analyse. ``None`` is the honest answer for
#: ``mrp``, ``status`` and ``notes``: force-fitting any of them onto a canonical
#: field would corrupt a number somewhere.
#:
#: ``unit_price`` → ``Selling Price`` and ``revenue`` → ``Line Total`` are the
#: two that carry real correctness weight. The second is the fix the README
#: already documents: an ``Amount`` column holds a LINE TOTAL, so mapping it to
#: ``Selling Price`` would inflate revenue by the quantity factor on every row.
SEMANTIC_TO_CANONICAL: dict[str, str | None] = {
    "date": "Date",
    "quantity": "Quantity",
    "unit_price": "Selling Price",
    "cost": "Cost Price",
    "revenue": "Line Total",
    "discount": "Discount",
    "tax": "Tax",
    "product": "Item",
    "category": "Category",
    "customer": "Customer",
    "region": "Branch",
    "mrp": "MRP",
    # Recognised, deliberately not analysed.
    "status": None,
    "notes": None,
    "currency": None,
    # Resolved at call time by ``canonical_field_for`` — a bare "id" is not
    # enough to justify calling something an Invoice No.
    "id": None,
    "other": None,
}

#: Header substrings that promote a bare ``id``-ish column to ``Invoice No``.
#: Without this gate, a customer-row id or a stock-code column would be reported
#: as an invoice number purely because it contained the word "id".
#:
#: Note these are all *qualified* document words ("serial no", not "serial"): a
#: column headed plainly "Serial" in a garment register could be a garment serial
#: number, and guessing an invoice reference from that would put a meaningless
#: value into the ledger.
_ID_HEADER_PROMOTIONS: tuple[str, ...] = (
    "invoice", "bill", "voucher", "receipt", "order", "txn", "transaction",
    "document", "doc no", "ref no", "serial no", "serial number", "sr no",
    "sr. no", "sr number",
    # Hindi / Hinglish
    "बिल", "चालान", "पर्ची", "क्रमांक",
)


def catalog_anchors() -> list[tuple[str, str]]:
    """
    Every text the Tier 1 model is embedded against, paired with the label it
    belongs to.

    Each label contributes its long ``description`` (which catches paraphrases
    and unseen spellings) plus every ``synonym`` (which gives a direct hit to
    literal headers like ``"Qty."``). Embedding all of them is what makes a
    match a maximum over anchors rather than a single blurry comparison.

    Returned in a fixed order so the cached embedding matrix and this list can
    be index-matched forever.
    """
    anchors: list[tuple[str, str]] = []
    for field in SEMANTIC_FIELDS:
        anchors.append((field.label, field.description))
        anchors.extend((field.label, synonym) for synonym in field.synonyms)
    return anchors


def is_known_label(label: str | None) -> bool:
    """True when ``label`` is a real meaning (not ``None``/``""``/``"other"``)."""
    if label is None:
        return False
    return label.strip().lower() not in UNKNOWN_LABELS


def canonical_field_for(label: str | None, raw_header: str = "") -> str | None:
    """
    Translate a meaning into the canonical field name the rest of SENOVA uses.

    Returns ``None`` for meanings with no canonical target (``mrp``, ``status``,
    ``notes``, ``other``) and for a bare ``id`` column that does not look like a
    document reference — see ``_ID_HEADER_PROMOTIONS`` for why that gate exists.

    ``raw_header`` is used only for that one ``id`` decision; every other
    mapping is unconditional.
    """
    if label is None:
        return None

    normalised = label.strip().lower()
    if normalised in UNKNOWN_LABELS:
        return None

    if normalised == "id":
        header = raw_header.strip().lower()
        if any(token in header for token in _ID_HEADER_PROMOTIONS):
            return "Invoice No"
        return None

    return SEMANTIC_TO_CANONICAL.get(normalised)


def analysable_canonical_fields() -> set[str]:
    """
    The canonical fields this pipeline is able to produce.

    Useful as an assertion target: if a translation ever invents a name outside
    the existing schema, ``normalize_dataframe`` would silently drop that column
    and the UI would show a mapping the backend quietly ignores. Deriving the set
    here makes that class of bug testable.
    """
    fields: set[str] = set(REQUIRED_COLUMNS) | set(OPTIONAL_MEASURE_COLUMNS)
    for label in SEMANTIC_LABELS:
        canonical = canonical_field_for(label)
        if canonical:
            fields.add(canonical)
    return fields