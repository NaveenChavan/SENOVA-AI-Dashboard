import os
import sys
from datetime import datetime

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

PRIMARY = colors.HexColor("#0F172A")
PRIMARY_LIGHT = colors.HexColor("#1E293B")
ACCENT = colors.HexColor("#2563EB")
ACCENT_LIGHT = colors.HexColor("#EFF6FF")
TEXT_DARK = colors.HexColor("#0F172A")
TEXT_MUTED = colors.HexColor("#475569")
BORDER_COLOR = colors.HexColor("#CBD5E1")
BG_LIGHT = colors.HexColor("#F8FAFC")

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(PRIMARY_LIGHT)
        self.drawString(54, 750, "SENOVA AI DASHBOARD")

        self.setFont("Helvetica", 8)
        self.setFillColor(TEXT_MUTED)
        self.drawString(170, 750, "— Master Preparation & Technical Architecture Reference")

        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.5)
        self.line(54, 744, 558, 744)

        self.line(54, 46, 558, 46)
        self.drawString(54, 34, "Confidential — Engineering Reference Manual")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 34, page_str)
        self.restoreState()


def build_pdf(output_path="docs/SENOVA_AI_Dashboard_Master_Guide.pdf"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=PRIMARY,
        spaceBefore=12,
        spaceAfter=5,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=ACCENT,
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=TEXT_DARK,
        spaceAfter=4
    )
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=TEXT_DARK,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )
    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=PRIMARY_LIGHT
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10.5,
        textColor=TEXT_DARK
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10.5,
        textColor=PRIMARY
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white
    )

    story = []

    # ── Top Banner ────────────────────────────────────────────────────────
    date_str = datetime.now().strftime("%B %d, %Y")
    p_title = Paragraph("<b>SENOVA AI DASHBOARD</b>", ParagraphStyle('BTitle', fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=colors.white))
    p_sub = Paragraph("<b>Master Preparation Guide</b>", ParagraphStyle('BSub', fontName='Helvetica', fontSize=10, leading=13, textColor=colors.HexColor("#93C5FD"), alignment=2))
    p_tag = Paragraph("Exhaustive Technical Reference • Mathematical Engines • Exact Function Breakdown", ParagraphStyle('BTag', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor("#E2E8F0")))
    p_date = Paragraph(f"Date: {date_str}", ParagraphStyle('BDate', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor("#CBD5E1"), alignment=2))

    banner_table = Table(
        [
            [p_title, p_sub],
            [p_tag, p_date]
        ],
        colWidths=[330, 174]
    )
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 8))

    # ── Core Architectural Guard Callout ──────────────────────────────────
    callout_content = [
        [Paragraph(
            "<b>Fundamental Architectural Invariant:</b> There is <b>NO Machine Learning (ML) model, LLM, or external cloud AI</b> "
            "in this codebase. 'Model' refers strictly to (1) Pydantic schemas (<code>backend/app/models/schemas.py</code>) and "
            "(2) deterministic mathematical/statistical formulas (Robust Z-Score via Median Absolute Deviation, Recency-Weighted "
            "Least Squares regression, Seasonal Indices) implemented with Pandas/NumPy. Every calculation is 100% auditable and reproducible.",
            callout_style
        )]
    ]
    callout_t = Table(callout_content, colWidths=[504])
    callout_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, ACCENT),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(callout_t)
    story.append(Spacer(1, 8))

    def add_h1(text):
        story.append(Paragraph(f"<b>{text}</b>", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=5, spaceBefore=2))

    def add_h2(text):
        story.append(Paragraph(f"<b>{text}</b>", h2_style))

    def add_p(text):
        story.append(Paragraph(text, body_style))

    def add_bullet(text):
        story.append(Paragraph(f"• {text}", bullet_style))

    # ── Section 0: Mental Model ───────────────────────────────────────────
    add_h1("0. System Mental Model & Data Flow")
    add_p(
        "A user uploads a sales CSV/Excel file → Backend guesses raw column mappings ('Date', 'Item', 'Selling Price', ...) "
        "→ User confirms or modifies mapping → Every row is validated, cleaned, and typed → Clean DataFrame is cached in a bounded "
        "LRU memory cache (keyed by file ID, mtime, and mapping signature) → Every dashboard view (KPI summary, charts, automated insights, "
        "inventory analytics, WLS forecast, P&L statement, PDF report) queries <b>one single slicing engine</b> (<code>query_engine.build_slice</code>) "
        "with identical time and dimension filters → The frontend renders interactive views via Recharts, or backend streams vector PDF via ReportLab. "
        "No database is required; uploads live on disk with a configurable TTL and are swept by a background task."
    )

    # ── Section 1: Tech Stack ─────────────────────────────────────────────
    add_h1("1. Complete Technology Stack & Dependencies")

    tech_data = [
        [Paragraph("Category", table_header), Paragraph("Package / Technology", table_header), Paragraph("Exact Role & Implementation Detail", table_header)],
        [Paragraph("<b>Backend Web</b>", table_cell_bold), Paragraph("FastAPI, Uvicorn, Pydantic v2", table_cell), Paragraph("Asynchronous REST API, strict request/response data contracts, auto OpenAPI schema docs.", table_cell)],
        [Paragraph("<b>Numeric Math</b>", table_cell_bold), Paragraph("Pandas, NumPy, openpyxl", table_cell), Paragraph("100% of data parsing, ledger math, robust statistics, WLS regression, and Excel ingestion.", table_cell)],
        [Paragraph("<b>Document Gen</b>", table_cell_bold), Paragraph("ReportLab (Platypus)", table_cell), Paragraph("Server-side vector PDF generation (A4), tables, summaries, and paginated transaction ledgers.", table_cell)],
        [Paragraph("<b>Authentication</b>", table_cell_bold), Paragraph("firebase-admin, SendGrid", table_cell), Paragraph("Server-side JWT token verification (revocation checks), branded password-reset email dispatch.", table_cell)],
        [Paragraph("<b>Testing (Py)</b>", table_cell_bold), Paragraph("pytest, pytest-asyncio", table_cell), Paragraph("139+ tests covering edge cases, math accuracy, IDOR security, and degenerate data frames.", table_cell)],
        [Paragraph("<b>Frontend Core</b>", table_cell_bold), Paragraph("React 18, Vite, React Router v7", table_cell), Paragraph("SPA client, lazy page loading, future flag compatibility, sub-second HMR dev server.", table_cell)],
        [Paragraph("<b>State Mgmt</b>", table_cell_bold), Paragraph("Zustand (3 stores)", table_cell), Paragraph("useSalesStore (data & abort controllers), useThemeStore (dark/light), useDensityStore.", table_cell)],
        [Paragraph("<b>Data Viz</b>", table_cell_bold), Paragraph("Recharts + Custom CSS Grid", table_cell), Paragraph("Chart Studio: 8 views (Bars, Donut, Combo, Pareto, Scatter, Treemap, Heatmap, Ranking).", table_cell)],
        [Paragraph("<b>Styling/UI</b>", table_cell_bold), Paragraph("Tailwind CSS, Motion v12", table_cell), Paragraph("Utility-first responsive styles, dark mode via data-theme attribute, non-intrusive DOM animations.", table_cell)]
    ]
    t_tech = Table(tech_data, colWidths=[80, 140, 284])
    t_tech.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('PADDING', (0, 0), (-1, -1), 3.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_tech)
    story.append(Spacer(1, 6))

    # ── Section 2: Repository Structure ───────────────────────────────────
    add_h1("2. Codebase Organization & Module Directory")
    file_map = [
        [Paragraph("File Path", table_header), Paragraph("Key Functions / Classes", table_header), Paragraph("Core Purpose & Mechanism", table_header)],
        [Paragraph("<code>app/main.py</code>", table_cell), Paragraph("<code>lifespan</code>, <code>_sweep_loop</code>", table_cell), Paragraph("FastAPI app factory, startup sweep, router registrations, CORS, /health.", table_cell)],
        [Paragraph("<code>app/core/config.py</code>", table_cell), Paragraph("Config constants, prod safety check", table_cell), Paragraph("Loads env vars, crashes startup if DISABLE_AUTH is active in production.", table_cell)],
        [Paragraph("<code>app/models/schemas.py</code>", table_cell), Paragraph("Pydantic models (Literal enums)", table_cell), Paragraph("Defines all API schemas with input bounds (TimeFilter, DimensionKey, MeasureKey).", table_cell)],
        [Paragraph("<code>app/api/routes/upload.py</code>", table_cell), Paragraph("<code>upload_file</code>, <code>confirm_mapping</code>", table_cell), Paragraph("2-step upload: preview mapping generation → normalization and caching.", table_cell)],
        [Paragraph("<code>app/api/routes/analytics.py</code>", table_cell), Paragraph("<code>get_summary</code>, <code>get_chart_data</code>, <code>get_insights</code>, etc.", table_cell), Paragraph("Exposes all Pro and classic analytics endpoints, backed by query_engine.", table_cell)],
        [Paragraph("<code>app/api/routes/auth.py</code>", table_cell), Paragraph("<code>forgot_password</code>", table_cell), Paragraph("Dispatches branded password reset links via SendGrid; anti-enumeration responses.", table_cell)],
        [Paragraph("<code>app/utils/data_validator.py</code>", table_cell), Paragraph("<code>detect_column_mapping</code>, <code>normalize_dataframe</code>", table_cell), Paragraph("180+ alias map + fuzzy matching, currency symbol stripping, ISO date parsing.", table_cell)],
        [Paragraph("<code>app/services/frame_cache.py</code>", table_cell), Paragraph("<code>get_or_set</code>, <code>invalidate</code>, <code>_get_key_lock</code>", table_cell), Paragraph("Bounded LRU DataFrame cache (max 3 frames, max 120k rows) with stampede locks.", table_cell)],
        [Paragraph("<code>app/services/query_engine.py</code>", table_cell), Paragraph("<code>build_slice</code>, <code>resolve_window</code>, <code>apply_filters</code>, <code>aggregate</code>", table_cell), Paragraph("Single chokepoint for data slicing, window bounds, multi-measure aggregation.", table_cell)],
        [Paragraph("<code>app/services/sales_calculations.py</code>", table_cell), Paragraph("<code>_prepare</code>, <code>compute_pnl_report</code>, <code>build_ledger_page</code>", table_cell), Paragraph("Gross/Net revenue derivation, Chartered Accountant P&L, category ledgers.", table_cell)],
        [Paragraph("<code>app/services/insights_engine.py</code>", table_cell), Paragraph("<code>compute_insights</code> (6 checks)", table_cell), Paragraph("MAD-based anomaly detection, top movers, margin leaks, concentration, timing.", table_cell)],
        [Paragraph("<code>app/services/forecasting.py</code>", table_cell), Paragraph("<code>forecast_revenue</code>, <code>_fit_wls</code>, <code>_seasonal_indices</code>", table_cell), Paragraph("Recency-weighted least squares (14d half-life), median seasonality, 80% intervals.", table_cell)],
        [Paragraph("<code>app/services/inventory_intel.py</code>", table_cell), Paragraph("<code>compute_inventory_intelligence</code>", table_cell), Paragraph("Demand vs stock-aware modes, ABC Pareto class, velocity, reorder priority (0-100).", table_cell)],
        [Paragraph("<code>app/services/pdf_report.py</code>", table_cell), Paragraph("<code>generate_pdf_report</code>", table_cell), Paragraph("Platypus multi-page PDF generation with findings, P&L, forecast, and ledger.", table_cell)],
        [Paragraph("<code>app/utils/auth_verifier.py</code>", table_cell), Paragraph("<code>get_current_user</code>, <code>get_firebase_app</code>", table_cell), Paragraph("Firebase ID token verification, revocation check, dev-mode bypass injection.", table_cell)]
    ]
    t_files = Table(file_map, colWidths=[125, 140, 239])
    t_files.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_files)
    story.append(Spacer(1, 8))

    # ── Section 3 & 4: Startup & Configuration ────────────────────────────
    add_h1("3 & 4. Backend Startup, Lifecycle & Configuration")
    add_h2("Startup Sequence & Prod Safety Guard")
    add_bullet("<b>Module Import Guard:</b> At import time, <code>config.py</code> verifies: <code>if DISABLE_AUTH and ENV == 'production': raise RuntimeError('DISABLE_AUTH cannot be True in production')</code>. Prevents accidental insecure deployments.")
    add_bullet("<b>Async Lifespan:</b> Runs <code>sweep_expired_uploads()</code> immediately on startup to clean remnants from previous restarts, then launches <code>_sweep_loop()</code> in a background task running every <code>UPLOAD_SWEEP_INTERVAL_MINUTES</code> (default 30 min).")
    add_bullet("<b>CORS & Middleware:</b> Configures <code>CORSMiddleware</code> with <code>ALLOWED_ORIGINS</code> (env-driven). Real authorization is enforced per-endpoint via Firebase ID token verification.")

    add_h2("Configuration Reference (`config.py`)")
    config_data = [
        [Paragraph("Constant", table_header), Paragraph("Env Variable", table_header), Paragraph("Default", table_header), Paragraph("Description & Impact", table_header)],
        [Paragraph("<code>ALLOWED_ORIGINS</code>", table_cell), Paragraph("<code>CORS_ORIGINS</code>", table_cell), Paragraph("localhost:5173", table_cell), Paragraph("Comma-separated list of allowed frontend origins.", table_cell)],
        [Paragraph("<code>MAX_UPLOAD_SIZE_MB</code>", table_cell), Paragraph("same", table_cell), Paragraph("50", table_cell), Paragraph("Rejects files exceeding this size with HTTP 413.", table_cell)],
        [Paragraph("<code>UPLOAD_TTL_MINUTES</code>", table_cell), Paragraph("same", table_cell), Paragraph("120", table_cell), Paragraph("File retention window before automated deletion.", table_cell)],
        [Paragraph("<code>FRAME_CACHE_MAX_ENTRIES</code>", table_cell), Paragraph("same", table_cell), Paragraph("3", table_cell), Paragraph("LRU cache capacity (tuned for 512MB RAM hosts).", table_cell)],
        [Paragraph("<code>FRAME_CACHE_MAX_ROWS</code>", table_cell), Paragraph("same", table_cell), Paragraph("120000", table_cell), Paragraph("DataFrames above this limit are parsed on demand and never cached.", table_cell)],
        [Paragraph("<code>FIREBASE_PROJECT_ID</code>", table_cell), Paragraph("same", table_cell), Paragraph("senova-dashboard", table_cell), Paragraph("Verifies Firebase token audience.", table_cell)]
    ]
    t_cfg = Table(config_data, colWidths=[120, 110, 80, 194])
    t_cfg.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_cfg)
    story.append(Spacer(1, 8))

    # ── Section 5 & 6: Ingestion & Validation ─────────────────────────────
    add_h1("5 & 6. Upload Pipeline, Alias Resolution & Data Sanitization")
    add_h2("Two-Step Upload Flow")
    add_bullet("<b>Step 1 — Preview (POST /upload/):</b> Receives file, validates size (≤50MB) and extension (.csv/.xlsx). Generates a 32-char hex UUID (file_id) and writes `{file_id}{ext}` and `{file_id}.meta.json`. Sniffs delimiter and reads via utf-8-sig (falling back to latin-1 for legacy POS systems). Runs column guesser and returns 5 sample rows.")
    add_bullet("<b>Step 2 — Confirmation (POST /upload/{file_id}/confirm-mapping):</b> Validates file ID regex (`^[0-9a-f]{32}$`), asserts ownership (unified 404 for security), normalizes DataFrame, writes mapping sidecar, invalidates LRU frame cache, and returns summary stats.")

    add_h2("Column Resolution & Math Rules (`data_validator.py`)")
    add_bullet("<b>18 Canonical Fields:</b> 6 Required (<code>Date, Category, Item, Quantity, Selling Price, Cost Price</code>), 4 Optional Measures (<code>Line Total, Discount, Tax, Stock On Hand</code>), 8 Optional Dimensions (<code>Branch, Payment Mode, Customer, Salesperson, Brand, Size, Colour, Invoice No</code>).")
    add_bullet("<b>Alias Resolution:</b> 2-tier check: (1) Exact alias map (180+ variations: 'Bill Date', 'MRP', 'Taxable Value', 'Stock Group', etc.), (2) Fuzzy keyword fallback. De-duplicates guesses so two raw columns never map to the same field.")
    add_bullet("<b>Line Total Derivation Rule:</b> Columns like 'Amount', 'Net Amount', or 'Taxable Value' represent `Quantity × Unit Price`. They map to <code>Line Total</code>, and `Selling Price` is derived as `Line Total / Quantity` (for Quantity > 0). This prevents massive revenue calculation errors.")
    add_bullet("<b>Numeric Coercion (<code>_coerce_numeric</code>):</b> Coerces via Pandas, then strips currency symbols (`₹, $, €, £, ,`) and whitespace. Maps `inf/-inf` to NaN.")
    add_bullet("<b>Date Parsing (<code>_parse_dates</code>):</b> Prioritizes ISO dates (`YYYY-MM-DD`) without `dayfirst` flag, then falls back to `dayfirst=True` (DD-MM-YYYY) for remaining rows. This prevents 2026-04-05 from flipping between April 5 and May 4.")
    add_bullet("<b>Business Rules:</b> Drops rows with `Quantity <= 0`, `Selling Price < 0`, `Cost Price < 0`. Allows `Cost Price > Selling Price` (clearance sales needed for margin leak detection). Blank `Stock On Hand` is left as NaN (never 0, which would fake stockouts).")
    story.append(Spacer(1, 8))

    # ── Section 7: Caching Architecture ───────────────────────────────────
    add_h1("7. Bounded LRU Frame Cache (`frame_cache.py`)")
    add_p(
        "To prevent duplicate parsing of 50k-row Excel/CSV files across parallel API queries, "
        "the backend implements a custom thread-safe LRU cache with stampede protection:"
    )
    add_bullet("<b>Composite Cache Key:</b> <code>(file_id, get_file_mtime(file_id), _mapping_signature(mapping))</code>. Any re-upload or modified column mapping automatically creates a fresh key.")
    add_bullet("<b>Cache Stampede Mutex (<code>_get_key_lock</code>):</b> When dashboard tabs fire 5 simultaneous requests on cold cache, threads lock on the specific key. The first thread parses and caches; remaining threads read the cached result instantly.")
    add_bullet("<b>Capacity Bounds:</b> Default 3 entries (LRU eviction via <code>OrderedDict.popitem(last=False)</code>). Frames > 120,000 rows bypass cache to prevent memory exhaustion on small 512MB RAM hosts.")
    story.append(Spacer(1, 8))

    # ── Section 8: Authentication ─────────────────────────────────────────
    add_h1("8. Authentication & Anti-Enumeration Security")
    add_bullet("<b>Firebase Token Verification (<code>auth_verifier.py</code>):</b> Injected via FastAPI <code>Depends(get_current_user)</code>. Executes <code>firebase_auth.verify_id_token(token, check_revoked=True)</code> to verify signature, audience, and revocation. Returns user email or UID.")
    add_bullet("<b>Dev Bypass:</b> When <code>DISABLE_AUTH=True</code>, returns <code>'dev-user@localhost'</code> without calling Firebase. Hard-blocked from running in production.")
    add_bullet("<b>Unified 404 Ownership Checks:</b> Malformed file ID, non-existent file, and file belonging to another user all return identical <b>404 File Not Found</b> responses. Prevents unauthorized ID enumeration.")
    add_bullet("<b>Branded Password Reset (<code>api/routes/auth.py</code>):</b> Generates Firebase single-use action code (1-hour validity), extracts `oobCode`, and sends a branded link via SendGrid. Always returns 200 with identical text to prevent user account enumeration.")
    story.append(Spacer(1, 8))

    # ── Section 9: Query Engine & Sales Calculations ──────────────────────
    add_h1("9. Query Engine Slicing & Sales Ledger Math")
    add_h2("Single Slicing Chokepoint (`query_engine.py`)")
    add_bullet("<b><code>build_slice(df, time_filter, start_date, end_date, filters)</code>:</b> Resolves window, filters data, and extracts equal-length previous period. Used by all endpoints to guarantee 100% data consistency.")
    add_bullet("<b>Window Presets:</b> Anchored to <code>df.Date.max()</code> (not server clock). Today = `[max, max+1d)`, Week = `[max-6d, max+1d)`, 30 Days = `[max-29d, max+1d)`, Month = `[1st of month, max+1d)`. Custom = `[start, end+1d)`. All presets compute an equal-length preceding period for trend comparisons.")
    add_bullet("<b>Safe Filtering (<code>apply_filters</code>):</b> Evaluates dimensions using <code>df[col].astype(str).isin(set(values))</code>. No dynamic string evaluation.")
    add_bullet("<b>Universal Aggregator (<code>aggregate</code>):</b> Computes Revenue, Cost, Profit, Units, Transactions, Discounts, Margin %, Avg Price in one pass. Calculates Pareto 80% concentration count and folds long-tail items into `Other (N)`.")

    add_h2("KPIs & Ledger Calculations (`sales_calculations.py`)")
    add_bullet("<b>Net Revenue Derivation (<code>_prepare</code>):</b> <code>gross_revenue = Quantity * Selling Price</code>; <code>revenue = max(gross - discount, 0)</code>; <code>cost = Quantity * Cost Price</code>; <code>profit = revenue - cost</code>.")
    add_bullet("<b>Tax Isolation:</b> GST/Tax is tracked separately and excluded from profit ('GST collected is a liability, not income').")
    add_bullet("<b>Trend Percentage:</b> <code>((current - previous) / previous) * 100</code>; returns 0.0 if previous is 0.")
    add_bullet("<b>P&L Statement:</b> Constructs formal CA-ready financial statement with Gross Sales, Discounts Allowed, Net Revenue, COGS, Gross Profit, and Tax Memo.")
    story.append(Spacer(1, 8))

    # ── Section 10: Intelligence Engines ──────────────────────────────────
    add_h1("10. Detailed Mathematical Intelligence Engines")

    add_h2("10.1 Automated Insights Engine (`insights_engine.py`) — 6 Statistical Checks")
    add_bullet("<b>1. Anomaly Detection (Robust Z-Score):</b> Computes <code>z = 0.6745 * (x - median) / MAD</code> where <code>MAD = median(|x - median|)</code>. Requires ≥7 days. If >25% days have zero revenue, baseline switches to trading-days-only to prevent median collapsing to 0. Thresholds: `|z| >= 3.0` (Critical Anomaly), `|z| >= 2.0` (Warning/Spike).")
    add_bullet("<b>2. Top Movers:</b> Evaluates items present in both current and previous windows. Ranked by <b>absolute rupee revenue delta</b> (not percentage), preventing tiny ₹50 items with 300% spikes from overshadowing a ₹50,000 drop.")
    add_bullet("<b>3. Margin Leak:</b> Evaluates items contributing ≥3% of total revenue. Flags items whose margin is ≥10.0% points below the category median (or store median). Negative margin items are prioritized (`gap = |margin| + 100`).")
    add_bullet("<b>4. Revenue Concentration:</b> Evaluates Pareto 80/20 rule using `cumulative_before` threshold (requires ≥8 items). Flags if ≤20% of inventory drives ≥80% of revenue.")
    add_bullet("<b>5. Timing (Weekday Variations):</b> Computes mean revenue per weekday (requires ≥2 observations per day). Flags if <code>mean_rev(best_day) / mean_rev(worst_day) >= 1.30</code>.")
    add_bullet("<b>6. Dead Stock:</b> Identifies items with 0 sales in the last ≥30 days (`days_since_last_sale = max_date - last_sale_date`), sorted by idle days descending.")

    add_h2("10.2 Forecasting Engine (`forecasting.py`) — WLS & Seasonal Index")
    add_bullet("<b>Data Guard:</b> Refuses forecast if history < 14 days. Uses trend-only (no seasonality) for 14–21 days of data.")
    add_bullet("<b>Recency-Weighted Least Squares (WLS):</b> Applies exponential decay weights: <code>w_i = 0.5 ** (age_days / 14)</code> (14-day half-life). Fits linear trend y = alpha + beta * t minimizing weighted squared residuals.")
    add_bullet("<b>Median Weekday Seasonality:</b> Computes detrended ratio <code>actual / trend_fit</code>, calculates the <b>median ratio per weekday</b>, normalizes indices to mean 1.0, and clamps to <code>[0.3, 3.0]</code> to avoid holiday distortion.")
    add_bullet("<b>Projection & Confidence Bounds:</b> Point forecast = <code>max(trend_t * seasonal_idx, 0)</code>. 80% confidence interval width = <code>1.2816 * sigma_residual * sqrt(1 + step / history_days)</code>.")
    add_bullet("<b>Holdout Backtesting (7 Days):</b> Measures accuracy on held-out 7 days. Normal series: <code>Accuracy = clamp(100 - MAPE, 0, 100)</code> where <code>MAPE = mean(|actual - pred| / actual) * 100</code>. Sparse series (>25% zero days): scores total volume accuracy <code>100 - |sum(pred) - sum(act)| / sum(act) * 100</code>.")

    add_h2("10.3 Inventory Intelligence (`inventory_intel.py`)")
    add_bullet("<b>Dual Operational Modes:</b> Demand Mode (sales only) vs Stock-Aware Mode (when `Stock On Hand` is provided).")
    add_bullet("<b>Velocity:</b> <code>velocity_per_day = units / window_days</code> and <code>velocity_active_days = units / active_days</code>.")
    add_bullet("<b>ABC Classification:</b> A (Top 80% cumulative revenue), B (Next 15% revenue), C (Remaining 5% revenue).")
    add_bullet("<b>Stock Ageing Buckets:</b> Fresh (<15 days idle), Slow (15–29 days), Stale (30–59 days), Dead (≥60 days idle).")
    add_bullet("<b>Reorder Priority Score (0–100):</b> <code>100 * (0.50 * velocity_norm + 0.30 * trend_norm + 0.20 * recency_norm)</code>.")
    add_bullet("<b>Stock-Aware Metrics:</b> <code>Days of Cover = stock_on_hand / velocity_per_day</code>; <code>Capital Locked = stock_on_hand * avg_cost_price</code>; <code>Reorder Flag = days_of_cover < 7 days</code>.")
    story.append(Spacer(1, 8))

    # ── Section 11: PDF Generator ─────────────────────────────────────────
    add_h1("11. Server-Side PDF Report Generator (`pdf_report.py`)")
    add_p(
        "Generates clean, professional A4 vector PDF documents using ReportLab Platypus. "
        "Every metric is computed from the same <code>build_slice</code> call, ensuring 100% visual parity with the screen:"
    )
    add_bullet("<b>1. Header & Summary:</b> Report title, original filename, active time filter, and date range.")
    add_bullet("<b>2. Automated Findings:</b> Insights printed first with text-based severity badges (`URGENT`, `WATCH`, `GOOD`, `NOTE`) for photocopy readability.")
    add_bullet("<b>3. Financial P&L Statement:</b> Formal financial layout with Gross Sales, Discounts, Net Revenue, COGS, Gross Profit, and Tax Liability Memo.")
    add_bullet("<b>4. Category Ledger & Forecast:</b> Revenue breakdown by category and 7–30 day forward forecast.")
    add_bullet("<b>5. Inventory Reorder & Dead Stock:</b> Top 20 items ranked by Reorder Priority and dead stock table.")
    add_bullet("<b>6. Paginated Transaction Ledger:</b> Capped at 500 rows (`MAX_LEDGER_ROWS_IN_PDF`) with overflow notification.")
    story.append(Spacer(1, 8))

    # ── Section 12: API Surface ───────────────────────────────────────────
    add_h1("12. Complete Backend REST API Reference")
    api_table_data = [
        [Paragraph("Method & Endpoint", table_header), Paragraph("Request Body / Params", table_header), Paragraph("Response Model", table_header), Paragraph("Functional Description", table_header)],
        [Paragraph("<code>POST /upload/</code>", table_cell), Paragraph("multipart file", table_cell), Paragraph("<code>ColumnMappingPreview</code>", table_cell), Paragraph("Uploads file, sniffs delimiter, returns preview & 5 sample rows.", table_cell)],
        [Paragraph("<code>POST /upload/{id}/confirm-mapping</code>", table_cell), Paragraph("<code>{mapping: dict}</code>", table_cell), Paragraph("<code>UploadResponse</code>", table_cell), Paragraph("Validates rows, saves mapping sidecar, primes LRU frame cache.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/summary</code>", table_cell), Paragraph("<code>AnalysisQuery</code>", table_cell), Paragraph("<code>AnalyticsResponse</code>", table_cell), Paragraph("KPI summary (Revenue, Profit, Margin %, Units, Trends, Top Items).", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/chart-data</code>", table_cell), Paragraph("<code>ChartQuery</code>", table_cell), Paragraph("<code>ChartDataResponse</code>", table_cell), Paragraph("Universal dimension aggregator with Pareto 80% and long-tail folding.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/heatmap</code>", table_cell), Paragraph("<code>ChartQuery</code>", table_cell), Paragraph("<code>HeatmapResponse</code>", table_cell), Paragraph("Weekday x ISO-Week matrix with numeric min/max bounds.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/insights</code>", table_cell), Paragraph("<code>AnalysisQuery</code>", table_cell), Paragraph("<code>InsightsResponse</code>", table_cell), Paragraph("Runs all 6 statistical finding checks and returns prioritized cards.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/forecast</code>", table_cell), Paragraph("<code>ForecastQuery</code>", table_cell), Paragraph("<code>ForecastResponse</code>", table_cell), Paragraph("WLS trend projection, confidence intervals, MAPE backtest score.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/inventory</code>", table_cell), Paragraph("<code>AnalysisQuery</code>", table_cell), Paragraph("<code>InventoryResponse</code>", table_cell), Paragraph("Velocity, ABC classification, ageing buckets, reorder priority scores.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/report</code>", table_cell), Paragraph("<code>AnalysisQuery</code>", table_cell), Paragraph("<code>CAReportSummary</code>", table_cell), Paragraph("Chartered Accountant P&L statement, revenue breakdown, category ledger.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/report.pdf</code>", table_cell), Paragraph("<code>AnalysisQuery</code>", table_cell), Paragraph("<code>application/pdf</code> bytes", table_cell), Paragraph("Generates and streams downloadable ReportLab PDF file.", table_cell)],
        [Paragraph("<code>POST /analytics/{id}/ledger</code>", table_cell), Paragraph("<code>LedgerQuery</code>", table_cell), Paragraph("<code>LedgerPage</code>", table_cell), Paragraph("Paginated, sorted raw transaction ledger with date/column filters.", table_cell)],
        [Paragraph("<code>POST /auth/forgot-password</code>", table_cell), Paragraph("<code>{email: str}</code>", table_cell), Paragraph("<code>ForgotPasswordResponse</code>", table_cell), Paragraph("Generates Firebase action code, sends branded email via SendGrid.", table_cell)],
        [Paragraph("<code>GET /health</code>", table_cell), Paragraph("None", table_cell), Paragraph("<code>{status: 'ok'}</code>", table_cell), Paragraph("Public health check endpoint for deployment monitoring.", table_cell)]
    ]
    t_api = Table(api_table_data, colWidths=[130, 95, 110, 169])
    t_api.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_api)
    story.append(Spacer(1, 8))

    # ── Section 13: Frontend Architecture ─────────────────────────────────
    add_h1("13. Frontend Architecture & State Management")
    add_bullet("<b>Zustand Stores:</b> <code>useSalesStore</code> manages global query state (`{timeFilter, startDate, endDate, filters}`), upload state, and cancellable fetchers with <code>AbortController</code> to prevent race conditions on fast filter toggles. <code>useThemeStore</code> and <code>useDensityStore</code> control UI theme and compact layout.")
    add_bullet("<b>URL as Source of Truth:</b> <code>Dashboard.jsx</code> synchronizes state with URL search params (`range, from, to, filters`). Allows users to share exact filtered views with accountants.")
    add_bullet("<b>Chart Studio (8 Views, 1 Payload):</b> <code>chartView.js</code> turns view configurations into API requests. Because <code>query_engine.aggregate</code> precomputes all measures in a single response, toggling chart views (Bar, Donut, Pareto, Ranking, etc.) switches components instantly without extra network round trips.")
    add_bullet("<b>Drill-Down Capabilities:</b> Clicking any chart element or table row opens <code>DrillDownPanel</code>, fetching filtered transaction lines directly from <code>/ledger</code>.")
    story.append(Spacer(1, 8))

    # ── Section 14: Testing ───────────────────────────────────────────────
    add_h1("14. Test Suite Coverage & Verification")
    add_p(
        "The backend test suite consists of <b>139 test functions across 10 test files</b> in <code>backend/tests/</code>:"
    )
    add_bullet("<code>test_data_validator.py</code>: 180+ alias maps, fuzzy resolution, Line Total unit price derivation, numeric cleaning, ISO date parsing.")
    add_bullet("<code>test_query_engine.py</code>: Window resolution (presets anchored to max date), safe filtering, Pareto concentration, heatmap matrix.")
    add_bullet("<code>test_insights_engine.py</code>: All 6 statistical checks, MAD anomaly detection, single-item catalog edge cases.")
    add_bullet("<code>test_forecasting.py</code>: WLS slope/intercept, 14-day history guard, median weekday seasonality, 80% confidence bands, MAPE backtesting.")
    add_bullet("<code>test_inventory_and_forecast.py</code>: ABC cumulative revenue threshold, velocity metrics, reorder priority scoring.")
    add_bullet("<code>test_api.py</code>: Complete upload → confirm → analytics workflow, IDOR ownership verification, 404 security checks.")
    add_bullet("<code>test_accuracy_audit.py</code>: Independent re-computation audit comparing engine outputs against raw unoptimized Pandas formulas.")
    add_bullet("<code>test_edge_cases.py</code>: Degenerate inputs (1-row files, all-zero revenue, infinite values, negative margins).")
    story.append(Spacer(1, 8))

    # ── Section 15: Documentation Discrepancies ───────────────────────────
    add_h1("15. Known Documentation Discrepancies (Code vs Docs)")
    add_p("Audited discrepancies between existing markdown docs and actual codebase implementation:")
    add_bullet("<b>1. Test Count Drift:</b> README notes 132 tests; direct source count has 139 test functions; older UI doc notes 177. (Caused by pytest parametrization expansion and test suite growth).")
    add_bullet("<b>2. Auth Routes Undocumented:</b> <code>app/api/routes/auth.py</code> and <code>email_service.py</code> are fully implemented with 19 tests, but missing from earlier architecture markdown documents.")
    add_bullet("<b>3. Design Proposal vs Code:</b> <code>docs/UPGRADES.md</code> describes WhatsApp sharing and persistent database history as future proposals — they are design specs and not implemented.")
    story.append(Spacer(1, 8))

    # ── Section 16: Magic Numbers Quick Reference ─────────────────────────
    add_h1("16. System Constants & Mathematical Parameters Reference")

    magic_data = [
        [Paragraph("Constant / Parameter", table_header), Paragraph("Value", table_header), Paragraph("File Location", table_header), Paragraph("Exact Mathematical Purpose", table_header)],
        [Paragraph("<code>MAD_TO_SIGMA_SCALE</code>", table_cell), Paragraph("0.6745", table_cell), Paragraph("<code>insights_engine.py</code>", table_cell), Paragraph("Scales Median Absolute Deviation to normal distribution standard deviation (1 / 1.4826).", table_cell)],
        [Paragraph("<code>ANOMALY_THRESHOLDS</code>", table_cell), Paragraph("3.0 / 2.0", table_cell), Paragraph("<code>insights_engine.py</code>", table_cell), Paragraph("Z-score thresholds for Critical Anomaly (z>=3.0) and Warning Spike/Drop (z>=2.0).", table_cell)],
        [Paragraph("<code>SPARSE_ZERO_THRESHOLD</code>", table_cell), Paragraph("0.25 (25%)", table_cell), Paragraph("<code>insights, forecasting</code>", table_cell), Paragraph("Switches to trading-days-only stats if >25% calendar days have zero revenue.", table_cell)],
        [Paragraph("<code>MARGIN_LEAK_THRESHOLDS</code>", table_cell), Paragraph("3% rev, 10% gap", table_cell), Paragraph("<code>insights_engine.py</code>", table_cell), Paragraph("Flags items with >=3% revenue share whose margin is >=10.0% pts below median.", table_cell)],
        [Paragraph("<code>CONCENTRATION_THRESHOLDS</code>", table_cell), Paragraph("20% items, 80% rev", table_cell), Paragraph("<code>insights_engine.py</code>", table_cell), Paragraph("Flags concentration if <=20% of catalog items generate >=80% of total revenue.", table_cell)],
        [Paragraph("<code>WEEKDAY_RATIO_THRESHOLD</code>", table_cell), Paragraph("1.30 (30%)", table_cell), Paragraph("<code>insights_engine.py</code>", table_cell), Paragraph("Flags timing insight if best weekday average revenue is >=30% higher than worst.", table_cell)],
        [Paragraph("<code>DEAD_STOCK_DAYS</code>", table_cell), Paragraph("30 days", table_cell), Paragraph("<code>insights, sales_calc</code>", table_cell), Paragraph("Threshold for dead stock inactivity.", table_cell)],
        [Paragraph("<code>FORECAST_MIN_HISTORY</code>", table_cell), Paragraph("14 days", table_cell), Paragraph("<code>forecasting.py</code>", table_cell), Paragraph("Refuses forecast below 14 days; requires 21 days for weekday seasonality.", table_cell)],
        [Paragraph("<code>WLS_HALF_LIFE</code>", table_cell), Paragraph("14 days", table_cell), Paragraph("<code>forecasting.py</code>", table_cell), Paragraph("Exponential weight decay half-life: w = 0.5 ** (age / 14).", table_cell)],
        [Paragraph("<code>SEASONAL_INDEX_CLAMP</code>", table_cell), Paragraph("[0.3, 3.0]", table_cell), Paragraph("<code>forecasting.py</code>", table_cell), Paragraph("Bounds seasonal multiplier to prevent extreme single-day holiday distortion.", table_cell)],
        [Paragraph("<code>CONFIDENCE_Z_80PCT</code>", table_cell), Paragraph("1.2816", table_cell), Paragraph("<code>forecasting.py</code>", table_cell), Paragraph("Z-multiplier for 80% two-sided forecast prediction interval.", table_cell)],
        [Paragraph("<code>BACKTEST_HOLDOUT_DAYS</code>", table_cell), Paragraph("7 days", table_cell), Paragraph("<code>forecasting.py</code>", table_cell), Paragraph("Holdout period used to evaluate forecast MAPE accuracy score.", table_cell)],
        [Paragraph("<code>ABC_BOUNDARIES</code>", table_cell), Paragraph("80% / 95%", table_cell), Paragraph("<code>inventory_intel.py</code>", table_cell), Paragraph("Cumulative revenue share split: Class A (<80%), Class B (<95%), Class C (rest).", table_cell)],
        [Paragraph("<code>AGEING_BUCKETS</code>", table_cell), Paragraph("15 / 30 / 60 days", table_cell), Paragraph("<code>inventory_intel.py</code>", table_cell), Paragraph("Inventory status: Fresh (<15d), Slow (<30d), Stale (<60d), Dead (>=60d).", table_cell)],
        [Paragraph("<code>REORDER_WEIGHTS</code>", table_cell), Paragraph("0.50 / 0.30 / 0.20", table_cell), Paragraph("<code>inventory_intel.py</code>", table_cell), Paragraph("Weights for Reorder Score: Velocity (50%), Trend (30%), Recency (20%).", table_cell)],
        [Paragraph("<code>REORDER_COVER_DAYS</code>", table_cell), Paragraph("7 days", table_cell), Paragraph("<code>inventory_intel.py</code>", table_cell), Paragraph("Days of cover threshold (<7 days triggers reorder flag).", table_cell)],
        [Paragraph("<code>MAX_UPLOAD_SIZE_MB</code>", table_cell), Paragraph("50 MB", table_cell), Paragraph("<code>config.py</code>", table_cell), Paragraph("Maximum allowable file upload size.", table_cell)],
        [Paragraph("<code>UPLOAD_TTL_MINUTES</code>", table_cell), Paragraph("120 min", table_cell), Paragraph("<code>config.py</code>", table_cell), Paragraph("File retention window on disk before background task purge.", table_cell)],
        [Paragraph("<code>FRAME_CACHE_LIMITS</code>", table_cell), Paragraph("3 frames / 120k rows", table_cell), Paragraph("<code>config.py</code>", table_cell), Paragraph("Memory bounds for in-memory LRU DataFrame cache.", table_cell)],
        [Paragraph("<code>MAX_LEDGER_ROWS_IN_PDF</code>", table_cell), Paragraph("500 rows", table_cell), Paragraph("<code>pdf_report.py</code>", table_cell), Paragraph("Maximum raw transaction rows rendered into the exported PDF ledger.", table_cell)]
    ]
    t_magic = Table(magic_data, colWidths=[125, 80, 100, 199])
    t_magic.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t_magic)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Master preparation PDF generated successfully at: {output_path}")


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "docs/SENOVA_AI_Dashboard_Master_Guide.pdf"
    build_pdf(out_file)
