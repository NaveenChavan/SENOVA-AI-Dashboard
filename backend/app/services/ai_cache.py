"""
Disk cache for Tier 2 (Gemini) results, stored as a per-upload sidecar.

Why a sidecar and not Firestore
-------------------------------
``firebase-admin`` in this project is used *only* to verify ID tokens — there is
no database write path anywhere. Adding one would mean a new set of security
rules, a new per-user path scheme, and a billing dependency (Firestore is not
available on the free Spark plan). So the cache lives on disk, right beside the
``.mapping.json`` and ``.meta.json`` sidecars that already exist, and is swept by
the same TTL sweep.

Who can read it
---------------
Same rule as every other artefact here: the cache is bound to a ``file_id`` that
is only reachable by the uploader, who is re-checked via ``assert_owner`` before
the pipeline touches the file at all. The cache stores **column metadata and
model verdicts only** — never a raw cell value, since everything that reached it
was already through ``pii_mask`` on the way in.

What the key covers
-------------------
A hash of the column names plus *what was actually sent* — the masked samples,
or the stats-only marker for a column whose values were suppressed. Read and
write must build the key the same way, or a suppressed column would miss the
cache on every single upload, which is the exact waste this is meant to avoid.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from app.services.file_handler import _aicache_path, validate_file_id

logger = logging.getLogger("senova.tier2")

#: Bumped if the stored payload's shape ever changes, so an old cache file is
#: ignored rather than misread.
CACHE_VERSION = 1

#: Cap on entries kept per file. A 100-column file can't legitimately produce
#: more than 100 entries, so this only exists to bound a hand-edited or
#: corrupted sidecar.
MAX_ENTRIES = 256

#: Marker written in place of samples for a column whose values were suppressed.
#: Hashing the marker (rather than the absence of samples) keeps the key stable
#: whether or not the column had samples to begin with.
SUPPRESSED_MARKER = "<suppressed>"


def build_key(columns: list[dict]) -> str:
    """
    Stable cache key for a batch of ambiguous columns.

    ``columns`` is a list of ``{name, samples, suppressed}`` dicts. Only the
    normalised name and the already-masked samples (or the suppression marker)
    contribute, so re-uploading the same structure with different row *counts* or
    different data still hits the cache — which is the whole point, since the
    verdict depends on the shape of the schema, not on the transactions in it.
    """
    parts = []
    for column in columns:
        samples = column.get("samples") or []
        parts.append(
            {
                "name": str(column.get("name", "")).strip().lower(),
                "suppressed": bool(column.get("suppressed", False)),
                "samples": list(samples) if not column.get("suppressed", False) else SUPPRESSED_MARKER,
            }
        )
    # Sort by name so column order in the sheet doesn't change the key.
    parts.sort(key=lambda part: part["name"])

    payload = json.dumps({"v": CACHE_VERSION, "columns": parts}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load(file_id: str, key: str) -> dict[str, dict]:
    """
    Return cached verdicts for ``key``, or ``{}`` on any problem.

    A missing, unreadable, malformed or version-mismatched cache is not an error
    — it just means we pay for one Gemini call. Never raises.
    """
    path = _aicache_path(file_id)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Discarding unreadable AI cache for %s (%s).", file_id, type(exc).__name__)
        return {}

    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return {}

    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}

    cached = entries.get(key)
    if not isinstance(cached, dict):
        return {}

    return {
        str(name): verdict
        for name, verdict in cached.items()
        if isinstance(verdict, dict)
    }


def save(file_id: str, key: str, verdicts: dict[str, dict]) -> None:
    """
    Persist verdicts for ``key``, merging into any existing entries.

    Best-effort: a cache write that fails (disk full, read-only mount) must not
    fail the upload, so every exception is swallowed after one log line. The
    upload already succeeded by this point and re-running Tier 2 next time is
    merely a small waste, not a broken feature.
    """
    if not verdicts:
        return

    path = _aicache_path(file_id)

    entries: dict[str, dict] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and existing.get("version") == CACHE_VERSION:
                stored = existing.get("entries")
                if isinstance(stored, dict):
                    entries = stored
        except (json.JSONDecodeError, OSError):
            entries = {}

    entries[key] = verdicts

    # Bound the sidecar. Oldest keys are dropped first because a re-upload's
    # earlier attempts are the least likely to be hit again.
    if len(entries) > MAX_ENTRIES:
        entries = dict(list(entries.items())[-MAX_ENTRIES:])

    payload = {"version": CACHE_VERSION, "updated_at": time.time(), "entries": entries}

    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write AI cache for %s (%s).", file_id, exc)


def invalidate(file_id: str) -> None:
    """Remove the cache sidecar. Called from the same places as ``cleanup``."""
    try:
        path = _aicache_path(file_id)
    except ValueError:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass