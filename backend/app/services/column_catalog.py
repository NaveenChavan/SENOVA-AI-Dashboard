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


#: Every meaning the pipeline can assign. ``other`` is the deliberate "we
#: recognised this as *not* one of our concepts" bucket — never a synonym for
#: "unmapped", because Tier 2 can still take a run at an ``other`` column and
#: move it to a real label.
SEMANTIC_FIELDS: tuple[SemanticField, ...] = (
    SemanticField(
        label="date",
        description=(
            "The calendar date or timestamp on which a transaction happened — "
            "bill date, invoice date, voucher date, order date, sale date."
        ),
        synonyms=(
            "date", "dates", "date_sold", "sale date", "sales date", "sold date",
            "transaction date", "txn date", "invoice date", "bill date",
            "billing date", "voucher date", "entry date", "posting date",
            "order date", "ordered on", "datetime", "timestamp", "day",
            # Hindi / Hinglish
            "तारीख", "बिल तारीख", "खरीद तारीख", "बिक्री तारीख", "दिनांक",
            "date kitne", "kis din", "din", "kab",
        ),
    ),
    SemanticField(
        label="quantity",
        description=(
            "How many individual pieces or units were sold on a line — pieces, "
            "pcs, stock quantity, units sold, billed quantity."
        ),
        synonyms=(
            "quantity", "qty", "qty.", "qnty", "quantities", "units", "unit",
            "nos", "no of units", "pieces", "pcs", "count", "units sold",
            "quantity sold", "qty sold", "billed qty", "sold qty", "actual qty",
            "order quantity", "lineitem quantity", "quantity-purchased",
            # Hindi / Hinglish
            "मात्रा", "कितना", "कितने", "संख्या", "पीस", "नग", "qty kya",
        ),
    ),
    SemanticField(
        label="unit_price",
        description=(
            "The selling price of ONE single piece — the retail rate per unit, "
            "not the total for the whole line."
        ),
        synonyms=(
            "selling price", "selling_price", "sale price", "sales price",
            "sell price", "price", "unit price", "unit_price", "price per unit",
            "price/unit", "rate", "rate/unit", "rate per unit", "unit rate",
            "retail price", "sp", "lineitem price", "item-price",
            # Hindi / Hinglish
            "इकाई मूल्य", "विक्रय मूल्य", "क्रय मूल्य", "दर", "भाव", "मूल्य",
            "ek kitna", "kitna paisa", "rate kya",
        ),
    ),
    SemanticField(
        label="mrp",
        description=(
            "The maximum retail price — the printed list price shown to a "
            "customer before any discount. This is NOT the price actually "
            "charged and NOT the cost price."
        ),
        synonyms=(
            "mrp", "m.r.p", "m.r.p.", "maximum retail price", "list price",
            "marked price", "printed price", "mrp price", "showroom price",
            # Hindi / Hinglish
            "एमआरपी", "अधिकतम खुदरा मूल्य", "सूची मूल्य", "छाप मूल्य",
            "mrp kitna", "maximum price",
        ),
    ),
    SemanticField(
        label="cost",
        description=(
            "What the shop paid for ONE piece — purchase rate, cost price, "
            "buying price, wholesale rate, landed cost, COGS."
        ),
        synonyms=(
            "cost price", "cost_price", "cost", "unit cost", "unit_cost",
            "cost per unit", "purchase price", "purchase_price", "purchase rate",
            "buying price", "buying_price", "wholesale price", "wholesale_price",
            "landing cost", "landed cost", "cp", "cogs",
            # Hindi / Hinglish
            "लागत", "खरीद मूल्य", "क्रय दर", "थोक मूल्य", "खर्च",
            "khareed ka daam", "cost kya", "lagai",
        ),
    ),
    SemanticField(
        label="revenue",
        description=(
            "The total amount for a whole invoice line — quantity multiplied "
            "by the unit price, i.e. the line total, net amount or taxable "
            "value. This is a LINE TOTAL, not a per-unit price."
        ),
        synonyms=(
            "amount", "amt", "net amount", "net_amount", "gross amount",
            "total", "total amount", "total_amount", "line total", "line_total",
            "line amount", "row total", "sale amount", "sales amount",
            "sales value", "invoice amount", "bill amount", "taxable value",
            "taxable amount", "revenue", "turnover", "value", "lineitem total",
            "item-total",
            # Hindi / Hinglish
            "राशि", "कुल राशि", "कुल रकम", "बिक्री राशि", "आय",
            "total kitne", "kitna paisa mila", "paisa",
        ),
    ),
    SemanticField(
        label="discount",
        description=(
            "A reduction given off the line — a discount amount, rebate or "
            "less-discount value, usually in rupees."
        ),
        synonyms=(
            "discount", "discount amount", "discount_amount", "disc", "disc amt",
            "rebate", "less discount", "lineitem discount", "concession",
            # Hindi / Hinglish
            "छूट", "रिहायत", "डिस्काउंट", "छोट", "bachat",
        ),
    ),
    SemanticField(
        label="tax",
        description=(
            "Government tax collected on the line — GST, CGST, SGST, IGST or "
            "VAT, reported separately and never counted as profit."
        ),
        synonyms=(
            "tax", "tax amount", "tax_amount", "gst", "gst amount", "gst_amount",
            "total gst", "cgst+sgst", "cgst", "sgst", "igst", "vat", "gstin",
            # Hindi / Hinglish
            "कर", "जीएसटी", "टैक्स", "ब्याज", "gst kitna",
        ),
    ),
    SemanticField(
        label="product",
        description=(
            "The name of the individual product, garment, style or article that "
            "was sold — the specific thing, not the group it belongs to."
        ),
        synonyms=(
            "item", "items", "item name", "item_name", "product", "product name",
            "product_name", "products", "description", "item description",
            "particulars", "stock item", "style", "style name", "style code",
            "design", "prod", "goods", "sku", "sku code", "item code",
            "product code", "barcode", "article", "title",
            # Hindi / Hinglish
            "उत्पाद", "वस्तु", "सामान", "चीज़", "आइटम", "नाम",
            "product naam", "item ka naam", "kya becha",
        ),
    ),
    SemanticField(
        label="category",
        description=(
            "The group or department a product belongs to — Kurta, Saree, "
            "Shirt, Grocery, Beverages. A classification of the product, not "
            "the product itself."
        ),
        synonyms=(
            "category", "categories", "cat", "product category", "item category",
            "item group", "stock group", "product type", "dept", "department",
            "type", "group", "segment", "class", "sub category", "sub-category",
            "subcategory", "collection", "section", "menu group", "course",
            "kitchen group", "food type",
            # Hindi / Hinglish
            "श्रेणी", "वर्ग", "समूह", "विभाग", "कटेगरी", "category kya",
        ),
    ),
    SemanticField(
        label="customer",
        description=(
            "The person or business the sale was made to — customer name, "
            "buyer, party, client. Personal data."
        ),
        synonyms=(
            "customer", "customer name", "customer_name", "buyer", "party",
            "party name", "client", "account", "account name", "consignee",
            "supplier", "vendor",
            # Hindi / Hinglish
            "ग्राहक", "कस्टमर", "खरीदार", "पार्टी", "ग्राहक का नाम",
            "customer kaun", "kiska maal",
        ),
    ),
    SemanticField(
        label="region",
        description=(
            "A geographical or organisational location the sale happened at — "
            "branch, store, shop, outlet, godown, warehouse, city."
        ),
        synonyms=(
            "branch", "store", "store name", "shop", "outlet", "location",
            "godown", "warehouse", "city", "region", "zone", "area", "territory",
            # Hindi / Hinglish
            "शाखा", "दुकान", "स्थान", "क्षेत्र", "इलाका", "फैक्ट्री",
            "branch kaun", "kitni dukan",
        ),
    ),
    SemanticField(
        label="status",
        description=(
            "The state of the order or transaction — pending, shipped, delivered, "
            "cancelled, returned, paid or unpaid."
        ),
        synonyms=(
            "status", "order status", "payment status", "state", "stage",
            "order state", "delivery status", "invoice status", "condition",
            # Hindi / Hinglish
            "स्थिति", "हालत", "स्टेटस", "status kya", "kya hua",
        ),
    ),
    SemanticField(
        label="notes",
        description=(
            "Free-text remarks written by staff about the transaction — "
            "delivery instructions, damage reports, supplier notes, anything "
            "typed in a remarks or observation box."
        ),
        synonyms=(
            "notes", "note", "remarks", "remark", "comment", "comments",
            "observation", "description note", "instructions", "memo",
            # Hindi / Hinglish
            "टिप्पणी", "नोट", "टिप्पणियाँ", "remarks kya", "koi baat",
        ),
    ),
    SemanticField(
        label="id",
        description=(
            "A unique reference number identifying a transaction or document — "
            "invoice number, bill number, voucher number, receipt number or "
            "order id."
        ),
        synonyms=(
            "id", "invoice no", "invoice_no", "invoice number", "invoice",
            "bill no", "bill_no", "bill number", "voucher no", "receipt no",
            "order id", "order_id", "order no", "txn id", "transaction id",
            "reference no", "ref no", "doc no", "sr no", "serial no",
            # Hindi / Hinglish
            "बिल संख्या", "चालान संख्या", "क्रमांक", "पर्ची संख्या",
        ),
    ),
    SemanticField(
        label="other",
        description=(
            "A column that matches none of the known business meanings — an "
            "unrecognised extra, a technical artefact, or free text we cannot "
            "place."
        ),
        synonyms=(
            "other", "misc", "miscellaneous", "na", "n/a", "unknown",
            "unnamed", "untitled", "column", "field",
        ),
    ),
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
    # Recognised, deliberately not analysed.
    "mrp": None,
    "status": None,
    "notes": None,
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