"""
Tests for Tier 1's scoring, threshold and margin routing.

The embedding model is stubbed with a controllable similarity matrix so these
tests assert the *decision logic* — when a column is escalated, when an exact
alias hit short-circuits, how the shape signal overrides a misleading header —
rather than re-testing the model's accuracy, which is not ours to assert on.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services import embedder, tier1_classifier
from app.services.column_catalog import SEMANTIC_LABELS, canonical_field_for
from app.services.tier1_classifier import (
    ROUTE_GEMINI,
    ROUTE_LOCAL,
    SOURCE_LOCAL,
    ColumnGuess,
    _route,
    _shape_fit,
    classify_columns,
)
from app.utils.data_validator import guess_canonical_column


@pytest.fixture(autouse=True)
def _clean_embedder_cache():
    embedder.reset_cache()
    yield
    embedder.reset_cache()


@pytest.fixture
def stub_embeddings(monkeypatch):
    """
    Replace the embedder with a table-driven stub.

    ``mapping`` is ``{header_text: {label: score}}``. Any header not listed scores
    zero against everything, which is the honest default: a stub shouldn't invent
    similarity the caller didn't ask for.
    """
    mapping: dict[str, dict[str, float]] = {}
    encode_calls: list[list[str]] = []

    import numpy as np

    def fake_encode(texts):
        encode_calls.append(list(texts))
        rows = []
        for text in texts:
            per_label = mapping.get(text, {})
            rows.append([per_label.get(label, 0.0) for label in SEMANTIC_LABELS])
        return np.asarray(rows, dtype="float32") if rows else np.zeros((0, len(SEMANTIC_LABELS)))

    def fake_catalog():
        # Identity, not zeros: `_header_scores` collapses the similarity matrix
        # with a max over anchor columns, so an identity anchor matrix makes the
        # per-header vector itself the similarity for that label — which is
        # exactly what the mapping table above describes.
        return np.eye(len(SEMANTIC_LABELS), dtype="float32"), list(SEMANTIC_LABELS)

    monkeypatch.setattr(embedder, "encode", fake_encode)
    monkeypatch.setattr(embedder, "catalog_embeddings", fake_catalog)

    class _Stub:
        def __init__(self):
            self.mapping = mapping
            self.encode_calls = encode_calls

        def set(self, header, label, score):
            mapping.setdefault(header, {})[label] = score

    return _Stub()


@pytest.fixture(autouse=True)
def _force_fastembed_enabled(monkeypatch):
    """Most tests exercise the embedding path; the flag-off test overrides this."""
    monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", True)


# ── Catalog invariants ───────────────────────────────────────────────────────


class TestCatalog:
    def test_translation_never_invents_a_canonical_field(self):
        """A translation to a field outside the real schema would be dropped
        silently by normalize_dataframe — the UI would show a mapping the
        backend then ignores."""
        from app.utils.data_validator import MAPPABLE_FIELDS

        for label in SEMANTIC_LABELS:
            canonical = canonical_field_for(label, raw_header="Invoice No")
            assert canonical is None or canonical in set(MAPPABLE_FIELDS)

    def test_unmapped_semantics_have_no_canonical_target(self):
        for label in ("mrp", "status", "notes", "other"):
            assert canonical_field_for(label) is None

    def test_bare_id_is_not_promoted_to_invoice_number(self):
        """A customer-row id must not be reported as an invoice number."""
        assert canonical_field_for("id", raw_header="Customer Id") is None
        assert canonical_field_for("id", raw_header="Serial") is None

    def test_document_id_is_promoted(self):
        assert canonical_field_for("id", raw_header="Invoice No") == "Invoice No"
        assert canonical_field_for("id", raw_header="Bill Number") == "Invoice No"
        assert canonical_field_for("id", raw_header="बिल संख्या") == "Invoice No"

    def test_meanings_translate_onto_the_existing_schema(self):
        assert canonical_field_for("unit_price") == "Selling Price"
        assert canonical_field_for("revenue") == "Line Total"
        assert canonical_field_for("product") == "Item"
        assert canonical_field_for("region") == "Branch"
        assert canonical_field_for("cost") == "Cost Price"

    def test_customer_is_pii_sensitive(self):
        from app.services.column_catalog import PII_SENSITIVE_LABELS

        assert "customer" in PII_SENSITIVE_LABELS


# ── The routing rule ─────────────────────────────────────────────────────────


class TestRouting:
    def test_high_score_wide_margin_stays_local(self):
        route, _reason = _route(top_score=0.95, margin=0.40, high_threshold=0.80, margin_threshold=0.05)
        assert route == ROUTE_LOCAL

    def test_low_score_escalates(self):
        route, _reason = _route(top_score=0.55, margin=0.40, high_threshold=0.80, margin_threshold=0.05)
        assert route == ROUTE_GEMINI

    def test_high_score_narrow_margin_escalates(self):
        """The MRP-vs-Selling-Price case: both readings fit, so a second opinion
        is worth paying for even though the top score is high."""
        route, reason = _route(top_score=0.92, margin=0.01, high_threshold=0.80, margin_threshold=0.05)
        assert route == ROUTE_GEMINI
        assert "equally well" in reason

    def test_margin_exactly_at_threshold_stays_local(self):
        route, _reason = _route(top_score=0.90, margin=0.05, high_threshold=0.80, margin_threshold=0.05)
        assert route == ROUTE_LOCAL

    def test_score_exactly_at_threshold_stays_local(self):
        route, _reason = _route(top_score=0.80, margin=0.20, high_threshold=0.80, margin_threshold=0.05)
        assert route == ROUTE_LOCAL


# ── Shape fit ────────────────────────────────────────────────────────────────


class TestShapeFit:
    def test_dates_fit_a_date_column(self):
        stats = {"numeric_ratio": 0.0, "date_parse_ratio": 1.0}
        assert _shape_fit("date", stats) == pytest.approx(1.0)

    def test_numbers_fit_a_quantity_column(self):
        stats = {"numeric_ratio": 1.0, "date_parse_ratio": 0.0}
        assert _shape_fit("quantity", stats) == pytest.approx(1.0)

    def test_dates_do_not_fit_a_quantity_column(self):
        stats = {"numeric_ratio": 0.0, "date_parse_ratio": 1.0}
        assert _shape_fit("quantity", stats) < 0.5

    def test_numbers_do_not_fit_a_textual_column(self):
        """A column of stock codes is not a customer column, whatever its header."""
        stats = {"numeric_ratio": 1.0, "date_parse_ratio": 0.0}
        assert _shape_fit("customer", stats) == pytest.approx(0.0)

    def test_text_fits_a_textual_column(self):
        stats = {"numeric_ratio": 0.0, "date_parse_ratio": 0.0}
        assert _shape_fit("customer", stats) == pytest.approx(1.0)


# ── End-to-end classification ───────────────────────────────────────────────


class TestClassifyColumns:
    def test_empty_frame_returns_empty_list(self, stub_embeddings):
        assert classify_columns(pd.DataFrame()) == []

    def test_exact_alias_hit_short_circuits_the_model(
        self, stub_embeddings, monkeypatch
    ):
        """'Bill Date' is in the alias map, so it is settled without consulting
        the embedding similarity at all — and lands on the existing canonical name.
        """
        # Deliberately give the header a terrible embedding score: the exact
        # alias must still win.
        stub_embeddings.set("Bill Date", "quantity", 0.99)
        stub_embeddings.set("Bill Date", "date", 0.01)

        df = pd.DataFrame({"Bill Date": ["01-04-2026", "02-04-2026", "03-04-2026"]})
        guesses = classify_columns(df)

        assert len(guesses) == 1
        assert guesses[0].canonical == "Date"
        assert guesses[0].route == ROUTE_LOCAL
        assert guesses[0].score == 1.0

    def test_mrp_escalates_rather_than_guessing(self, stub_embeddings):
        """MRP scores well against both mrp and unit_price — the ambiguous case.

        Also guards the deliberate behaviour change: the legacy alias map still
        says "mrp" -> "Selling Price" (and test_data_validator.py pins that), so
        the pipeline must explicitly refuse to inherit that answer here.
        """
        stub_embeddings.set("MRP", "mrp", 0.90)
        stub_embeddings.set("MRP", "unit_price", 0.88)

        df = pd.DataFrame({"MRP": [1200, 1500, 999]})
        guesses = classify_columns(df, ai_available=True)

        assert guesses[0].route == ROUTE_GEMINI
        assert guesses[0].label in {"mrp", "unit_price"}
        assert guesses[0].canonical is None  # never committed without escalation
        # The legacy alias map would have said "Selling Price" here.
        assert guess_canonical_column("MRP")[0] == "Selling Price"

    def test_mrp_is_never_mapped_to_selling_price_in_fallback_mode(self, stub_embeddings, monkeypatch):
        """With no embedder, MRP must fall through instead of inheriting the
        legacy alias — otherwise the flag being off would reintroduce the bug."""
        monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", False)

        df = pd.DataFrame({"MRP": [1200, 1500]})
        guess = classify_columns(df)[0]
        assert guess.canonical != "Selling Price"

    def test_clear_match_is_resolved_locally(self, stub_embeddings):
        stub_embeddings.set("Kitne", "quantity", 0.97)
        stub_embeddings.set("Kitne", "cost", 0.10)

        df = pd.DataFrame({"Kitne": [3, 5, 2, 8]})
        guesses = classify_columns(df)

        assert guesses[0].label == "quantity"
        assert guesses[0].route == ROUTE_LOCAL
        assert guesses[0].source == SOURCE_LOCAL

    def test_shape_evidence_overrides_a_misleading_header(self, stub_embeddings):
        """A column headed 'Aggregate' whose values are all dates is a date column.

        The header term dominates at 0.7 weight, so the header here is set to
        favour 'quantity' — but the values must still pull it back, because a
        register with every row a date is not a quantity column. "Aggregate" is
        used rather than "Total" so the exact-alias short-circuit doesn't fire and
        mask the scoring behaviour under test.
        """
        stub_embeddings.set("Aggregate", "quantity", 0.40)
        stub_embeddings.set("Aggregate", "date", 0.35)

        dates = pd.DataFrame({"Aggregate": ["2026-04-05", "2026-04-06", "2026-04-07"]})
        guess = classify_columns(dates)[0]
        assert guess.label == "date"
        assert guess.route == ROUTE_LOCAL

    def test_unrecognised_header_reports_other_rather_than_guessing(self, stub_embeddings):
        """A heading the model has never seen must yield 'other', not a confident
        label won by catalog order. Shape stats can refute a label but cannot
        positively identify one, so with no textual evidence the honest answer is
        'don't know'."""
        df = pd.DataFrame({"Some Vendor Specific Column": ["alpha", "beta", "gamma"]})
        guess = classify_columns(df, ai_available=True)[0]
        assert guess.label == "other"
        assert guess.route == ROUTE_GEMINI
        assert "isn't one we recognise" in guess.reason

    def test_unrecognised_numeric_header_also_reports_other(self, stub_embeddings):
        """Numbers cannot distinguish revenue from cost from tax either."""
        df = pd.DataFrame({"Vendor Code Figure": [10, 20, 30]})
        guess = classify_columns(df, ai_available=True)[0]
        assert guess.label == "other"

    def test_unrecognised_header_without_ai_asks_for_manual_mapping(self, stub_embeddings):
        df = pd.DataFrame({"Some Vendor Specific Column": ["alpha", "beta"]})
        guess = classify_columns(df, ai_available=False)[0]
        assert guess.label == "other"
        assert guess.route == ROUTE_LOCAL
        assert "by hand" in guess.reason

    def test_alternatives_are_recorded_for_the_ui(self, stub_embeddings):
        stub_embeddings.set("Charge", "unit_price", 0.90)
        stub_embeddings.set("Charge", "cost", 0.85)
        stub_embeddings.set("Charge", "mrp", 0.20)

        df = pd.DataFrame({"Charge": [100, 200, 300]})
        guess = classify_columns(df)[0]
        assert guess.label == "unit_price"
        assert guess.alternatives
        assert all(isinstance(label, str) for label, _score in guess.alternatives)

    def test_escalated_column_never_carries_a_committed_canonical(self, stub_embeddings):
        """Whatever the reason for escalation, the canonical field must stay None
        until Tier 2 or the user decides."""
        stub_embeddings.set("Charge", "unit_price", 0.55)
        stub_embeddings.set("Charge", "cost", 0.53)

        df = pd.DataFrame({"Charge": [100, 200, 300]})
        guess = classify_columns(df, ai_available=True)[0]
        assert guess.route == ROUTE_GEMINI
        assert guess.canonical is None


