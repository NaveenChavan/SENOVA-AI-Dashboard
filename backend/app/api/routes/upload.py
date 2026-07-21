"""
POST /upload — accepts a CSV or Excel file, validates every row, persists
the file to local disk, and returns per-row errors alongside a file_id
that the dashboard uses to fetch the analytics JSON.

The file is kept on disk after upload so the ``/process/{file_id}`` route
can read it. A background TTL sweep (see ``app.services.file_handler``)
removes it automatically after ``UPLOAD_TTL_MINUTES``.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.core.config import MAX_UPLOAD_SIZE_MB
from app.services.file_handler import save_upload, read_to_dataframe, cleanup
from app.models.schemas import UploadResponse, RowError
from app.utils.data_validator import normalize_dataframe
from app.utils.auth_verifier import get_current_user

router = APIRouter()

@router.post("/", response_model=UploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user_email: str = Depends(get_current_user),
):
    allowed_extensions = (".csv", ".xlsx")
    if not file.filename or not any(
        file.filename.lower().endswith(ext) for ext in allowed_extensions
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(allowed_extensions)}.",
        )

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
        valid_df, error_dicts = normalize_dataframe(df, soft_fail=True)
        errors = [RowError(**e) for e in error_dicts]
    except ValueError as e:
        cleanup(file_id)
        raise HTTPException(status_code=400, detail=str(e))

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        message=f"Uploaded {len(valid_df)} valid row(s) with {len(errors)} error(s).",
        valid_count=len(valid_df),
        error_count=len(errors),
        errors=errors,
    )