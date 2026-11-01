"""
Phase 4.1 — cooldown for the explicit "Check again with AI" action.

Why this exists
----------------
``run_tier2`` already runs automatically once per upload. "Check again" is a
second, user-initiated chance at the *same* ambiguous columns, deliberately
bypassing the Gemini verdict cache (Phase 4.1 requirement 2) so a changed note
or a retried request actually reaches the model instead of replaying a stale
answer. Bypassing the cache removes the free rate-limit a cache hit gives for
nothing — a user mashing the button could otherwise fire a fresh Gemini
request every click. This module is the floor under that: at most one forced
recheck per (owner, file) every ``COOLDOWN_SECONDS``.

Why in-memory and not persisted
--------------------------------
A cooldown only needs to survive a few seconds, and this process is the only
thing serving the request anyway. Persisting it would mean a disk write on the
hot path of a button a user might click several times a minute, for a
guarantee that doesn't need to survive a restart — a restart clearing every
cooldown is a non-issue, since it only ever makes the next click succeed
slightly earlier than it otherwise would.

Thread/async safety
--------------------
FastAPI's default worker runs a single asyncio event loop per process; a
plain dict read-then-write here is not interrupted by another coroutine
unless this function itself awaits, and it never does. A multi-process
deployment (multiple uvicorn workers) would not share this dict, which is a
known, accepted limitation: it degrades to "a bit more permissive" per
worker, never to "no cooldown at all" within a worker, and never to
bypassing consent or the operator switch.
"""

from __future__ import annotations

import threading
import time

#: Minimum seconds between two forced rechecks for the same (owner, file_id).
COOLDOWN_SECONDS = 10.0

_lock = threading.Lock()
_last_recheck_at: dict[str, float] = {}


def _key(owner: str, file_id: str) -> str:
    return f"{owner}:{file_id}"


def seconds_remaining(owner: str, file_id: str, now: float | None = None) -> float:
    """
    How many seconds until another forced recheck is allowed, 0.0 if allowed now.

    Never negative; never raises on a missing/invalid owner or file_id — the
    caller treats "0.0 remaining" as "go ahead", so an unexpected key simply
    looks like a request that has never happened yet.
    """
    now = now if now is not None else time.monotonic()
    with _lock:
        last = _last_recheck_at.get(_key(owner, file_id))
    if last is None:
        return 0.0
    remaining = COOLDOWN_SECONDS - (now - last)
    return max(0.0, remaining)


def record_attempt(owner: str, file_id: str, now: float | None = None) -> None:
    """Mark this instant as the latest forced recheck for (owner, file_id)."""
    now = now if now is not None else time.monotonic()
    with _lock:
        _last_recheck_at[_key(owner, file_id)] = now


def reset(owner: str | None = None, file_id: str | None = None) -> None:
    """
    Test-only escape hatch. Clears one entry, or the whole tracker when no
    arguments are given, so tests never leak cooldown state into each other.
    """
    with _lock:
        if owner is None and file_id is None:
            _last_recheck_at.clear()
            return
        _last_recheck_at.pop(_key(owner or "", file_id or ""), None)