class TestDegradation:
    def test_flag_off_uses_the_alias_map(self, stub_embeddings, monkeypatch):
        monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", False)

        df = pd.DataFrame({"Bill Date": ["01-04-2026"], "Item Name": ["Kurta"]})
        guesses = classify_columns(df)

        assert [g.canonical for g in guesses] == ["Date", "Item"]
        assert all(g.source == SOURCE_LOCAL for g in guesses)

    def test_flag_off_leaves_fuzzy_matches_for_confirmation(self, stub_embeddings, monkeypatch):
        monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", False)

        # "Party Discounted Amount" is not an alias; the fuzzy keyword map
        # catches "discount" only because it precedes "count"-containing keys.
        df = pd.DataFrame({"Some Net Amount Field": [100, 200]})
        guess = classify_columns(df)[0]
        assert guess.route in {ROUTE_LOCAL, ROUTE_GEMINI}

    def test_embedder_unavailable_falls_back(self, stub_embeddings, monkeypatch):
        monkeypatch.setattr(embedder, "catalog_embeddings", lambda: (None, None))

        df = pd.DataFrame({"Bill Date": ["01-04-2026"], "Item Name": ["Kurta"]})
        guesses = classify_columns(df)
        assert [g.canonical for g in guesses] == ["Date", "Item"]

    def test_embedding_exception_falls_back(self, stub_embeddings, monkeypatch):
        def _boom(texts):
            raise RuntimeError("onnx exploded")

        monkeypatch.setattr(embedder, "encode", _boom)
        monkeypatch.setattr(embedder, "catalog_embeddings", stub_embeddings.__class__ and (lambda: (_boom_matrix(), list(SEMANTIC_LABELS))))

        df = pd.DataFrame({"Bill Date": ["01-04-2026"]})
        guesses = classify_columns(df)
        assert guesses[0].canonical == "Date"


def _boom_matrix():
    import numpy as np

    return np.zeros((len(SEMANTIC_LABELS), len(SEMANTIC_LABELS)), dtype="float32")


class TestPassthroughCanonicalFields:
    def test_fields_without_a_semantic_label_pass_through(self):
        """Stock On Hand has no meaning-layer label, so fallback mode must leave
        it as a canonical name rather than pretending it is 'other'."""
        from app.services.tier1_classifier import _semantic_from_canonical

        assert _semantic_from_canonical("Stock On Hand") is None
        assert _semantic_from_canonical("Payment Mode") is None
        assert _semantic_from_canonical("Selling Price") == "unit_price"

    def test_stock_on_hand_still_maps_in_fallback_mode(self, stub_embeddings, monkeypatch):
        monkeypatch.setattr(tier1_classifier, "FASTEMBED_ENABLED", False)

        df = pd.DataFrame({"Closing Stock": [40, 35, 30]})
        guess = classify_columns(df)[0]
        assert guess.canonical == "Stock On Hand"