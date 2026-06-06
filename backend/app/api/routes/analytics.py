"""
Analytics endpoints — reads a previously uploaded file from local disk,
runs the full analytics pipeline, and returns pre-formatted
Recharts-compatible JSON.

Routes
------
- GET /process/{file_id}                    — reads from disk, returns AnalyticsResponse
- GET /analytics/{file_id}?time_filter=...  — same as /process, but with a
  server-side date filter so every widget (summary, top items, categories,
  daily trend, dead stock) is re-aggregated for the selected range.
"""

import pandas as pd
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from app.models.schemas import AnalyticsResponse
from app.services.file_handler import read_to_dataframe
from app.services.sales_calculations import run_full_analysis

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


def _apply_time_filter(
    df: pd.DataFrame, time_filter: str
) -> tuple[pd.DataFrame, dict]:
    """
    Filter the cleaned DataFrame by date range. The reference point is the
    maximum date in the dataset (NOT system time) so older CSV uploads
    still produce sensible "Last 7 Days" / "This Month" slices.

    Returns the filtered DataFrame plus a metadata dict describing the
    active window (used for empty-state messaging downstream).
    """
    if time_filter == "all" or df.empty:
        return df, {"filter": time_filter, "window_start": None, "window_end": None}

    dates = pd.to_datetime(df["Date"], errors="coerce")
    max_date = dates.max()
    if pd.isna(max_date):
        return df.iloc[0:0], {"filter": time_filter, "window_start": None, "window_end": None}

    if time_filter == "week":
        cutoff = max_date - timedelta(days=7)
    elif time_filter == "month":
        cutoff = max_date.replace(day=1).normalize()
    else:
        return df, {"filter": time_filter, "window_start": None, "window_end": None}

    filtered = df[dates >= cutoff].copy()
    meta = {
        "filter": time_filter,
        "window_start": cutoff.strftime("%Y-%m-%d"),
        "window_end": max_date.strftime("%Y-%m-%d"),
    }
    return filtered, meta


@router.get("/{file_id}", response_model=AnalyticsResponse)
def process_file(file_id: str):
    """
    Load the file from disk, validate, and analyse. Returns the full
    AnalyticsResponse payload that the React dashboard renders directly.
    """
    df = _load_dataframe(file_id)
    try:
        return run_full_analysis(df)
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)


# ── /analytics router — supports server-side date filtering ──────────────

analytics_router = APIRouter()

TimeFilter = Literal["all", "month", "week"]


@analytics_router.get("/{file_id}", response_model=AnalyticsResponse)
def get_analytics(
    file_id: str,
    time_filter: TimeFilter = Query(
        "all",
        description=(
            "Date window to apply BEFORE aggregation. "
            "'all' = entire dataset, 'week' = last 7 days from the max date, "
            "'month' = from the 1st of the max date's month."
        ),
    ),
):
    """
    Same engine as ``/process/{file_id}`` but with a server-side date
    filter so every widget (summary, top items, categories, daily trend,
    dead stock) reflects the selected range. An empty filtered DataFrame
    is handled gracefully by ``run_full_analysis`` and returns a
    zero-valued AnalyticsResponse.
    """
    df = _load_dataframe(file_id)
    filtered_df, _meta = _apply_time_filter(df, time_filter)
    try:
        return run_full_analysis(filtered_df)
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)