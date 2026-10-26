"""
Module 2.3 — Safe Mapping Memory Service.

Provides owner-scoped, SQLite-backed persistent memory of user-approved column
mappings across uploads for identical or re-ordered export templates.

Guarantees
----------
1. Owner Isolation: Stored in a per-owner database derived exclusively from
   server-verified credentials (hash of get_current_user identity).
2. Minimal Storage: Zero cell values, zero transaction data, zero display
   headers, and zero PII stored. Only (template_signature, normalized_header,
   canonical_field, confirmed_at).
3. Collision Immunity: Normalized headers that occur multiple times within the
   same template are excluded from both lookup and persistence, preventing
   overwrite or ambiguity bugs.
4. Concurrency Safety: SQLite WAL mode with busy_timeout=10000 and BEGIN IMMEDIATE
   transactions ensures concurrent writes do not produce lost updates.
5. Graceful Degradation: Any database or I/O failure degrades safely to an empty
   dict without raising HTTP 500 errors.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Iterator, Sequence

from app.core.config import MAPPING_MEMORY_DIR
from app.utils.data_validator import MAPPABLE_FIELDS, _is_pii_header

logger = logging.getLogger("senova.mapping_memory")

_INIT_LOCK = threading.Lock()
_INITIALIZED_DBS: set[str] = set()


def normalize_header(col: str) -> str:
    """
    Deterministic header normalization:
    - Strips leading UTF-8 byte order mark (BOM)
    - Lowercases text
    - Replaces underscores, hyphens, dots, and colons with spaces
    - Strips brackets, parentheses, quotes, and symbols like '#'
    - Collapses whitespace
    - Maps empty or pandas 'Unnamed' headers to '__empty__'
    """
    if col is None:
        return "__empty__"
    cleaned = str(col).lstrip("\ufeff").lower()
    cleaned = re.sub(r"[_\-\.:]+", " ", cleaned)
    cleaned = re.sub(r"[\[\]\(\)\"\'`#]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or re.match(r"^unnamed(?:\s+\d+)?$", cleaned):
        return "__empty__"
    return cleaned


def compute_template_signature(headers: Sequence[str]) -> str:
    """
    Computes a deterministic multiset SHA-256 signature for the template.
    Preserves multiplicity (does not set-deduplicate) and is column-order invariant.
    Uses canonical JSON list serialization to eliminate delimiter collisions.
    """
    normalized = sorted(normalize_header(h) for h in headers)
    serialized = json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def get_colliding_tokens(headers: Sequence[str]) -> set[str]:
    """
    Identifies normalized header tokens that occur more than once in the template.
    Mapping memory is disabled for any colliding token to prevent overwrite errors.
    """
    normalized = [normalize_header(h) for h in headers]
    counts = Counter(normalized)
    return {token for token, count in counts.items() if count > 1}


def _ensure_memory_dir() -> Path:
    path = Path(MAPPING_MEMORY_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_db_path(owner: str) -> Path:
    owner_hash = hashlib.sha256(owner.strip().lower().encode("utf-8")).hexdigest()
    return _ensure_memory_dir() / f"{owner_hash}.db"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS template_mappings (
            template_signature TEXT NOT NULL,
            normalized_header  TEXT NOT NULL,
            canonical_field    TEXT NOT NULL,
            confirmed_at       REAL NOT NULL,
            PRIMARY KEY (template_signature, normalized_header)
        );
        """
    )
    conn.commit()


def _ensure_db_initialized(db_path: Path) -> None:
    owner_key = str(db_path)
    if owner_key in _INITIALIZED_DBS and db_path.exists():
        return
    with _INIT_LOCK:
        if owner_key in _INITIALIZED_DBS and db_path.exists():
            return
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            _init_db(conn)
            _INITIALIZED_DBS.add(owner_key)
        finally:
            conn.close()


@contextmanager
def transaction(owner: str) -> Iterator[sqlite3.Connection]:
    """
    Owner-scoped transactional context manager.
    Enforces WAL mode, busy timeout, and immediate exclusive write locks
    with retries to guarantee zero lost updates during concurrent operations.
    """
    db_path = _get_db_path(owner)
    _ensure_db_initialized(db_path)

    for attempt in range(10):
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            conn.rollback()
            conn.close()
            if "locked" in str(exc).lower() and attempt < 9:
                time.sleep(0.02 * (attempt + 1))
            else:
                raise
        except Exception:
            conn.rollback()
            conn.close()
            raise
        else:
            conn.close()
            return


