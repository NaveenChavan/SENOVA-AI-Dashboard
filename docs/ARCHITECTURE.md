# SENOVA AI Dashboard — Technical Architecture

Deep technical reference: API contracts, calculation formulas, and how
data flows through the system. Read `PROJECT_OVERVIEW.md` first for the
high-level picture.

---

## 1. Backend API reference

All routes except `/health` require `Authorization: Bearer <firebase-id-token>`
(or `DISABLE_AUTH=true` for local dev).

### `POST /upload/`
Accepts a `.csv` or `.xlsx` file (multipart form, field name `file`).
Saves it to disk, does **not** validate or analyze yet. Returns a
`ColumnMappingPreview`:
```json
{
  "file_id": "uuid-hex",
  "filename": "sales_july.csv",
  "detected_columns": [
    {"raw_column": "Sold On", "suggested_field": "Date", "confidence": "fuzzy"},
    {"raw_column": "Qty.", "suggested_field": "Quantity", "confidence": "exact"},
    {"raw_column": "Notes", "suggested_field": null, "confidence": "none"}
  ],
  "required_fields": ["Date", "Category", "Item", "Quantity", "Selling Price", "Cost Price"],
  "row_count": 21,
  "sample_rows": [{"Sold On": "15-07-2025", "Qty.": "12", ...}]
}
```
`confidence` is one of `"exact"` (known alias, high confidence),
`"fuzzy"` (keyword substring match, needs human confirmation), or
`"none"` (no guess at all).

### `POST /upload/{file_id}/confirm-mapping`
Body: `{"mapping": {"Sold On": "Date", "Qty.": "Quantity", ...}}`
(only columns the user wants mapped; unmapped/ignored columns are
simply omitted). Runs full row-level validation using this explicit
mapping, persists it to `{file_id}.mapping.json` for reuse, returns:
```json
{
  "file_id": "uuid-hex",
  "filename": "sales_july.csv",
  "message": "Uploaded 20 valid row(s) with 1 error(s).",
  "valid_count": 20,
  "error_count": 1,
  "errors": [{"row": 5, "column": "Quantity", "error": "Quantity must be greater than zero."}],
  "date_range": {"min_date": "2025-07-15", "max_date": "2025-07-21", "span_days": 7}
}
```

### `GET /process/{file_id}`
Legacy/simple endpoint — same as `/analytics/{file_id}?time_filter=all`.
Requires a confirmed mapping (409 if not confirmed yet).

### `GET /analytics/{file_id}?time_filter=30days`
`time_filter` ∈ `{all, today, week, 30days, month}` (default `30days`).
Returns the full `AnalyticsResponse` — see §3 below for its shape and
exactly how each field is computed.

### `GET /analytics/{file_id}/report?time_filter=30days`
Returns a `CAReportSummary` — the Profit & Loss statement + category
ledger, for the CA-style "Financial Report" tab:
```json
{
  "period_label": "Last 30 Days",
  "period_start": "2025-06-22", "period_end": "2025-07-21",
  "pnl": [
    {"label": "Gross Revenue", "amount": 137337.0, "percentage_of_revenue": 100.0, "is_subtotal": false},
    {"label": "Cost of Goods Sold (COGS)", "amount": 86450.0, "percentage_of_revenue": 62.95, "is_subtotal": false},
    {"label": "Gross Profit", "amount": 50887.0, "percentage_of_revenue": 37.05, "is_subtotal": true}
  ],
  "category_ledger": [
    {"category": "Electronics", "units_sold": 40, "revenue": 59980.0, "cost": 41000.0, "profit": 18980.0, "margin_percentage": 31.63}
  ],
  "total_transactions": 21
}
```

### `GET /analytics/{file_id}/ledger?time_filter=all&page=1&page_size=100`
`page_size` max 1000. Returns a `LedgerPage` — never the full dataset in
one response (critical for 50k+-row files):
```json
{
  "entries": [
    {"row": 0, "date": "2025-07-15", "category": "Electronics", "item": "Wireless Mouse",
     "quantity": 12, "selling_price": 1200.0, "cost_price": 800.0, "revenue": 14400.0, "profit": 4800.0}
  ],
  "page": 1, "page_size": 100, "total_rows": 21, "total_pages": 1
}
```

### `GET /analytics/{file_id}/report.pdf?time_filter=30days`
Streams `application/pdf` (Content-Disposition: attachment). Contains,
in order: header (brand + period), P&L statement table, category ledger
table, top-5-items table, dead-stock table, and a page-broken detailed
transaction ledger (capped at 500 rows, with a footnote if truncated).

### `GET /health`
No auth required. `{"status": "ok"}` — liveness probe.

---

## 2. Column-mapping engine

`backend/app/utils/data_validator.py` is the heart of "any column layout
works." Three layers of matching, in order:

