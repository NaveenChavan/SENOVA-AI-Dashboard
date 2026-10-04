"""
Tier 1's local embedding model — loaded lazily, embedded once, never per request.

Why the singleton
-----------------
Loading a FastEmbed model means reading a ~0.5 GB ONNX file off disk and
initialising an onnxruntime session. Doing that per upload would add seconds to
every request on a memory-starved host. So the model is created on first use and
kept for the process lifetime, and — the part that actually matters — the
**catalog anchors are embedded exactly once**, not once per request and not once
per column. The catalog is static; re-embedding 300-odd anchor texts for every
uploaded file would be pure waste.

Why it is lazy rather than eager
--------------------------------
An import-time ``TextEmbedding(...)`` would download the model during ``pytest``
collection and during every CLI/import of the app, including the many code paths
that never classify a column. Lazy loading means the ~0.5 GB cost is only paid
by a process that actually classifies something, and it is paid in the background
of the first real upload rather than at boot.

Degradation, not failure
------------------------
Every entry point here catches its own errors and returns ``None`` instead of
raising. A missing ``fastembed`` install, an offline machine with no cached
model, a bad model name — all of them mean "Tier 1 can't run", and the right
response is for ``tier1_classifier`` to fall back to the existing alias map. A
classifier that raises would take the upload endpoint down with it.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from app.core.config import FASTEMBED_CACHE_PATH, FASTEMBED_MODEL
from app.services.column_catalog import catalog_anchors

logger = logging.getLogger("senova.tier1")

#: Guards both the model construction and the catalog embedding. FastAPI runs
#: sync handlers in a thread pool, so two uploads really can reach this at once
#: and loading the model twice would double the memory peak on exactly the host
#: that cannot afford it.
_lock = threading.Lock()

#: The FastEmbed model instance, or ``None`` if loading failed / was disabled.
_model = None
#: ``True`` once a load has been *attempted*, so a failure isn't retried on every
#: single upload (each attempt would re-hit the filesystem and, offline, the
#: network timeout).
_model_attempted = False

#: Cached anchor embedding matrix, shape ``(n_anchors, dim)``.
_anchor_matrix: np.ndarray | None = None
#: Anchor labels, parallel to ``_anchor_matrix`` rows.
_anchor_labels: list[str] | None = None


def reset_cache() -> None:
    """
    Drop the model and the cached catalog embeddings.

    Test-only. The production lifetime of both is the process; this exists so a
    test that swaps ``FASTEMBED_MODEL`` or fakes a load failure isn't poisoned by
    whatever a previous test left behind.
    """
    global _model, _model_attempted, _anchor_matrix, _anchor_labels
    with _lock:
        _model = None
        _model_attempted = False
        _anchor_matrix = None
        _anchor_labels = None


def _load_model():
    """Construct the FastEmbed model once. Returns ``None`` on any failure."""
    global _model, _model_attempted

    if _model_attempted:
        return _model

    with _lock:
        if _model_attempted:
            return _model
        _model_attempted = True
        try:
            from fastembed import TextEmbedding

            _model = TextEmbedding(
                model_name=FASTEMBED_MODEL,
                cache_dir=FASTEMBED_CACHE_PATH,
                # Single-threaded: Tier 1 handles one upload's worth of headers
                # at a time, and letting onnxruntime spread across every core
                # makes the per-request latency far less predictable on a
                # shared host.
                threads=1,
            )
            logger.info("Tier 1 embedder loaded: %s", FASTEMBED_MODEL)
        except Exception as exc:
            # Logged once, without a traceback: an absent optional dependency is
            # a configuration state, not a crash.
            logger.warning(
                "Tier 1 embedder unavailable (%s: %s). Falling back to the "
                "alias map — column detection still works, just with the older "
                "heuristic.",
                type(exc).__name__,
                exc,
            )
            _model = None
    return _model


def encode(texts: list[str]) -> np.ndarray | None:
    """
    Embed ``texts`` into unit-length vectors, or return ``None`` if Tier 1 can't run.

    Returning ``None`` rather than raising is deliberate: every caller has a
    working fallback, and a raised exception here would surface as a 500 on an
    upload of a perfectly good file.
    """
    if not texts:
        return np.zeros((0, 0), dtype="float32")

    model = _load_model()
    if model is None:
        return None

    try:
        vectors = np.asarray(list(model.embed(texts)), dtype="float32")
    except Exception as exc:
        logger.warning("Tier 1 embedding failed (%s: %s).", type(exc).__name__, exc)
        return None

    return _normalize(vectors)


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """
    Scale each row to unit length so a dot product is cosine similarity.

    Zero rows are left as zeros rather than divided by zero. They arise from an
    empty or whitespace-only header, and scoring them as distance 0 from every
    label is the safe outcome — it reads as "no information", not "perfect
    match".
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe = np.where(norms == 0.0, 1.0, norms)
    return (vectors / safe).astype("float32")


def catalog_embeddings() -> tuple[np.ndarray | None, list[str] | None]:
    """
    The embedded catalog anchors, embedded on first call and cached thereafter.

    Returns ``(matrix, labels)`` where ``labels[i]`` is the semantic label that
    ``matrix[i]`` represents, or ``(None, None)`` when Tier 1 can't run.

    Caching is the point. ``catalog_anchors()`` yields several hundred texts
    (16 labels × a description plus all synonyms) and the model is a ~0.5 GB
    onnxruntime session — encoding them once per upload would dominate the
    request and pin CPU for seconds. ``test_embedder.py`` asserts the encoder is
    invoked exactly once regardless of how many columns are classified.
    """
    global _anchor_matrix, _anchor_labels

    if _anchor_matrix is not None:
        return _anchor_matrix, _anchor_labels

    with _lock:
        if _anchor_matrix is not None:
            return _anchor_matrix, _anchor_labels

        pairs = catalog_anchors()
        matrix = encode([text for _label, text in pairs])
        if matrix is None:
            return None, None

        _anchor_matrix = matrix
        _anchor_labels = [label for label, _text in pairs]
        logger.info(
            "Tier 1 catalog embedded: %d anchors across %d labels.",
            matrix.shape[0],
            len({label for label, _ in pairs}),
        )
        return _anchor_matrix, _anchor_labels


def is_available() -> bool:
    """True when Tier 1's embedding path can actually run."""
    return _load_model() is not None