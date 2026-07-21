"""
Handles file I/O — saving uploads to disk and reading them into Pandas.

Swap this module when moving from local files to object storage / database
without touching the calculation or route layers.

Cleanup strategy
-----------------
Files are NOT deleted right after the first successful ``/process`` or
``/analytics`` call, because the dashboard re-fetches the same ``file_id``
whenever the user changes the date filter (see ``Dashboard.jsx``). Instead,
a TTL sweep (``sweep_expired_uploads``) removes any file older than
``UPLOAD_TTL_MINUTES``. The sweep runs once at app startup and on a
background interval (see ``app/main.py``).

Column mapping persistence
---------------------------
Every shop's export format is different (see the column-mapping
confirmation flow in ``api/routes/upload.py``), so once a user confirms
how their columns map to our 6 canonical fields, that mapping is saved
alongside the raw file as ``{file_id}.mapping.json``. Every later read of
the same file (different date filters, the CA-style report, the PDF
export, etc.) reuses the confirmed mapping instead of re-guessing.
"""

import csv
import json
import time
import uuid
from pathlib import Path

import pandas as pd

from app.core.config import UPLOAD_DIR, UPLOAD_TTL_MINUTES


def _ensure_upload_dir() -> Path:
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    return Path(UPLOAD_DIR).resolve()


def save_upload(file_bytes: bytes, original_filename: str) -> str:
    """
    Persist the uploaded file to `temp_uploads/` under a unique name.
    Returns a `file_id` (UUID) that the rest of the system uses as a lookup key.
    """
    file_id = uuid.uuid4().hex
    ext = Path(original_filename).suffix.lower()
    dest = _ensure_upload_dir() / f"{file_id}{ext}"

    dest.write_bytes(file_bytes)

    return file_id


def _resolve_path(file_id: str) -> Path:
    """
    Find the file on disk matching the given `file_id`.
    Raises FileNotFoundError when the file does not exist.
    """
    upload_dir = _ensure_upload_dir()
    for candidate in upload_dir.iterdir():
        if candidate.stem == file_id:
            return candidate
    raise FileNotFoundError(f"No uploaded file found for id '{file_id}'.")


def get_original_filename(file_id: str, fallback: str | None = None) -> str:
    """
    Public helper: best-effort original filename for a stored upload.

    We don't persist the original filename separately from the file_id, so
    this just returns the on-disk filename (``{file_id}{ext}``). It exists
    mainly so response messages have *some* filename to show; callers that
    already know the original name (e.g. right after upload, still in
    memory) should prefer that instead of calling this.
    """
    try:
        return _resolve_path(file_id).name
    except FileNotFoundError:
        return fallback or file_id


def _sniff_delimiter(path: Path) -> str:
    """Detect CSV delimiter from a small sample. Falls back to comma."""
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
    Supports .csv and .xlsx extensions.

    For CSV: auto-detects delimiter (`,` `;` `\t` `|`) and tries
    `utf-8-sig` first, then `latin-1` as a fallback for non-ASCII data.
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


def cleanup(file_id: str) -> None:
    """Remove the uploaded file (and its saved column mapping, if any) from disk."""
    try:
        path = _resolve_path(file_id)
    except FileNotFoundError:
        pass
    else:
        if path.exists():
            path.unlink()

    mapping_path = _mapping_path(file_id)
    if mapping_path.exists():
        mapping_path.unlink()


def _mapping_path(file_id: str) -> Path:
    """Sidecar JSON file storing the user-confirmed column mapping for a file."""
    return _ensure_upload_dir() / f"{file_id}.mapping.json"


def save_column_mapping(file_id: str, mapping: dict[str, str]) -> None:
    """
    Persist the user-confirmed ``{raw_column: canonical_field}`` mapping so
    subsequent reads of this file (different date filters, PDF export,
    detailed ledger, etc.) don't need the frontend to resend it every time.
    """
    _mapping_path(file_id).write_text(json.dumps(mapping), encoding="utf-8")


def load_column_mapping(file_id: str) -> dict[str, str] | None:
    """Return the previously confirmed column mapping, or None if never confirmed."""
    path = _mapping_path(file_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def sweep_expired_uploads() -> int:
    """
    Delete every file in ``UPLOAD_DIR`` older than ``UPLOAD_TTL_MINUTES``.

    Returns the number of files removed. Safe to call repeatedly (e.g. on
    startup and on a periodic background timer) — never raises on
    individual file errors so one locked/mid-write file can't abort the
    whole sweep.
    """
    upload_dir = _ensure_upload_dir()
    ttl_seconds = UPLOAD_TTL_MINUTES * 60
    now = time.time()
    removed = 0

    for candidate in upload_dir.iterdir():
        if not candidate.is_file():
            continue
        try:
            age_seconds = now - candidate.stat().st_mtime
            if age_seconds > ttl_seconds:
                candidate.unlink()
                removed += 1
        except OSError:
            # File may have been removed concurrently or is locked — skip it.
            continue

    return removed
