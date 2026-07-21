"""
Upload flow — two steps, because every shop's export format is different.

Step 1: POST /upload/
    Accepts a CSV/Excel file, saves it to disk, and returns a
    ColumnMappingPreview — our best guess at how the file's raw columns map
    to the 6 canonical fields (Date, Category, Item, Quantity, Selling
    Price, Cost Price). No validation or analysis runs yet.

Step 2: POST /upload/{file_id}/confirm-mapping
    The frontend shows the guess to the user, lets them correct any wrong
    mapping, then posts the confirmed ``{raw_column: canonical_field}``
    map here. This is where the actual row-level validation happens and
    the confirmed mapping is saved so every later read of this file
    (date filters, PDF export, detailed ledger) reuses it automatically.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
import pandas as pd

from app.core.config import MAX_UPLOAD_SIZE_MB
from app.services.file_handler import (
    save_upload,
    read_to_dataframe,
    cleanup,
    save_column_mapping,
    get_original_filename,
)
from app.models.schemas import UploadResponse, RowError, ColumnMappingPreview, ColumnGuess, DataDateRange
from app.utils.data_validator import normalize_dataframe, detect_column_mapping
from app.utils.auth_verifier import get_current_user
from app.services.sales_calculations import compute_data_date_range

router = APIRouter()

# How many sample rows to send back for the live preview on the mapping screen.
_SAMPLE_ROW_COUNT = 5


def _validate_upload_constraints(file: UploadFile) -> None:
    """Shared checks for both the file type and its declared extension."""
    allowed_extensions = (".csv", ".xlsx")
    if not file.filename or not any(
        file.filename.lower().endswith(ext) for ext in allowed_extensions
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(allowed_extensions)}.",
        )


@router.post("/", response_model=ColumnMappingPreview, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user_email: str = Depends(get_current_user),
):
    """
    Step 1 — save the file and return a best-guess column mapping.
    Does NOT validate rows or run analysis; that happens once the user
    confirms their mapping via ``/upload/{file_id}/confirm-mapping``.
    """
    _validate_upload_constraints(file)

    contents = await file.read()

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB}MB.",
        )

    file_id = save_upload(contents, file.filename)

    try:
        df = read_to_dataframe(file_id)
    except (ValueError, Exception) as e:
        cleanup(file_id)
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    if df.empty or len(df.columns) == 0:
        cleanup(file_id)
        raise HTTPException(status_code=400, detail="The uploaded file has no columns or rows.")

    guesses = detect_column_mapping(df)

    # Sample rows for the live preview — replace NaN with None so it's valid JSON,
    # and stringify everything else so we don't leak numpy/pandas types.
    sample_df = df.head(_SAMPLE_ROW_COUNT)
    sample_rows = [
        {str(col): (None if pd.isna(v) else str(v)) for col, v in row.items()}
        for row in sample_df.to_dict(orient="records")
    ]

    return ColumnMappingPreview(
        file_id=file_id,
        filename=file.filename,
        detected_columns=[ColumnGuess(**g) for g in guesses],
        row_count=len(df),
        sample_rows=sample_rows,
    )


class ConfirmMappingRequest(BaseModel):
    """Body for POST /upload/{file_id}/confirm-mapping."""
    mapping: dict[str, str]


@router.post("/{file_id}/confirm-mapping", response_model=UploadResponse)
async def confirm_mapping(
    file_id: str,
    body: ConfirmMappingRequest,
    user_email: str = Depends(get_current_user),
):
    """
    Step 2 — apply the user-confirmed column mapping, run full row-level
    validation, persist the mapping for reuse, and return the same
    UploadResponse shape the old single-step flow used to return.
    """
    try:
        df = read_to_dataframe(file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for id '{file_id}'. Upload a file first via POST /upload/.",
        )

    try:
        valid_df, error_dicts = normalize_dataframe(
            df, soft_fail=True, column_mapping=body.mapping
        )
        errors = [RowError(**e) for e in error_dicts]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Persist the confirmed mapping so /analytics, the PDF export, and the
    # detailed ledger can all re-read this file later without needing the
    # frontend to resend the mapping every time.
    save_column_mapping(file_id, body.mapping)

    # Best-effort filename lookup for the response — we don't store the
    # original filename separately, so fall back to the on-disk name.
    filename = get_original_filename(file_id)

    # Actual date span of the valid data — the frontend uses this to grey
    # out date filters that are wider than the data itself (see
    # DataDateRange docstring for why that matters).
    date_range = DataDateRange(**compute_data_date_range(valid_df))

    return UploadResponse(
        file_id=file_id,
        filename=filename,
        message=f"Uploaded {len(valid_df)} valid row(s) with {len(errors)} error(s).",
        valid_count=len(valid_df),
        error_count=len(errors),
        errors=errors,
        date_range=date_range,
    )
