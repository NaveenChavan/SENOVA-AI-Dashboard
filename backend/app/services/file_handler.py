"""
Handles file I/O — saving uploads to disk, binding them to their owner, and
reading them back into Pandas.

Swap this module when moving from local files to object storage / database
without touching the calculation or route layers.

On-disk layout
--------------
For one upload with id ``ab12…`` three files may exist in ``UPLOAD_DIR``::

    ab12….csv               the raw uploaded bytes
    ab12….mapping.json      the user-confirmed {raw_column: canonical_field} map
    ab12….meta.json         owner + original filename + upload timestamp

Ownership (security)
--------------------
``file_id`` is an unguessable UUID4 hex, but "unguessable" is not
"authorised": any signed-in user who obtained someone else's id could
otherwise read that shop's entire sales ledger and download their P&L.
So the uploader's identity is written to the ``.meta.json`` sidecar at
upload time and ``assert_owner()`` is called on **every** later read. A
mismatch (or a missing sidecar) raises ``PermissionError``, which the route
layer converts to a 404 — deliberately not a 403, so the response never
confirms that some other user's file exists.

Cleanup strategy
----------------
Files are NOT deleted right after the first successful ``/process`` or
``/analytics`` call, because the dashboard re-fetches the same ``file_id``
whenever the user changes a filter (see ``Dashboard.jsx``). Instead a TTL
sweep (``sweep_expired_uploads``) removes any file older than
``UPLOAD_TTL_MINUTES``. The sweep runs once at app startup and on a
background interval (see ``app/main.py``).
"""

import csv
import json
import re
import time
import uuid
from pathlib import Path

import pandas as pd

from app.core.config import UPLOAD_DIR, UPLOAD_TTL_MINUTES

# ── file_id format ──────────────────────────────────────────────────────────
# Every id we generate is ``uuid4().hex`` — exactly 32 lowercase hex chars.
# Validating against that shape *before* touching the filesystem means a
# hostile value ("../../.env", a 10 MB string, a null byte) is rejected at
# the door rather than relying on later path handling to be safe.
_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def validate_file_id(file_id: str) -> str:
    """
    Return ``file_id`` unchanged if it matches our generated id format.

    Raises ``ValueError`` otherwise. Called at the start of every public
    function in this module, so no caller can accidentally skip it.
    """
    if not isinstance(file_id, str) or not _FILE_ID_PATTERN.match(file_id):
        raise ValueError("Malformed file id.")
    return file_id


def _ensure_upload_dir() -> Path:
    """Create ``UPLOAD_DIR`` on first use and return its absolute path."""
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    return Path(UPLOAD_DIR).resolve()


# ── Writing ─────────────────────────────────────────────────────────────────


def save_upload(file_bytes: bytes, original_filename: str, owner: str) -> str:
    """
    Persist an uploaded file plus its ownership metadata.

    ``owner`` is the caller's verified identity (Firebase email or uid, from
    ``get_current_user``). It is stored alongside the file so every later
    read can be authorised — see the module docstring.

    Returns the generated ``file_id`` that the rest of the system uses as a
    lookup key.
    """
    file_id = uuid.uuid4().hex
    # Only the extension is taken from the user-supplied filename; the name
    # itself is never used to build a path, so a crafted filename cannot
    # escape the upload directory.
    ext = Path(original_filename).suffix.lower()
    dest = _ensure_upload_dir() / f"{file_id}{ext}"
    dest.write_bytes(file_bytes)

    _write_meta(
        file_id,
        {
            "owner": owner,
            # Kept for display only (report headers, PDF filename). Truncated
            # so an absurdly long name can't bloat the sidecar.
            "original_filename": Path(original_filename).name[:200],
            "uploaded_at": time.time(),
        },
    )
    return file_id


def _write_meta(file_id: str, meta: dict) -> None:
    """Write the ``.meta.json`` sidecar (owner, original filename, timestamp)."""
    _meta_path(file_id).write_text(json.dumps(meta), encoding="utf-8")


def save_column_mapping(file_id: str, mapping: dict[str, str]) -> None:
    """
    Persist the user-confirmed ``{raw_column: canonical_field}`` mapping so
    subsequent reads of this file (different filters, PDF export, detailed
    ledger, …) don't need the frontend to resend it every time.
    """
    validate_file_id(file_id)
    _mapping_path(file_id).write_text(json.dumps(mapping), encoding="utf-8")


# ── Path helpers ────────────────────────────────────────────────────────────


def _resolve_path(file_id: str) -> Path:
    """
    Find the raw data file on disk for ``file_id``.

    Matches on ``Path.stem`` rather than joining a user string onto a
    directory, so the sidecars (``{id}.mapping``/``{id}.meta`` stems) are
    never mistaken for the data file. Raises ``FileNotFoundError`` when
    nothing matches.
    """
    validate_file_id(file_id)
    upload_dir = _ensure_upload_dir()
    for candidate in upload_dir.iterdir():
        if candidate.is_file() and candidate.stem == file_id:
            return candidate
    raise FileNotFoundError(f"No uploaded file found for id '{file_id}'.")


