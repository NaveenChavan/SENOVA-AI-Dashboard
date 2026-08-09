"""
Frame-cache concurrency behaviour.

The property that matters here isn't just "results are cached" — it's that
several requests arriving at once for the *same* file cause exactly **one**
parse, while requests for *different* files are still free to parse in
parallel.

This is what makes a cold dashboard load survive: opening it fires five
analytics requests simultaneously, and before the per-key parse lock existed
all five re-parsed the same 30k-row Excel and contended for CPU, blowing past
the frontend's request timeout.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pandas as pd

from app.services import frame_cache


def _tiny_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": ["01-01-2026", "02-01-2026"],
            "Category": ["Kurta", "Kurta"],
            "Item": ["Cotton Kurta", "Cotton Kurta"],
            "Quantity": [2, 3],
            "Selling Price": [750.0, 750.0],
            "Cost Price": [300.0, 300.0],
        }
    )


MAPPING = {
    "Date": "Date",
    "Category": "Category",
    "Item": "Item",
    "Quantity": "Quantity",
    "Selling Price": "Selling Price",
    "Cost Price": "Cost Price",
}


def test_concurrent_requests_for_one_file_parse_it_only_once():
    frame_cache.clear()
    parse_count = 0
    parse_lock = threading.Lock()

    def slow_read(_file_id):
        nonlocal parse_count
        with parse_lock:
            parse_count += 1
        # Long enough that every thread is definitely inside the window a
        # stampede would exploit.
        time.sleep(0.4)
        return _tiny_frame()

    with patch.object(frame_cache, "read_to_dataframe", side_effect=slow_read):
        with patch.object(frame_cache, "get_file_mtime", return_value=12345.0):
            results = []
            errors = []

            def worker():
                try:
                    df, _ = frame_cache.get_normalized_frame("f" * 32, MAPPING)
                    results.append(len(df))
                except Exception as exc:  # pragma: no cover - surfaced below
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

    assert not errors, f"worker(s) raised: {errors}"
    # Every caller got real data...
    assert len(results) == 6
    assert all(count == 2 for count in results)
    # ...but the expensive parse happened exactly once.
    assert parse_count == 1


def test_different_files_are_not_serialised_behind_each_other():
    """
    Two different files must be able to parse concurrently — the per-key lock
    exists to de-duplicate one key, not to funnel all traffic through a single
    global parse lock.
    """
    frame_cache.clear()
    concurrent_now = 0
    peak_concurrent = 0
    counter_lock = threading.Lock()

    def slow_read(_file_id):
        nonlocal concurrent_now, peak_concurrent
        with counter_lock:
            concurrent_now += 1
            peak_concurrent = max(peak_concurrent, concurrent_now)
        time.sleep(0.4)
        with counter_lock:
            concurrent_now -= 1
        return _tiny_frame()

    def mtime_for(file_id):
        return float(abs(hash(file_id)) % 10_000)

    with patch.object(frame_cache, "read_to_dataframe", side_effect=slow_read):
        with patch.object(frame_cache, "get_file_mtime", side_effect=mtime_for):
            threads = [
                threading.Thread(target=frame_cache.get_normalized_frame, args=(fid, MAPPING))
                for fid in ("a" * 32, "b" * 32, "c" * 32)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

    assert peak_concurrent > 1, (
        "different files were parsed one-at-a-time; the per-key lock is "
        "behaving like a global lock"
    )


def test_key_lock_registry_stays_bounded():
    frame_cache.clear()

    with patch.object(frame_cache, "read_to_dataframe", return_value=_tiny_frame()):
        for i in range(frame_cache.MAX_KEY_LOCKS + 20):
            with patch.object(frame_cache, "get_file_mtime", return_value=float(i)):
                frame_cache.get_normalized_frame(f"{i:032x}", MAPPING)

    assert len(frame_cache._key_locks) <= frame_cache.MAX_KEY_LOCKS
