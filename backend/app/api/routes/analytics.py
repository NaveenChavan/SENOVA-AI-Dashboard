"""
Analytics endpoints — reads a previously uploaded file from local disk,
runs the full analytics pipeline, and returns pre-formatted
Recharts-compatible JSON.

Routes
------
- GET /process/{file_id}                    — reads from disk, returns AnalyticsResponse
- GET /analytics/{file_id}?time_filter=...  — server-side date filter applied
  before aggregation so every widget reflects the selected range.

Both routes require a valid Firebase ID token (see ``get_current_user``).
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Literal

from app.models.schemas import AnalyticsResponse
from app.services.file_handler import read_to_dataframe
from app.services.sales_calculations import run_full_analysis
from app.utils.auth_verifier import get_current_user

router = APIRouter()


def _load_dataframe(file_id: str) -> pd.DataFrame:
    """Shared helper: load a file from disk, translating low-level errors to HTTP."""
    try:
        return read_to_dataframe(file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for id '{file_id}'. Upload a file first via POST /upload/.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{file_id}", response_model=AnalyticsResponse)
def process_file(file_id: str, user_email: str = Depends(get_current_user)):
    """
    Load the file from disk, validate, and analyse. Returns the full
    AnalyticsResponse payload that the React dashboard renders directly.
    """
    df = _load_dataframe(file_id)
    try:
        return run_full_analysis(df, time_filter="all")
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)


# ── /analytics router — supports server-side date filtering ──────────────

analytics_router = APIRouter()

TimeFilter = Literal["all", "30days", "month", "week"]


@analytics_router.get("/{file_id}", response_model=AnalyticsResponse)
def get_analytics(
    file_id: str,
    time_filter: TimeFilter = Query(
        "all",
        description=(
            "Date window to apply BEFORE aggregation. "
            "'all' = entire dataset, '30days' = last 30 days, "
            "'week' = last 7 days from the max date, "
            "'month' = from the 1st of the max date's month."
        ),
    ),
    user_email: str = Depends(get_current_user),
):
    """
    Same engine as ``/process/{file_id}`` but with a server-side date
    filter so every widget (summary, top items, categories, daily trend,
    dead stock) reflects the selected range. An empty filtered DataFrame
    is handled gracefully by ``run_full_analysis`` and returns a
    zero-valued AnalyticsResponse.
    """
    df = _load_dataframe(file_id)
    try:
        return run_full_analysis(df, time_filter=time_filter)
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)