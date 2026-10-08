# SENOVA AI Dashboard — PDF Report Generation Pipeline

This folder contains all files from the SENOVA AI Dashboard codebase related to PDF report generation, covering both Frontend and Backend, as well as test suites and documentation.

---

## 📂 File Manifest & Descriptions

### 1. Core Backend PDF Generation
- **`backend/app/services/pdf_report.py`**
  - **Role**: Core PDF document generation engine using **ReportLab** (`SimpleDocTemplate`, `Table`, `TableStyle`, `Paragraph`, `Spacer`, `PageBreak`).
  - **Key Function**: `generate_ca_report_pdf(...)`
  - **Output**: Generates a professional, Chartered Accountant (CA) style printable and selectable financial report.
  - **Sections generated**:
    1. Title & Header metadata (File name, reporting window, generated timestamp).
    2. Executive Summary & KPIs (Revenue, Profit, Margin %, Transaction count).
    3. Profit & Loss (P&L) Statement table.
    4. Category-wise sales & revenue breakdown table.
    5. Inventory & Reorder Intelligence (Fast moving, dead stock, reorder flags).
    6. Sales Forecasting section (Expected revenue, trend factors).
    7. Automated AI Insights & Anomaly findings.
    8. Transaction Ledger Register (capped at `MAX_LEDGER_ROWS_IN_PDF = 500` to prevent unprintable huge PDFs).

### 2. Backend API Routes & Slicing
- **`backend/app/api/routes/analytics.py`**
  - **Role**: FastAPI controller handling HTTP requests for PDF downloads.
  - **Key Routes**:
    - `POST /analytics/{file_id}/report.pdf` (Pro route accepting an `AnalysisQuery` with custom date range and dimension filters).
    - `GET /analytics/{file_id}/report.pdf` (Classic route accepting `time_filter` preset).
  - **Key Function**: `_render_pdf(file_id, user, query)`:
    - Slices dataset using `_slice(file_id, user, query)`.
    - Computes analytics summary and P&L using `compute_pnl_report()`.
    - Fetches capped ledger rows via `build_ledger_page()`.
    - Calls `generate_ca_report_pdf(...)`.
    - Returns `fastapi.Response` with `media_type="application/pdf"` and `Content-Disposition: attachment; filename="senova-financial-report-...pdf"`.

### 3. Business Logic & Calculations Feeding PDF
- **`backend/app/services/sales_calculations.py`**
  - **Role**: Computes the numerical figures formatted inside the PDF.
  - **Key Functions**:
    - `compute_pnl_report(...)`: Calculates Revenue, COGS, Gross Profit, Expenses, Net Profit, and Margin %.
    - `build_ledger_page(...)`: Prepares transaction ledger rows for the PDF table.
- **`backend/app/models/schemas.py`**
  - **Role**: Data contracts and schemas.
  - **Key Models**: `CAReportSummary`, `AnalyticsResponse`, `AnalysisQuery`, `LedgerPage`, `FinancialKPISummary`.

### 4. Frontend PDF Export & UI Triggers
- **`frontend/src/pages/Dashboard.jsx`**
  - **Role**: Main UI view where the user clicks to download the PDF.
  - **Key Functions & UI Elements**:
    - `exportPDF()`: Async handler that triggers `api.post('/analytics/${fileId}/report.pdf', buildQueryBody(query), { responseType: 'blob' })`.
    - Creates a Blob URL (`URL.createObjectURL(response.data)`) and programmatically triggers a browser download link.
    - Export button in toolbar: `<button onClick={exportPDF} disabled={exporting}>... Export PDF ...</button>`.
    - Command Palette (`⌘K / Ctrl+K`): "Download the printed sales & P&L report (PDF)" action item.
- **`frontend/src/services/api.js`**
  - **Role**: Axios HTTP client configured with base URL and JWT authentication interceptors.

### 5. Automated Tests Verifying PDF Export
- **`backend/tests/test_api.py`**
  - **Test**: `test_pdf_export_builds`:
    - Posts to `/analytics/{file_id}/report.pdf`.
    - Asserts HTTP 200.
    - Asserts `content-type == "application/pdf"`.
    - Asserts content starts with magic bytes `b"%PDF"`.
    - Asserts content size > 5,000 bytes.
- **`backend/tests/test_accuracy_audit.py`**
  - **Test**: `test_pdf_export_reflects_the_same_numbers`:
    - Asserts that numbers in the PDF match exact calculated values from the query engine.

### 6. Presentation / Standalone PDF Scripts
- **`generate_prep_pdfs.py`**
  - Standalone script using ReportLab Canvas & Platypus to generate comprehensive presentation & defense guides.
- **`build_all_prep_pdfs_26slides.py`**
  - Standalone script generating 26-slide presentation PDF guides.

### 7. Documentation
- **`docs/PRO_UPGRADE.md`**
  - Feature 4 documentation detailing why ReportLab was chosen over HTML-to-PDF or screenshots, and explaining pagination, memory safety, and accounting report layout.

---

## 🔄 End-to-End Workflow Diagram

```
User clicks "Export PDF" (Dashboard.jsx)
        │
        ▼
POST /analytics/{file_id}/report.pdf  (with active filters & date range)
        │
        ▼
FastAPI Route (_render_pdf in analytics.py)
        │
        ├──> query_engine.build_slice() ──> Filtered DataFrame
        ├──> compute_pnl_report()        ──> P&L summary
        ├──> build_ledger_page()         ──> Ledger rows (max 500)
        │
        ▼
generate_ca_report_pdf() (pdf_report.py using ReportLab Platypus)
        │
        ▼
Returns Raw PDF Bytes (application/pdf)
        │
        ▼
Axios receives Blob response (Dashboard.jsx)
        │
        ▼
Browser downloads "senova-financial-report-XXXX.pdf"
```
