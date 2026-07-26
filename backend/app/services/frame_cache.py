"""
Bounded in-memory cache of *normalised* DataFrames.

Why
---
Every dashboard interaction (switch a filter, open a tab, change a chart
dimension, page the ledger) re-reads the same uploaded file. Parsing a
50 000-row Excel export and re-running the whole validation pipeline on each
of those calls is both slow and a cheap way for one signed-in user to burn
all the server's CPU. Caching the parsed result makes the second and later
requests near-instant.

Security / memory notes
-----------------------
An unbounded cache is itself a denial-of-service vector, so this one is
deliberately small and self-limiting:

* at most ``MAX_ENTRIES`` frames are kept, evicted least-recently-used first;
* frames larger than ``MAX_CACHED_ROWS`` are never cached (they are still
  served, just re-parsed each time — slow beats out-of-memory);
* the key includes the file's mtime **and** a signature of the column
  mapping, so a re-uploaded file or a corrected mapping can never be served
  from a stale entry;
* entries hold only already-validated data, never raw request input.

Cached frames disappear on process restart, and the upload TTL sweep
(``file_handler.sweep_expired_uploads``) removes the underlying files, so
nothing accumulates indefinitely.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict

import pandas as pd

from app.services.file_handler import get_file_mtime, read_to_dataframe
from app.utils.data_validator import normalize_dataframe

#: Maximum number of normalised frames held at once (small on purpose).
MAX_ENTRIES = 8

#: Frames with more rows than this are served but not cached.
MAX_CACHED_ROWS = 300_000

# OrderedDict gives us LRU semantics: move_to_end on hit, popitem(last=False)
# to evict. The lock matters because FastAPI runs sync route handlers in a
# thread pool, so two requests really can touch this dict at the same time.
_cache: "OrderedDict[tuple, tuple[pd.DataFrame, list[dict]]]" = OrderedDict()
_lock = threading.Lock()


def _mapping_signature(mapping: dict[str, str] | None) -> str:
    """Stable string form of a column mapping, used as part of the cache key."""
    if not mapping:
        return "auto"
    return json.dumps(mapping, sort_keys=True)


def get_normalized_frame(
    file_id: str,
    mapping: dict[str, str] | None,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Return ``(valid_rows_df, row_errors)`` for an uploaded file, from cache
    when possible.

    The returned DataFrame is a **copy**, so callers can add derived columns
    or filter it in place without corrupting the cached original.

    Raises the same exceptions as the underlying reader/validator
    (``FileNotFoundError``, ``ValueError``) so route handlers keep their
    existing error translation.
    """
    key = (file_id, get_file_mtime(file_id), _mapping_signature(mapping))

    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit[0].copy(), list(hit[1])

    # Parse outside the lock: this is the slow part, and holding the lock
    # through it would serialise every request for every file.
    raw_df = read_to_dataframe(file_id)
    valid_df, errors = normalize_dataframe(raw_df, column_mapping=mapping)

    if len(valid_df) <= MAX_CACHED_ROWS:
        with _lock:
            _cache[key] = (valid_df.copy(), list(errors))
            _cache.move_to_end(key)
            while len(_cache) > MAX_ENTRIES:
                _cache.popitem(last=False)

    return valid_df, errors


def invalidate(file_id: str) -> None:
    """
    Drop every cached entry for one file — called when its mapping is
    re-confirmed or the file is deleted, so the next read re-parses.
    """
    with _lock:
        for key in [k for k in _cache if k[0] == file_id]:
            del _cache[key]


def clear() -> None:
    """Empty the whole cache (used by tests)."""
    with _lock:
        _cache.clear()