1. **`COLUMN_ALIAS_MAP`** — an exact-match dictionary of ~80 known header
   variants (`"qty"`, `"units sold"`, `"rate"`, `"mrp"`, etc.) to the 6
   canonical fields. Confidence: `"exact"`.
2. **`_FUZZY_KEYWORDS`** — if no exact alias matches, checks whether a
   known keyword (`"qty"`, `"price"`, `"cost"`, etc.) appears as a
   *substring* anywhere in the column name. Confidence: `"fuzzy"`.
3. **No match** — the column is left unmapped (`suggested_field: null`,
   confidence `"none"`), e.g. a shop's internal "Notes" or "Discount %"
   column.

`detect_column_mapping(df)` runs this for every column and returns the
preview shown to the user. `apply_column_mapping(df, mapping)` renames
columns using the **explicit, user-confirmed** mapping (not the guesser)
— this is the path used for all real analysis, so a wrong guess never
silently produces wrong numbers.

---

## 3. Row validation & coercion pipeline

`normalize_dataframe()` — the full pipeline, in order:

1. Rename columns (via confirmed mapping or auto-guess fallback).
2. Assert all 6 canonical columns exist (raises `ValueError` if not,
   unless `soft_fail=True`, which instead reports every row as an error
   and returns an empty valid DataFrame — used by the upload endpoint so
   it never 500s on a badly-shaped file).
3. `pd.to_numeric(..., errors='coerce')` on `Quantity`/`Selling Price`/`Cost Price`.
4. **Currency-symbol retry**: for values still `NaN`, strip
   `$ , € £ ₹` and retry parsing (so `"₹1,200"` → `1200.0`).
5. Replace `inf`/`-inf` with `NaN` (so later `.astype(int)` never chokes).
6. **Two-pass date parsing**: try `dayfirst=True` (handles Indian
   `DD-MM-YYYY`), then retry without `dayfirst` for any rows still
   unparsed (handles ISO `YYYY-MM-DD`).
7. Empty `Category`/`Item` strings → `NaN` (so `dropna` catches them).
8. Collect every cell-level failure into a structured error list
   (`{"row": i, "column": "...", "error": "..."}`).
9. `dropna()` on all 6 required columns — only fully-valid rows survive.
10. Safe `.astype(int)`/`.astype(float)` (guaranteed NaN/inf-free by this point).
11. **Business rule validation**: `Quantity <= 0`, `Selling Price < 0`,
    `Cost Price < 0` are flagged and removed. `Cost Price > Selling Price`
    is deliberately **not** flagged (legitimate clearance-sale scenario).

---

## 4. Analytics calculation formulas

All in `backend/app/services/sales_calculations.py`. Per-row derived
values (`_prepare()`):
```
_row_revenue = Quantity × Selling Price
_row_cost    = Quantity × Cost Price
_row_profit  = _row_revenue − _row_cost
```

### Time filters
Anchored to the **data's own max date**, not the system clock (so an
old CSV upload still gives a correct "Last 7 Days" relative to itself):

| Filter | Window |
|---|---|
| `today` | `[max_date's midnight, max_date's midnight + 1 day)` |
| `week` | `[max_date − 7 days, max_date]` |
| `30days` | `[max_date − 30 days, max_date]` |
| `month` | `[1st of max_date's month, max_date]` |
| `all` | entire dataset |

### Trend percentage (period-over-period)
`_split_periods()` divides the dataset into a *current* window and an
equally-sized *previous* window immediately before it (e.g. for `week`:
current = last 7 days, previous = the 7 days before that). Trend:
```
trend_% = (current_value − previous_value) / previous_value × 100
```
Returns `0.0` if the previous period had no data (avoids division by
zero) — this also means "All Time" never has a meaningful previous
period, so its trend is always `0.0` by design.

### Sparklines
Daily-grouped values are **zero-filled** across every calendar day in
the filter's window (`_zero_fill_daily`), so a sparkline for "Last 7
Days" always has exactly 7 points even if some days had zero sales —
otherwise gaps would compress the visual comparison.

### Dead stock
Items whose **total quantity sold** (in the filtered window) is `<= 5`
(the `threshold_qty` default). `days_since_last_sale` = days between the
filtered dataset's max date and that item's own last sale date.

### Data date range (`compute_data_date_range`)
```
span_days = (max_date.normalize() − min_date.normalize()).days + 1
```
This drives the frontend's filter-disabling logic (§6 below).

---

## 5. CA-style P&L construction

`compute_pnl_report()` builds exactly 3 P&L lines in display order:
1. **Gross Revenue** — `100%` of itself by definition.
2. **Cost of Goods Sold (COGS)** — `cost / revenue × 100`.
3. **Gross Profit** (marked `is_subtotal: true`, so the frontend/PDF
   renders it bold with a ruled-off top border) — `profit / revenue × 100`.

The category ledger is a `groupby("Category")` aggregation of the same
filtered DataFrame, sorted by revenue descending, each row carrying its
own `margin_percentage = profit / revenue × 100`.

