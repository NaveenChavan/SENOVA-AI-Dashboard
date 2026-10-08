"""
Analytics endpoints.

Two generations of routes live here, sharing one engine:

**Classic GET routes** (``/process/{id}``, ``/analytics/{id}``,
``/analytics/{id}/report``, ``/ledger``, ``/report.pdf``) take a preset
``time_filter`` in the query string. They are unchanged in behaviour and stay
for backwards compatibility.

**Pro POST routes** take an ``AnalysisQuery`` body — the same presets *plus*
custom date ranges and dimension filters — and power the upgraded dashboard:
``/summary``, ``/chart-data``, ``/heatmap``, ``/insights``, ``/inventory``,
``/forecast``, ``/report``, ``/ledger``, ``/report.pdf``, and a ``GET
/dimensions`` that tells the frontend what this particular file can be sliced
by. Filters live in a body rather than the query string because they are
structured data; every one of them is validated against a closed registry.

Security applied to every route in this file
--------------------------------------------
* a verified Firebase ID token (``get_current_user``);
* ``file_id`` matched against the generated-id format before any filesystem
  access;
* **ownership check** — the file must belong to the caller, else 404 (never
  403, so the API doesn't confirm that someone else's file exists);
* a confirmed column mapping, else 409 with a pointer back to the mapping
  screen — we never silently re-guess a shop's column layout;
* bounded pagination/horizon/top-N values, enforced by the schema models.
"""

from datetime import timedelta
import logging

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from typing import Literal

from app.models.schemas import (
    AiInsightsRequest,
    AiInsightsResponse,
    AiNarrative,
    AnalysisQuery,
    AnalyticsResponse,
    CAReportSummary,
    ChartDataResponse,
    ChartQuery,
    DimensionsResponse,
    DimensionOption,
    DimensionOptionsRequest,
    DynamicSchema,
    ForecastQuery,
    ForecastResponse,
    HeatmapResponse,
    InsightsResponse,
    InventoryResponse,
    LedgerPage,
    LedgerQuery,
    RowError,
)
from app.services import dynamic_schema, frame_cache, number_guard, query_engine, tier2_gemini

logger = logging.getLogger("senova.analytics")
from app.services.file_handler import (
    assert_owner,
    get_original_filename,
    load_column_mapping,
    validate_file_id,
)
from app.services.forecasting import compute_forecast
from app.services.insights_engine import compute_insights
from app.services.inventory_intel import compute_inventory_intelligence
from app.services.pdf_report import (
    MAX_LEDGER_ROWS_IN_PDF,
    generate_ca_report_pdf,
    generate_visual_financial_pdf,
)
from app.services.query_engine import QueryError
from app.services.discount_calculations import compute_discount, compute_discount_vs_margin
from app.services.sales_calculations import (
    build_ledger_page,
    compute_daily_trend_between,
    compute_daily_financial_summary,
    compute_dead_stock,
    compute_pnl_report,
    compute_revenue_by_category,
    compute_summary_between,
    compute_top_items,
)
from app.utils.auth_verifier import get_current_user

router = APIRouter()

TimeFilter = Literal["all", "today", "week", "30days", "month"]

#: Human-readable labels for the classic presets (kept in sync with the engine).
_PERIOD_LABELS = query_engine.PERIOD_LABELS


logger = logging.getLogger("senova.analytics")

# ── Shared loading + slicing ────────────────────────────────────────────────


def _load_frame(file_id: str, user: str) -> pd.DataFrame:
    """
    Authorise the caller, then return the cached, normalised frame for a file.

    Every failure is translated to the HTTP status the frontend already knows
    how to handle, and no internal path or stack detail is ever echoed back.
    """
    try:
        validate_file_id(file_id)
        assert_owner(file_id, user)
    except (ValueError, PermissionError):
        # Same 404 for "malformed", "missing" and "not yours" — the response
        # must not reveal which of the three it was.
        raise HTTPException(status_code=404, detail="File not found. Upload a file first.")

    mapping = load_column_mapping(file_id)
    if mapping is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Column mapping not confirmed for file '{file_id}'. "
                "Call POST /upload/{file_id}/confirm-mapping first."
            ),
        )

    try:
        frame, _errors = frame_cache.get_normalized_frame(file_id, mapping)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found. Upload a file first.")
    except ValueError as exc:
        # Missing required columns after mapping — actionable, so it is shown.
        raise HTTPException(status_code=400, detail=str(exc))

    return frame