def load_template_mappings(
    owner: str,
    template_sig: str,
    colliding_tokens: set[str] | None = None,
) -> dict[str, str]:
    """
    Loads saved mappings for a template signature, filtering out colliding tokens
    and invalid canonical fields. Never raises: on any error returns {}.
    """
    if not owner or not template_sig:
        return {}

    colliding = colliding_tokens or set()
    db_path = _get_db_path(owner)
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            _init_db(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT normalized_header, canonical_field
                FROM template_mappings
                WHERE template_signature = ?
                """,
                (template_sig,),
            )
            rows = cursor.fetchall()
            valid_fields = set(MAPPABLE_FIELDS)
            mappings: dict[str, str] = {}
            for norm_hdr, canonical in rows:
                if norm_hdr not in colliding and canonical in valid_fields:
                    mappings[norm_hdr] = canonical
            return mappings
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to read mapping memory for owner: %s", exc)
        return {}


def record_confirmed_mappings(
    owner: str,
    raw_headers: Sequence[str],
    confirmed_mapping: dict[str, str],
    user_selected_columns: list[str],
    remember_mapping: bool,
    df: pd.DataFrame | None = None,
) -> None:
    """
    Records explicitly confirmed user mappings to safe mapping memory.
    - Only runs when remember_mapping is True.
    - Only processes columns in user_selected_columns.
    - Excludes PII headers and columns containing personal data in cell values.
    - Excludes tokens that collide (occur multiple times in the template).
    - If mapped to empty string "", deletes any prior remembered mapping for this token.
    - If mapped to valid canonical field, upserts into the template.
    Encompasses the entire operation in a single atomic transaction.
    """
    if not remember_mapping or not owner or not user_selected_columns:
        return

    from app.services.extra_columns import is_personal_pii

    template_sig = compute_template_signature(raw_headers)
    colliding = get_colliding_tokens(raw_headers)
    selected_set = set(user_selected_columns)
    valid_fields = set(MAPPABLE_FIELDS)

    try:
        with transaction(owner) as conn:
            now = time.time()
            for raw_col in raw_headers:
                if raw_col not in selected_set:
                    continue
                norm_col = normalize_header(raw_col)
                if norm_col in colliding or norm_col == "__empty__":
                    continue

                canonical = str(confirmed_mapping.get(raw_col, "")).strip()
                if canonical == "":
                    # Explicitly ignored / unmapped by user -> invalidate existing memory.
                    # This must always purge prior memory even if the column triggers PII detection.
                    conn.execute(
                        """
                        DELETE FROM template_mappings
                        WHERE template_signature = ? AND normalized_header = ?
                        """,
                        (template_sig, norm_col),
                    )
                elif canonical in valid_fields:
                    # Never save / update a mapping for a column identified as PII
                    if _is_pii_header(raw_col):
                        continue
                    if df is not None and raw_col in df.columns:
                        if is_personal_pii(raw_col, df[raw_col]):
                            continue

                    conn.execute(
                        """
                        INSERT INTO template_mappings (
                            template_signature, normalized_header, canonical_field, confirmed_at
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(template_signature, normalized_header)
                        DO UPDATE SET canonical_field=excluded.canonical_field, confirmed_at=excluded.confirmed_at
                        """,
                        (template_sig, norm_col, canonical, now),
                    )
    except Exception as exc:
        logger.warning("Failed to record mapping memory for owner: %s", exc)


def list_user_memories(owner: str) -> list[dict]:
    """
    Returns all remembered templates and their column mappings for the owner.
    """
    if not owner:
        return []
    db_path = _get_db_path(owner)
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            _init_db(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT template_signature, normalized_header, canonical_field, confirmed_at
                FROM template_mappings
                ORDER BY confirmed_at DESC
                """
            )
            rows = cursor.fetchall()
            templates_map: dict[str, dict] = {}
            for sig, norm_hdr, canonical, confirmed_at in rows:
                if sig not in templates_map:
                    templates_map[sig] = {
                        "template_signature": sig,
                        "updated_at": confirmed_at,
                        "mappings": {},
                    }
                templates_map[sig]["mappings"][norm_hdr] = canonical
                if confirmed_at > templates_map[sig]["updated_at"]:
                    templates_map[sig]["updated_at"] = confirmed_at
            return list(templates_map.values())
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Failed to list memories: %s", exc)
        return []


def delete_memory_entry(owner: str, template_sig: str, normalized_header: str) -> bool:
    """Deletes a single column mapping in a template."""
    if not owner or not template_sig or not normalized_header:
        return False
    try:
        with transaction(owner) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM template_mappings
                WHERE template_signature = ? AND normalized_header = ?
                """,
                (template_sig, normalized_header),
            )
            return cursor.rowcount > 0
    except Exception as exc:
        logger.warning("Failed to delete memory entry: %s", exc)
        return False


def delete_template_memory(owner: str, template_sig: str) -> bool:
    """Deletes all mappings for an entire template."""
    if not owner or not template_sig:
        return False
    try:
        with transaction(owner) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM template_mappings
                WHERE template_signature = ?
                """,
                (template_sig,),
            )
            return cursor.rowcount > 0
    except Exception as exc:
        logger.warning("Failed to delete template memory: %s", exc)
        return False


def clear_user_memory(owner: str) -> bool:
    """Clears all mapping memory for the owner."""
    if not owner:
        return False
    try:
        with transaction(owner) as conn:
            conn.execute("DELETE FROM template_mappings")
            return True
    except Exception as exc:
        logger.warning("Failed to clear user memory: %s", exc)
        return False