---

## 6. Frontend state management

Two Zustand stores, both in `frontend/src/store/`:

### `useSalesStore.js`
- `mappingPreview` — set after `uploadFile()`, cleared after `confirmMapping()`.
- `dateRange` — `{min_date, max_date, span_days}`, set from the
  `confirm-mapping` response; drives filter-disabling on the dashboard.
- `data` — the current `AnalyticsResponse` (charts tab).
- `caReport` / `ledgerPage` — Financial Report tab data, fetched lazily
  only when that tab is first opened.
- All fetch actions use the shared `api` Axios instance (§7) so every
  request gets the Firebase auth header and the correct base URL.

### `useThemeStore.js`
- `theme` — `"dark"` or `"light"`.
- Initial value resolved from `localStorage['senova-theme']`, falling
  back to `prefers-color-scheme`, falling back to `"dark"`.
- `setTheme()`/`toggleTheme()` both write `document.documentElement`'s
  `data-theme` attribute directly (not React state alone) so every CSS
  variable in `index.css` re-resolves immediately, and persist the
  choice to `localStorage`.
- **Flash-of-wrong-theme prevention**: `index.html` has an inline
  `<script>` that runs *before* `<div id="root">` is even parsed, which
  synchronously reads `localStorage`/`prefers-color-scheme` and sets
  `data-theme` on `<html>` — by the time React mounts and this store
  initializes, the correct theme is already painted.

---

## 7. Frontend ↔ backend request flow

`frontend/src/services/api.js` wraps Axios with two interceptors:
1. **Request interceptor**: calls `getIdToken()` (from `firebase.js`,
   which transparently refreshes the token if it's near expiry) and
   attaches `Authorization: Bearer <token>` to every outgoing request.
2. **Response interceptor**: if a request comes back `401` (e.g. token
   was revoked server-side), retries **once** with a force-refreshed
   token before giving up.

`baseURL` is `import.meta.env.VITE_API_URL || ''` — empty string means
relative URLs, which the Vite dev-server proxy (`vite.config.js`)
forwards to `http://127.0.0.1:8000` locally. In production, setting
`VITE_API_URL` makes every request go directly to the deployed backend
origin (this value is baked into the JS bundle at build time — verified
during this project's Vercel-compatibility check).

---

## 8. Charts and theming

Recharts renders SVG with literal JS colour strings — it cannot read CSS
custom properties the way Tailwind classes can. `frontend/src/components/
charts/useChartTheme.js` solves this: it calls
`getComputedStyle(document.documentElement)` to read the *live* resolved
value of each CSS variable, and re-runs whenever `useThemeStore`'s
`theme` changes — so `LineChart`, `BarChart`, and `CategoryPieChart` all
repaint correctly on theme toggle without any hardcoded hex values.

Every other component uses CSS variables directly via Tailwind's
`style={{ color: 'var(--text-primary)' }}` pattern rather than
theme-specific Tailwind classes — confirmed via a full-codebase grep
sweep that zero hardcoded `slate-*`/`emerald-*` Tailwind colour classes
remain. The only intentionally-fixed colours are semantic status badges
(red/amber/green for critical/warning/success — meant to stay consistent
across themes) and Google's 4-brand-colour logo SVG on the login button.

---

## 9. File storage & lifecycle (backend)

`backend/app/services/file_handler.py`:
- `save_upload()` writes the raw file to `UPLOAD_DIR/{uuid}.{ext}`.
- `save_column_mapping()` / `load_column_mapping()` persist the
  user-confirmed mapping as a sidecar JSON: `UPLOAD_DIR/{uuid}.mapping.json`.
- **No file is deleted right after processing** — the dashboard re-fetches
  the same `file_id` every time the user changes a date filter or opens
  the Financial Report tab, so deleting on first read would break that.
- Instead, `sweep_expired_uploads()` deletes any file (and its mapping
  sidecar) older than `UPLOAD_TTL_MINUTES` (default 120). This sweep runs
  once at app startup and then on a recurring `asyncio` background task
  every `UPLOAD_SWEEP_INTERVAL_MINUTES` (default 30), wired in via
  FastAPI's `lifespan` context manager in `main.py`.
- **This is why the backend cannot run on a serverless platform** — a
  serverless function has no persistent disk between invocations and no
  long-lived process for the background sweep to run in.

---

## 10. Testing artifacts

`testing/` contains real sample files used to verify behaviour at scale
and at edge cases during development:
- `narrow_range_7days.csv` / `wide_range_6months.csv` — purpose-built to
  demonstrate the filter-disabling feature (see §4's "data date range").
- `senova_stress_test_50k.csv`, `senova_ultimate_test_25k.csv`,
  `senova_30k_test_data.xlsx` — large-file performance/correctness tests;
  used to confirm pagination, PDF generation time (~1.3s for 50k rows),
  and calculation accuracy at scale (verified against independent Pandas
  calculations during development, exact match).