def _row_errors(file_id: str, user: str) -> list[RowError]:
    """Row-level validation errors for a file (cheap: served from the same cache)."""
    mapping = load_column_mapping(file_id) or {}
    try:
        _frame, errors = frame_cache.get_normalized_frame(file_id, mapping)
    except (FileNotFoundError, ValueError):
        return []
    return [RowError(**e) for e in errors]


def _slice(file_id: str, user: str, query: AnalysisQuery):
    """
    Resolve one ``AnalysisQuery`` into ``(current, previous, window)``.

    This is the single place a Pro request turns into rows, which is why the
    KPI cards, charts, insights, inventory, P&L and PDF can never disagree.
    """
    frame = _load_frame(file_id, user)
    try:
        return query_engine.build_slice(
            frame,
            time_filter=query.time_filter,
            start_date=query.start_date,
            end_date=query.end_date,
            filters=query.filters,
        )
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _empty_analytics(errors: list[RowError], row_count: int = 0) -> AnalyticsResponse:
    """A zero-valued payload, so an empty filter result still renders cleanly."""
    from app.models.schemas import MetricValue, SalesSummary

    return AnalyticsResponse(
        row_count=row_count,
        summary=SalesSummary(
            revenue=MetricValue(value=0.0),
            profit=MetricValue(value=0.0),
            cost=MetricValue(value=0.0),
            units_sold=MetricValue(value=0),
            unique_items_sold=MetricValue(value=0),
        ),
        top_items=[],
        daily_trend=[],
        dead_stock=[],
        categories=[],
        errors=errors,
        discount_metrics=None,
        discount_vs_margin=[],
    )