def _mapping_path(file_id: str) -> Path:
    """Sidecar JSON storing the user-confirmed column mapping for a file."""
    return _ensure_upload_dir() / f"{validate_file_id(file_id)}.mapping.json"


def _meta_path(file_id: str) -> Path:
    """Sidecar JSON storing owner + original filename for a file."""
    return _ensure_upload_dir() / f"{validate_file_id(file_id)}.meta.json"


# ── Reading ─────────────────────────────────────────────────────────────────


def load_upload_meta(file_id: str) -> dict | None:
    """Return the parsed ``.meta.json`` sidecar, or ``None`` if it's missing/corrupt."""
    path = _meta_path(file_id)
    if not path.exists():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def assert_owner(file_id: str, owner: str) -> None:
    """
    Authorise ``owner`` to read ``file_id``.

    Raises ``PermissionError`` when the ownership sidecar is missing (an
    orphaned or pre-upgrade file — treated as not-yours by default) or names
    a different user. Route handlers translate this to a 404 so the API
    never reveals whether another user's file exists.
    """
    meta = load_upload_meta(file_id)
    if not meta or meta.get("owner") != owner:
        raise PermissionError("This file does not belong to the current user.")


def load_column_mapping(file_id: str) -> dict[str, str] | None:
    """Return the previously confirmed column mapping, or ``None`` if never confirmed."""
    path = _mapping_path(file_id)
    if not path.exists():
        return None
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # Defensive shape check: a hand-edited or truncated sidecar must not be
    # able to feed non-string values into the DataFrame rename step.
    if not isinstance(mapping, dict):
        return None
    return {str(k): str(v) for k, v in mapping.items()}


def get_original_filename(file_id: str, fallback: str | None = None) -> str:
    """
    Best-effort original filename for a stored upload, for display in report
    headers and the PDF title. Prefers the name recorded in the metadata
    sidecar, then the on-disk name, then ``fallback``.
    """
    try:
        validate_file_id(file_id)
    except ValueError:
        return fallback or "upload"

    meta = load_upload_meta(file_id)
    if meta and meta.get("original_filename"):
        return str(meta["original_filename"])
    try:
        return _resolve_path(file_id).name
    except FileNotFoundError:
        return fallback or file_id


def get_file_mtime(file_id: str) -> float:
    """
    Last-modified timestamp of the raw data file.

    Used as part of the normalised-DataFrame cache key so a re-uploaded or
    re-written file can never serve stale cached analytics.
    """
    return _resolve_path(file_id).stat().st_mtime


def _sniff_delimiter(path: Path) -> str:
    """Detect the CSV delimiter from a small sample. Falls back to comma."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            sample = f.read(2048)
        if not sample.strip():
            return ","
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def read_to_dataframe(file_id: str) -> pd.DataFrame:
    """
    Read the previously uploaded file into a Pandas DataFrame.
    Supports ``.csv`` and ``.xlsx``.

    For CSV: auto-detects the delimiter (``,`` ``;`` tab ``|``) and tries
    ``utf-8-sig`` first, then ``latin-1`` as a fallback for non-ASCII data
    exported by older Windows POS software.
    """
    path = _resolve_path(file_id)

    if path.suffix == ".csv":
        sep = _sniff_delimiter(path)
        try:
            df = pd.read_csv(path, sep=sep, encoding="utf-8-sig", engine="python")
        except UnicodeDecodeError:
            df = pd.read_csv(path, sep=sep, encoding="latin-1", engine="python")
    elif path.suffix == ".xlsx":
        df = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported file extension: {path.suffix}")

    return df


# ── Deletion ────────────────────────────────────────────────────────────────


def cleanup(file_id: str) -> None:
    """Remove an upload and both of its sidecars (mapping + metadata) from disk."""
    try:
        path = _resolve_path(file_id)
    except (FileNotFoundError, ValueError):
        pass
    else:
        if path.exists():
            path.unlink()

    for sidecar in (_mapping_path(file_id), _meta_path(file_id)):
        if sidecar.exists():
            sidecar.unlink()


def sweep_expired_uploads() -> int:
    """
    Delete every file in ``UPLOAD_DIR`` older than ``UPLOAD_TTL_MINUTES``
    (data files and sidecars alike, since they share the same mtime window).

    Returns the number of files removed. Safe to call repeatedly (startup +
    periodic timer) — never raises on individual file errors, so one locked
    or mid-write file can't abort the whole sweep.
    """
    upload_dir = _ensure_upload_dir()
    ttl_seconds = UPLOAD_TTL_MINUTES * 60
    now = time.time()
    removed = 0

    for candidate in upload_dir.iterdir():
        if not candidate.is_file():
            continue
        try:
            if now - candidate.stat().st_mtime > ttl_seconds:
                candidate.unlink()
                removed += 1
        except OSError:
            # Removed concurrently or locked by another process — skip it.
            continue

    return removed
