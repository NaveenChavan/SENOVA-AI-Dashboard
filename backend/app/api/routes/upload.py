"""
Upload flow — two steps, because every shop's export format is different.

Step 1: ``POST /upload/``
    Accepts a CSV/Excel file, saves it to disk **bound to the calling user**,
    and returns a ``ColumnMappingPreview``: our best guess at how the file's
    raw columns map to the canonical fields, which optional fields are
    available, and a few sample rows for a live preview. Nothing is validated
    or analysed yet.

Step 2: ``POST /upload/{file_id}/confirm-mapping``
    The frontend shows the guess, the user corrects it, and the confirmed
    ``{raw_column: canonical_field}`` map is posted here. This is where
    row-level validation runs and where the mapping is persisted so every
    later read (filters, charts, insights, PDF) reuses it automatically.

Security notes
--------------
* Both routes require a verified Firebase ID token.
* The upload records the caller as the file's owner; every analytics route
  re-checks that ownership, so one user can never read another's sales data.
* Only the *extension* of the client-supplied filename is used when writing to
  disk — the name itself never becomes part of a path.
* Confirming a mapping invalidates the cached frame for that file, so a
  corrected mapping can't be shadowed by a stale cache entry.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
import pandas as pd

from app.core.config import MAX_UPLOAD_SIZE_MB
from app.models.schemas import (
    ColumnGuess,
    ColumnMappingPreview,
    DataDateRange,
    RowError,
    UploadResponse,
)
from app.services import frame_cache
from app.services.file_handler import (
    assert_owner,
    cleanup,
    get_original_filename,
    read_to_dataframe,
    save_column_mapping,
    save_upload,
    validate_file_id,
)
from app.services.sales_calculations import compute_data_date_range
from app.utils.auth_verifier import get_current_user
from app.utils.data_validator import (
    MAPPABLE_FIELDS,
    OPTIONAL_DIMENSION_COLUMNS,
    OPTIONAL_MEASURE_COLUMNS,
    REQUIRED_COLUMNS,
    detect_column_mapping,
    normalize_dataframe,
)

router = APIRouter()

#: How many sample rows to send back for the live preview on the mapping screen.
_SAMPLE_ROW_COUNT = 5

#: Cap on how many raw columns we will describe. A file with thousands of
#: columns is almost certainly not a sales register, and rendering them all
#: would lock up the mapping screen.
_MAX_COLUMNS = 100

#: Helper text shown under each field on the mapping screen. Written for a shop
#: owner, not a developer — this is the screen where a wrong choice quietly
#: corrupts every number downstream.
_FIELD_HELP: dict[str, str] = {
    "Date": "When the sale happened (invoice / bill / voucher date).",
    "Category": "Product group — Kurta, Saree, Shirt, Grocery…",
    "Item": "The product name, style or SKU that was sold.",
    "Quantity": "How many pieces were sold on that line.",
    "Selling Price": "Price of ONE piece. Leave unmapped if your file only has a line total.",
    "Cost Price": "Your purchase cost for ONE piece.",
    "Line Total": "Line amount = quantity × rate. Map this if your file has Amount / Net Amount instead of a unit price.",
    "Discount": "Discount given on the line, in rupees. Revenue is reported net of this.",
    "Tax": "GST / VAT collected on the line. Shown separately, never counted as profit.",
    "Stock On Hand": "Pieces still in stock. Unlocks days-of-cover and reorder alerts.",
    "Branch": "Shop, store or godown name — becomes a filter and a chart axis.",
    "Payment Mode": "Cash / UPI / Card — becomes a filter and a chart axis.",
    "Customer": "Customer or party name.",
    "Salesperson": "Who made the sale.",
    "Brand": "Brand or manufacturer.",
    "Size": "Size or variant.",
    "Colour": "Colour or shade.",
    "Invoice No": "Bill / invoice / order number.",
}


def _validate_upload_constraints(file: UploadFile) -> None:
    """Reject anything that isn't a CSV or XLSX by declared extension."""
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
    user: str = Depends(get_current_user),
):
    """
    Step 1 — save the file (owned by the caller) and return a best-guess
    column mapping. No rows are validated and no analysis runs yet.
    """
    _validate_upload_constraints(file)

    contents = await file.read()

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB}MB.",
        )

    file_id = save_upload(contents, file.filename, owner=user)

    try:
        df = read_to_dataframe(file_id)
    except Exception as exc:
        # A file we can't parse is worthless — delete it rather than leaving an
        # orphan on disk waiting for the TTL sweep.
        cleanup(file_id)
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    if df.empty or len(df.columns) == 0:
        cleanup(file_id)
        raise HTTPException(status_code=400, detail="The uploaded file has no columns or rows.")

    if len(df.columns) > _MAX_COLUMNS:
        cleanup(file_id)
        raise HTTPException(
            status_code=400,
            detail=f"This file has {len(df.columns)} columns; the maximum supported is {_MAX_COLUMNS}.",
        )

    guesses = detect_column_mapping(df)

    # Sample rows for the live preview: NaN → None so the JSON stays valid, and
    # everything else stringified so no numpy/pandas type leaks into the payload.
    sample_rows = [
        {str(col): (None if pd.isna(value) else str(value)[:120]) for col, value in row.items()}
        for row in df.head(_SAMPLE_ROW_COUNT).to_dict(orient="records")
    ]

    return ColumnMappingPreview(
        file_id=file_id,
        filename=file.filename,
        detected_columns=[ColumnGuess(**g) for g in guesses],
        required_fields=sorted(REQUIRED_COLUMNS),
        optional_fields=[f for f in MAPPABLE_FIELDS if f not in REQUIRED_COLUMNS],
        field_help=_FIELD_HELP,
        row_count=len(df),
        sample_rows=sample_rows,
    )


class ConfirmMappingRequest(BaseModel):
    """Body for ``POST /upload/{file_id}/confirm-mapping``."""

    mapping: dict[str, str] = Field(
        ..., description="{raw_column: canonical_field}; unrecognised fields are ignored."
    )


@router.post("/{file_id}/confirm-mapping", response_model=UploadResponse)
async def confirm_mapping(
    file_id: str,
    body: ConfirmMappingRequest,
    user: str = Depends(get_current_user),
):
    """
    Step 2 — apply the confirmed mapping, run full row-level validation,
    persist the mapping, and report what came out: valid row count, every
    row-level error, the data's real date span, and which optional fields this
    file unlocked.
    """
    try:
        validate_file_id(file_id)
        assert_owner(file_id, user)
        df = read_to_dataframe(file_id)
    except (ValueError, PermissionError, FileNotFoundError):
        # One indistinguishable 404 for malformed / missing / someone else's id.
        raise HTTPException(status_code=404, detail="File not found. Upload a file first.")

    try:
        valid_df, error_dicts = normalize_dataframe(df, soft_fail=True, column_mapping=body.mapping)
        errors = [RowError(**e) for e in error_dicts]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Persist the mapping, then drop any cached frame built from an older one.
    save_column_mapping(file_id, body.mapping)
    frame_cache.invalidate(file_id)

    optional_present = [
        field
        for field in sorted(OPTIONAL_MEASURE_COLUMNS | OPTIONAL_DIMENSION_COLUMNS)
        if field in valid_df.columns
    ]

    return UploadResponse(
        file_id=file_id,
        filename=get_original_filename(file_id),
        message=f"Uploaded {len(valid_df)} valid row(s) with {len(errors)} error(s).",
        valid_count=len(valid_df),
        error_count=len(errors),
        errors=errors,
        date_range=DataDateRange(**compute_data_date_range(valid_df)),
        optional_fields=optional_present,
    )