def _build_analytics(current, previous, window, errors: list[RowError]) -> AnalyticsResponse:
    """Assemble the standard dashboard payload from a resolved slice."""
    if current.empty:
        return _empty_analytics(errors, row_count=0)

    # The window's end is exclusive; the trend chart wants the last included day.
    trend_end = window.end - timedelta(days=1)
    return AnalyticsResponse(
        row_count=len(current),
        summary=compute_summary_between(current, previous, window.start, trend_end),
        top_items=compute_top_items(current),
        daily_trend=compute_daily_trend_between(current, window.start, trend_end),
        dead_stock=compute_dead_stock(current),
        categories=compute_revenue_by_category(current),
        errors=errors,
        discount_metrics=compute_discount(current),
        discount_vs_margin=compute_discount_vs_margin(current),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Classic routes — preset filter in the query string
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{file_id}", response_model=AnalyticsResponse)
def process_file(file_id: str, user: str = Depends(get_current_user)):
    """Full analytics over the whole file (``/process/{file_id}``)."""
    query = AnalysisQuery(time_filter="all")
    current, previous, window = _slice(file_id, user, query)
    return _build_analytics(current, previous, window, _row_errors(file_id, user))


analytics_router = APIRouter()


@analytics_router.get("/{file_id}", response_model=AnalyticsResponse)
def get_analytics(
    file_id: str,
    time_filter: TimeFilter = Query("30days", description="Date window applied before aggregation."),
    user: str = Depends(get_current_user),
):
    """Analytics for one preset window — the classic dashboard endpoint."""
    current, previous, window = _slice(file_id, user, AnalysisQuery(time_filter=time_filter))
    return _build_analytics(current, previous, window, _row_errors(file_id, user))


@analytics_router.get("/{file_id}/report", response_model=CAReportSummary)
def get_ca_report(
    file_id: str,
    time_filter: TimeFilter = Query("30days", description="Reporting period for the P&L statement."),
    user: str = Depends(get_current_user),
):
    """CA-style P&L + category ledger for one preset window."""
    current, _previous, window = _slice(file_id, user, AnalysisQuery(time_filter=time_filter))
    return compute_pnl_report(current, window.label)


@analytics_router.get("/{file_id}/ledger", response_model=LedgerPage)
def get_transaction_ledger(
    file_id: str,
    time_filter: TimeFilter = Query("all", description="Restrict the ledger to this period."),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    user: str = Depends(get_current_user),
):
    """One page of the row-by-row transaction register."""
    current, _previous, _window = _slice(file_id, user, AnalysisQuery(time_filter=time_filter))
    return build_ledger_page(current, page=page, page_size=page_size)


@analytics_router.get("/{file_id}/report.pdf")
def get_ca_report_pdf(
    file_id: str,
    time_filter: TimeFilter = Query("30days", description="Reporting period for the PDF."),
    user: str = Depends(get_current_user),
):
    """Structured PDF report (real tables, not a screenshot) for one preset window."""
    return _render_pdf(file_id, user, AnalysisQuery(time_filter=time_filter))


# ═══════════════════════════════════════════════════════════════════════════
#  Pro routes — full AnalysisQuery body (presets, custom ranges, filters)
# ═══════════════════════════════════════════════════════════════════════════


@analytics_router.get("/{file_id}/dimensions", response_model=DimensionsResponse)
def get_dimensions(file_id: str, user: str = Depends(get_current_user)):
    """
    What this file can be sliced by: the dimensions it actually contains with
    their distinct values, the optional measures it provided, and its real date
    span. The filter panel and chart dropdowns are built from this response.
    """
    frame = _load_frame(file_id, user)
    return query_engine.dimension_options(frame)


@analytics_router.post("/{file_id}/dimensions/options", response_model=DimensionOption)
def post_dimension_options(file_id: str, request: DimensionOptionsRequest, user: str = Depends(get_current_user)):
    """Return searchable, cascade-aware values for one filter dimension."""
    frame = _load_frame(file_id, user)
    try:
        return query_engine.dimension_option(
            frame,
            request.dimension,
            filters=request.filters,
            time_filter=request.time_filter,
            start_date=request.start_date,
            end_date=request.end_date,
            search=request.search,
            limit=request.limit,
        )
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@analytics_router.post("/{file_id}/schema", response_model=DynamicSchema)
def post_schema(file_id: str, user: str = Depends(get_current_user)):
    """
    What this file can be asked — KPI cards, charts, dimensions and measures,
    each flagged available or not with the reason when it isn't.

    Additive: the existing dashboard does not depend on this. Its value is that
    the UI can stop hiding cards silently. A file with no Cost Price would
    otherwise show a profit card reading zero, which is indistinguishable from a
    genuinely unprofitable month.

    Goes through ``_load_frame``, so it carries the same ownership check, the same
    indistinguishable 404 and the same 409-until-mapping-confirmed rule as every
    other route in this file.
    """
    frame = _load_frame(file_id, user)
    mapping = load_column_mapping(file_id) or {}
    return dynamic_schema.build(frame, mapping=mapping)


@analytics_router.post("/{file_id}/ai-insights", response_model=AiInsightsResponse)
async def post_ai_insights(file_id: str, body: AiInsightsRequest, user: str = Depends(get_current_user)):
    """
    The existing insights, plus AI wording for each card that passed a number check.

    Additive in the strongest sense: ``insights`` is exactly what
    ``POST /{file_id}/insights`` returns, computed by the same untouched
    ``insights_engine``. Gemini only ever rephrases. No new statistic, no new
    severity, no new card type — so if this endpoint is unreachable, the
    dashboard loses nothing but nicer wording.

    Two gates before anything leaves the server: ``AI_ASSIST_ENABLED`` (the
    operator switch) and ``ai_consent`` on this request. When either is closed the
    response is the plain insights with ``ai_source="skipped"`` and **zero** HTTP
    calls, which is why a declined user gets a completely normal dashboard.

    Each rewrite is verified against its own insight's ``metrics`` and
    ``evidence`` by ``number_guard``. An unverified rewrite is reported with
    ``verified=false`` and the frontend renders the deterministic sentence instead,
    so one bad rewrite costs one card's wording, not the response.
    """
    current, previous, window = _slice(file_id, user, body)
    insights = compute_insights(current, previous, period_label=window.label)

    candidates: dict[str, str] = {}
    notice: str | None = None
    reason_code: str | None = None
    source = "skipped"
    elapsed_ms = 0.0

    # The gate is re-checked here as well as in tier2_gemini, so that the "zero
    # calls" promise is visible at the route rather than only inside a helper.
    if tier2_gemini.gemini_enabled() and body.ai_consent:
        payload = [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "severity": item.severity,
                "metrics": item.metrics,
                "evidence": item.evidence,
            }
            for item in insights.insights
        ]
        result = await tier2_gemini.rewrite_insights(payload, ai_consent=True)
        candidates = result.rewrites
        source = result.source
        notice = result.notice
        reason_code = result.reason_code
        elapsed_ms = result.elapsed_ms

    ai_text: list[AiNarrative] = []
    verified_count = 0

    # Built from the computed insights rather than from the request, so the check
    # is always against the figures actually in this response. A rewrite is
    # verified against the insight it claims to rewrite, never against a pool of
    # every number on the dashboard — that would let a card cite a real number
    # belonging to a completely different finding.
    by_id = {item.id: item for item in insights.insights}
    for insight_id, text in candidates.items():
        insight = by_id.get(insight_id)
        if insight is None:
            continue  # defence in depth; _sanitise_rewrites already filters these
        verified, offenders = number_guard.verify(
            text, metrics=insight.metrics, evidence=insight.evidence
        )
        verified_count += int(verified)
        ai_text.append(
            AiNarrative(id=insight_id, text=text, verified=verified, rejected_numbers=offenders)
        )

    if candidates and verified_count == 0:
        # Every rewrite failed the check. Say so rather than shipping a response
        # where nothing is renderable and the failure looks like silence.
        logger.warning("All %d AI rewrite(s) failed the number check.", len(candidates))
        reason_code = "number_check"
        notice = "AI answer failed the number check; original text kept."

    logger.info(
        "AI insights: source=%s cards=%d rewrites=%d verified=%d elapsed=%.1fms",
        source, len(insights.insights), len(ai_text), verified_count, elapsed_ms,
    )

    return AiInsightsResponse(
        insights=insights.insights,
        anomaly_dates=insights.anomaly_dates,
        analysed_days=insights.analysed_days,
        note=insights.note,
        ai_text=ai_text,
        ai_source=source,
        ai_notice=notice,
        ai_reason_code=reason_code,
        ai_elapsed_ms=elapsed_ms,
    )


