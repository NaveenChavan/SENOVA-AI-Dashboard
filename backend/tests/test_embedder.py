"""
Tests for the lazy Tier 1 embedder.

The real ONNX model is never loaded here: it is a ~0.5 GB download and the
point of these tests is the caching and degradation contract, not the model's
accuracy. ``encode`` is monkeypatched with a deterministic stand-in so we can
assert *how many times* encoding happened — which is the property that actually
costs money at request time.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services import embedder


@pytest.fixture(autouse=True)
def _clean_embedder_cache():
    """Each test starts from a cold singleton."""
    embedder.reset_cache()
    yield
    embedder.reset_cache()


class _FakeModel:
    """Deterministic stand-in for a FastEmbed model.

    Maps a text to a vector by a stable hash so the same text always produces
    the same vector — enough to prove caching without asserting on semantics.
    """

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        out = []
        for text in batch:
            seed = sum(ord(ch) for ch in str(text)) % 997
            rng = np.random.default_rng(seed)
            out.append(rng.standard_normal(8))
        return out


@pytest.fixture
def fake_model(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(embedder, "_load_model", lambda: model)
    return model


class TestEncode:
    def test_returns_unit_length_rows(self, fake_model):
        vectors = embedder.encode(["Bill Date", "Qty."])
        assert vectors.shape == (2, 8)
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)

    def test_empty_input_returns_empty_matrix(self, fake_model):
        vectors = embedder.encode([])
        assert vectors.shape == (0, 0)

    def test_same_text_produces_same_vector(self, fake_model):
        a = embedder.encode(["Qty."])[0]
        b = embedder.encode(["Qty."])[0]
        assert np.allclose(a, b)

    def test_returns_none_when_model_unavailable(self, monkeypatch):
        monkeypatch.setattr(embedder, "_load_model", lambda: None)
        assert embedder.encode(["Qty."]) is None

    def test_model_load_failure_is_swallowed(self, monkeypatch):
        """A broken model must never propagate into the upload route."""
        monkeypatch.setattr(embedder, "_load_model", lambda: None)
        embedder._model_attempted = False
        embedder._model = None

        # Exercise the real loader with fastembed made unimportable.
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "fastembed":
                raise ImportError("fastembed is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert embedder._load_model() is None
        assert embedder.is_available() is False

    def test_load_failure_is_attempted_only_once(self, monkeypatch):
        """A failed load must not re-hit the filesystem on every upload."""
        import builtins

        attempts = []
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "fastembed":
                attempts.append(name)
                raise ImportError("no fastembed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert embedder._load_model() is None
        assert embedder._load_model() is None
        assert embedder._load_model() is None
        assert len(attempts) == 1


class TestCatalogEmbeddings:
    def test_catalog_is_embedded_once_and_reused(self, fake_model):
        first_matrix, first_labels = embedder.catalog_embeddings()
        calls_after_first = len(fake_model.calls)

        second_matrix, second_labels = embedder.catalog_embeddings()

        assert second_matrix is first_matrix
        assert second_labels is first_labels
        # The whole point: N calls to catalog_embeddings(), one encode().
        assert len(fake_model.calls) == calls_after_first == 1

    def test_matrix_and_labels_are_aligned(self, fake_model):
        matrix, labels = embedder.catalog_embeddings()
        assert matrix is not None and labels is not None
        assert matrix.shape[0] == len(labels)

    def test_every_semantic_label_is_represented(self, fake_model):
        from app.services.column_catalog import SEMANTIC_LABELS

        _matrix, labels = embedder.catalog_embeddings()
        assert set(SEMANTIC_LABELS).issubset(set(labels))

    def test_returns_none_when_model_unavailable(self, monkeypatch):
        monkeypatch.setattr(embedder, "_load_model", lambda: None)
        assert embedder.catalog_embeddings() == (None, None)

    def test_includes_hindi_and_hinglish_anchors(self, fake_model):
        """Hindi coverage is the reason the multilingual model is the default."""
        from app.services.column_catalog import catalog_anchors

        texts = [text for _label, text in catalog_anchors()]
        assert any("तारीख" in text for text in texts)
        assert any("कितने" in text for text in texts)


class TestNormalize:
    def test_zero_rows_stay_zero(self):
        vectors = np.array([[3.0, 4.0], [0.0, 0.0]], dtype="float32")
        normalized = embedder._normalize(vectors)
        assert np.allclose(normalized[0], [0.6, 0.8])
        # A zero row must not become NaN — it would poison every comparison.
        assert np.allclose(normalized[1], [0.0, 0.0])
        assert not np.isnan(normalized).any()