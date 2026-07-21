"""
Analytics endpoints — reads a previously uploaded file from local disk,
runs the full analytics pipeline, and returns pre-formatted
Recharts-compatible JSON.

Routes
------
- GET /process/{file_id}                    — reads from disk, returns AnalyticsResponse
- GET /analytics/{file_id}?time_filter=...  — server-side date filter applied
  before aggregation so every widget reflects the selected range.

Both routes require:
  1. A valid Firebase ID token (see ``get_current_user``).
  2. A confirmed column mapping (see ``/upload/{file_id}/confirm-mapping``)
     — every shop's export format is different, so we never fall back to
     auto-guessing the mapping here. If the user hasn't confirmed their
     columns yet, we return a clear 409 telling the frontend to send them
     back to the mapping screen instead of silently guessing wrong.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response
from typing import Literal

from app.models.schemas import AnalyticsResponse, CAReportSummary, LedgerPage
from app.services.file_handler import read_to_dataframe, load_column_mapping, get_original_filename
from app.services.sales_calculations import (
    run_full_analysis,
    normalize_dataframe,
    apply_time_filter,
    compute_pnl_report,
    build_ledger_page,
)
from app.services.pdf_report import generate_ca_report_pdf, MAX_LEDGER_ROWS_IN_PDF
from app.utils.auth_verifier import get_current_user

router = APIRouter()

# Human-readable labels for the CA report header — kept in sync with the
# TimeFilter literal below.
_PERIOD_LABELS: dict[str, str] = {
    "all": "All Time",
    "today": "Today",
    "week": "Last 7 Days",
    "30days": "Last 30 Days",
    "month": "This Month",
}


def _load_dataframe_and_mapping(file_id: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Shared helper: load a file from disk plus its confirmed column mapping,
    translating low-level errors to HTTP. Raises 409 if the mapping was
    never confirmed (the frontend should redirect to the mapping screen).
    """
    try:
        df = read_to_dataframe(file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for id '{file_id}'. Upload a file first via POST /upload/.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mapping = load_column_mapping(file_id)
    if mapping is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Column mapping not confirmed for file '{file_id}'. "
                "Call POST /upload/{file_id}/confirm-mapping first."
            ),
        )

    return df, mapping


@router.get("/{file_id}", response_model=AnalyticsResponse)
def process_file(file_id: str, user_email: str = Depends(get_current_user)):
    """
    Load the file from disk, validate, and analyse. Returns the full
    AnalyticsResponse payload that the React dashboard renders directly.
    """
    df, mapping = _load_dataframe_and_mapping(file_id)
    try:
        return run_full_analysis(df, time_filter="all", column_mapping=mapping)
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)


# ── /analytics router — supports server-side date filtering ──────────────

analytics_router = APIRouter()

TimeFilter = Literal["all", "today", "week", "30days", "month"]


@analytics_router.get("/{file_id}", response_model=AnalyticsResponse)
def get_analytics(
    file_id: str,
    time_filter: TimeFilter = Query(
        "30days",
        description=(
            "Date window to apply BEFORE aggregation. "
            "'all' = entire dataset, 'today' = max date only, "
            "'week' = last 7 days, '30days' = last 30 days (default), "
            "'month' = from the 1st of the max date's calendar month."
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
    df, mapping = _load_dataframe_and_mapping(file_id)
    try:
        return run_full_analysis(df, time_filter=time_filter, column_mapping=mapping)
    except ValueError as e:
        error_msg = str(e)
        if "Missing required columns" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)


@analytics_router.get("/{file_id}/report", response_model=CAReportSummary)
def get_ca_report(
    file_id: str,
    time_filter: TimeFilter = Query("30days", description="Reporting period for the P&L statement."),
    user_email: str = Depends(get_current_user),
):
    """
    CA-style Profit & Loss report for the selected period: labelled line
    items (Gross Revenue, COGS, Gross Profit) plus a category-wise ledger
    — the same numbers as ``/analytics/{file_id}``, but presented the way
    an accountant would print them (rows and columns), for the "Financial
    Report" view and the PDF export.
    """
    df, mapping = _load_dataframe_and_mapping(file_id)
    try:
        normalized, _errors = normalize_dataframe(df, column_mapping=mapping)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered = apply_time_filter(normalized, time_filter)
    return compute_pnl_report(filtered, time_filter, _PERIOD_LABELS.get(time_filter, time_filter))


@analytics_router.get("/{file_id}/ledger", response_model=LedgerPage)
def get_transaction_ledger(
    file_id: str,
    time_filter: TimeFilter = Query("all", description="Restrict the ledger to this period (default: all rows)."),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(100, ge=1, le=1000, description="Rows per page (max 1000)."),
    user_email: str = Depends(get_current_user),
):
    """
    Paginated, row-by-row transaction ledger — the detailed sales register
    behind the summary numbers. Large files (tens of thousands of rows)
    are never returned in a single response; the frontend pages through
    this endpoint as the user scrolls/navigates the ledger table.
    """
    df, mapping = _load_dataframe_and_mapping(file_id)
    try:
        normalized, _errors = normalize_dataframe(df, column_mapping=mapping)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered = apply_time_filter(normalized, time_filter)
    return build_ledger_page(filtered, page=page, page_size=page_size)


@analytics_router.get("/{file_id}/report.pdf")
def get_ca_report_pdf(
    file_id: str,
    time_filter: TimeFilter = Query("30days", description="Reporting period for the PDF."),
    user_email: str = Depends(get_current_user),
):
    """
    Stream a structured, CA-style PDF report — real text and tables (a
    Profit & Loss statement, category ledger, top items, dead stock, and a
    detailed transaction register), not a screenshot of the dashboard.
    """
    df, mapping = _load_dataframe_and_mapping(file_id)
    try:
        normalized, _errors = normalize_dataframe(df, column_mapping=mapping)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered = apply_time_filter(normalized, time_filter)

    analytics = run_full_analysis(df, time_filter=time_filter, column_mapping=mapping)
    ca_report = compute_pnl_report(filtered, time_filter, _PERIOD_LABELS.get(time_filter, time_filter))

    # Cap the printed ledger — see MAX_LEDGER_ROWS_IN_PDF docstring in
    # pdf_report.py for why we don't print all 50k rows into one PDF.
    ledger_page = build_ledger_page(filtered, page=1, page_size=MAX_LEDGER_ROWS_IN_PDF)

    pdf_bytes = generate_ca_report_pdf(
        filename=get_original_filename(file_id, fallback=file_id),
        analytics=analytics,
        ca_report=ca_report,
        ledger_entries=ledger_page.entries,
        ledger_total_rows=ledger_page.total_rows,
    )

    download_name = f"senova-financial-report-{file_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