@analytics_router.post("/{file_id}/summary", response_model=AnalyticsResponse)
def post_summary(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """KPIs, top items, category split, daily trend and dead stock for a filtered slice."""
    current, previous, window = _slice(file_id, user, query)
    return _build_analytics(current, previous, window, _row_errors(file_id, user))


@analytics_router.post("/{file_id}/chart-data", response_model=ChartDataResponse)
def post_chart_data(file_id: str, query: ChartQuery, user: str = Depends(get_current_user)):
    """
    Group a filtered slice by any allowed dimension and return points carrying
    every measure — one request feeds bar, line, donut, combo, scatter, Pareto
    and treemap views.
    """
    current, _previous, _window = _slice(file_id, user, query)
    try:
        return query_engine.aggregate(
            current, dimension=query.dimension, measure=query.measure, top_n=query.top_n
        )
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@analytics_router.post("/{file_id}/heatmap", response_model=HeatmapResponse)
def post_heatmap(file_id: str, query: ChartQuery, user: str = Depends(get_current_user)):
    """Weekday × week intensity grid for the selected measure."""
    current, _previous, _window = _slice(file_id, user, query)
    try:
        return query_engine.heatmap(current, measure=query.measure)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@analytics_router.post("/{file_id}/insights", response_model=InsightsResponse)
def post_insights(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """Automatically-detected findings for the slice (Feature 1)."""
    current, previous, window = _slice(file_id, user, query)
    return compute_insights(current, previous, period_label=window.label)


@analytics_router.post("/{file_id}/inventory", response_model=InventoryResponse)
def post_inventory(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """Velocity, ABC class, ageing and reorder priority per item (Feature 3)."""
    current, _previous, _window = _slice(file_id, user, query)
    return compute_inventory_intelligence(current)


@analytics_router.post("/{file_id}/forecast", response_model=ForecastResponse)
def post_forecast(file_id: str, query: ForecastQuery, user: str = Depends(get_current_user)):
    """Revenue projection with confidence band and backtested accuracy (Feature 2)."""
    current, _previous, _window = _slice(file_id, user, query)
    return compute_forecast(current, horizon_days=query.horizon)


@analytics_router.post("/{file_id}/report", response_model=CAReportSummary)
def post_ca_report(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """CA-style P&L + category ledger for a filtered slice."""
    current, _previous, window = _slice(file_id, user, query)
    return compute_pnl_report(current, window.label)


@analytics_router.post("/{file_id}/ledger", response_model=LedgerPage)
def post_ledger(file_id: str, query: LedgerQuery, user: str = Depends(get_current_user)):
    """
    One page of the transaction register for a filtered slice — this is what
    the chart drill-down opens when the user clicks a bar or a slice.
    """
    current, _previous, _window = _slice(file_id, user, query)
    return build_ledger_page(current, page=query.page, page_size=query.page_size)


@analytics_router.post("/{file_id}/report.pdf")
def post_ca_report_pdf(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """Detailed Financial Report PDF for the filtered slice."""
    return _render_pdf(file_id, user, query)


@analytics_router.post("/{file_id}/visual-report.pdf")
def post_visual_report_pdf(file_id: str, query: AnalysisQuery, user: str = Depends(get_current_user)):
    """One-page Visual Financial Report PDF for the filtered slice."""
    return _render_visual_pdf(file_id, user, query)


def _assert_report_consistency(analytics, ca_report, daily_summary: list[dict]) -> None:
    """Fail closed if the report's independent sections disagree."""
    revenue = round(float(analytics.summary.revenue.value), 2)
    profit = round(float(analytics.summary.profit.value), 2)
    cost = round(float(analytics.summary.cost.value), 2)
    units = int(analytics.summary.units_sold.value)

    pnl = {line.label: round(float(line.amount), 2) for line in ca_report.pnl}
    revenue_from_pnl = pnl.get("Net Revenue", pnl.get("Gross Revenue"))
    profit_from_pnl = pnl.get("Gross Profit")
    cost_from_pnl = pnl.get("Cost of Goods Sold (COGS)")

    if revenue_from_pnl != revenue or profit_from_pnl != profit or cost_from_pnl != cost:
        raise HTTPException(status_code=500, detail="Report generation stopped because dashboard and report values do not match.")

    category_revenue = round(sum(float(r.revenue) for r in ca_report.category_ledger), 2)
    category_cost = round(sum(float(r.cost) for r in ca_report.category_ledger), 2)
    category_profit = round(sum(float(r.profit) for r in ca_report.category_ledger), 2)
    category_units = sum(int(r.units_sold) for r in ca_report.category_ledger)
    if (category_revenue, category_cost, category_profit, category_units) != (revenue, cost, profit, units):
        raise HTTPException(status_code=500, detail="Report generation stopped because category totals do not reconcile with dashboard totals.")

    daily_revenue = round(sum(float(r["revenue"]) for r in daily_summary), 2)
    daily_cost = round(sum(float(r["cost"]) for r in daily_summary), 2)
    daily_profit = round(sum(float(r["profit"]) for r in daily_summary), 2)
    daily_units = sum(int(r["units_sold"]) for r in daily_summary)
    if (daily_revenue, daily_cost, daily_profit, daily_units) != (revenue, cost, profit, units):
        raise HTTPException(status_code=500, detail="Report generation stopped because daily totals do not reconcile with dashboard totals.")


# ── PDF assembly (shared by the classic GET and the Pro POST) ───────────────


def _render_visual_pdf(file_id: str, user: str, query: AnalysisQuery) -> Response:
    current, previous, window = _slice(file_id, user, query)
    analytics = _build_analytics(current, previous, window, _row_errors(file_id, user))
    ca_report = compute_pnl_report(current, window.label)
    daily_summary = compute_daily_financial_summary(current, window.start, window.end - timedelta(days=1))
    insights = compute_insights(current, previous, period_label=window.label)
    inventory = compute_inventory_intelligence(current, top_n=15)
    forecast = compute_forecast(current)

    _assert_report_consistency(analytics, ca_report, daily_summary)

    pdf_bytes = generate_visual_financial_pdf(
        filename=get_original_filename(file_id, fallback=file_id),
        analytics=analytics,
        ca_report=ca_report,
        daily_summary=daily_summary,
        insights=insights,
        inventory=inventory,
        forecast=forecast,
    )
    download_name = f"senova-visual-financial-report-{file_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


def _render_pdf(file_id: str, user: str, query: AnalysisQuery) -> Response:
    """
    Build the full PDF for a slice.

    The printed ledger is capped (see ``MAX_LEDGER_ROWS_IN_PDF``) because a
    50 000-row register would produce a document nobody can open, and the
    forecast/insight sections are computed from the same slice as the charts.
    """
    current, previous, window = _slice(file_id, user, query)

    analytics = _build_analytics(current, previous, window, _row_errors(file_id, user))
    ca_report = compute_pnl_report(current, window.label)
    # The PDF export is complete for the selected slice. The UI ledger remains
    # paginated, but the downloadable detailed report contains every selected row.
    ledger_page = build_ledger_page(current, page=1, page_size=max(1, len(current)))
    daily_summary = compute_daily_financial_summary(current, window.start, window.end - timedelta(days=1))
    insights = compute_insights(current, previous, period_label=window.label)
    inventory = compute_inventory_intelligence(current, top_n=15)
    forecast = compute_forecast(current)

    _assert_report_consistency(analytics, ca_report, daily_summary)

    pdf_bytes = generate_ca_report_pdf(
        filename=get_original_filename(file_id, fallback=file_id),
        analytics=analytics,
        ca_report=ca_report,
        ledger_entries=ledger_page.entries,
        ledger_total_rows=ledger_page.total_rows,
        insights=insights,
        inventory=inventory,
        forecast=forecast,
        daily_summary=daily_summary,
    )

    download_name = f"senova-detailed-financial-report-{file_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
