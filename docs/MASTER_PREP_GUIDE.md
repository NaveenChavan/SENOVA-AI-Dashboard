# SENOVA AI Dashboard — Master Preparation Guide

> **Purpose of this document:** A single, exhaustive, step-by-step reference to
> everything actually running in this codebase — every backend function, every
> formula/constant, every frontend component, the full request/response
> contracts, and how data flows end-to-end from file upload to PDF export.
> Built by reading the source directly (not by trusting prior docs blindly);
> discrepancies found between existing docs and the code are called out
> explicitly in §15.
>
> **The most important fact to internalize first:** there is **no ML model**
> anywhere in this project. "Model" in this codebase means two things only:
> (1) Pydantic **data models** (`backend/app/models/schemas.py`) that define
> API request/response shapes, and (2) statistical/mathematical **models**
> (robust z-score, weighted least squares, seasonal indices) implemented by
> hand in Pandas/NumPy. No LLM, no scikit-learn, no PyTorch/TensorFlow. Every
> number the app shows is a deterministic formula over the uploaded rows.

---

## 0. One-paragraph mental model

A user uploads a sales CSV/Excel file → the backend guesses which raw column
means what ("Date", "Item", "Selling Price", ...) → the user confirms/fixes
that mapping → every row is validated and typed → the clean DataFrame is
cached in memory (bounded LRU, keyed on file + mapping) → every dashboard
tab (KPIs, charts, insights, inventory, forecast, P&L, PDF) calls **one**
shared slicing function (`query_engine.build_slice`) with the same
time-filter/date-range/dimension-filters, so every view of the data is
guaranteed to describe the same rows → the frontend renders that JSON with
Recharts, or the backend renders it directly into a PDF with ReportLab.
Nothing is stored in a database; uploaded files live on disk for a TTL window
and are swept away by a background asyncio task.

---

## 1. Tech stack — exact dependencies

### Backend (`backend/requirements.txt`, `requirements-dev.txt`)
- **FastAPI** — the web framework (async, Pydantic-validated routes).
- **Pandas / NumPy** — 100% of the data processing and math. No other numeric library.
- **ReportLab** — PDF generation (Platypus layout engine).
- **firebase-admin** — server-side verification of Firebase ID tokens.
- **python-dotenv** — loads `backend/.env` into `os.environ` before config reads it.
- **openpyxl** — Excel (`.xlsx`) reading engine for Pandas.
- **sendgrid** — password-reset email delivery.
- **uvicorn** — ASGI server.
- Dev-only: **pytest** (test runner).

There is deliberately **no** database driver, **no** ORM, **no** ML/AI
library. The README states this explicitly as a design decision: "Every
calculation is done in-house with Pandas/NumPy. No language model, no
third-party analytics service."

### Frontend (`frontend/package.json`)
- **React 18** + **Vite** (build tool/dev server).
- **Tailwind CSS** — utility-first styling.
- **Zustand** — global state (three small stores, no Redux).
- **Firebase (client SDK)** — auth only.
- **Recharts** — all charting except the heatmap (hand-built CSS grid) and PDF (server-side).
- **React Router v7** (with v7 future flags already enabled).
- **Axios** — HTTP client with auth interceptors.
- **Motion** (`motion@12.42.2`, exact-pinned) — the *only* new runtime
  dependency added for the UI redesign; animates already-rendered DOM nodes,
  no network access, no data access.
- **Space Grotesk** (display font, headings only) + **Plus Jakarta Sans**
  (body/UI text) + **JetBrains Mono** (numeric/mono contexts).
- Dev/test: **Vitest** + **Testing Library**.

---

## 2. Repository map (what's actually on disk)

```
senova-ai-dashboard/
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI app assembly, lifespan, routers
│   │   ├── core/config.py             env vars → typed constants, prod safety guard
│   │   ├── models/schemas.py          every Pydantic request/response model
│   │   ├── api/routes/
│   │   │   ├── upload.py              2-step upload flow
│   │   │   ├── analytics.py           classic + Pro analytics endpoints
│   │   │   └── auth.py                POST /auth/forgot-password
│   │   ├── services/
│   │   │   ├── file_handler.py        disk I/O, ownership, TTL sweep
│   │   │   ├── frame_cache.py         bounded LRU cache of parsed frames
│   │   │   ├── sales_calculations.py  KPIs, P&L, ledger, top items, dead stock
│   │   │   ├── query_engine.py        window/filter/aggregate/heatmap engine
│   │   │   ├── insights_engine.py     6 statistical "finding" checks
│   │   │   ├── forecasting.py         revenue forecast + backtest
│   │   │   ├── inventory_intel.py     velocity/ABC/ageing/reorder scoring
│   │   │   ├── pdf_report.py          ReportLab PDF assembly
│   │   │   └── email_service.py       SendGrid password-reset delivery
│   │   └── utils/
│   │       ├── data_validator.py      column alias map + row validation
│   │       ├── auth_verifier.py       Firebase ID token verification
│   │       └── safe_json.py           NaN/Infinity-safe number coercion
│   ├── tests/                         139 test functions across 10 files
│   ├── temp_uploads/                  runtime upload storage (gitignored)
│   └── .env / .env.example
├── frontend/
│   └── src/
│       ├── main.jsx, App.jsx          bootstrap + app shell (header/footer)
│       ├── routes/AppRoutes.jsx       route table, lazy-loaded pages
│       ├── services/{api,firebase}.js Axios instance, Firebase wrapper
│       ├── store/{useSalesStore,useThemeStore,useDensityStore}.js
│       ├── pages/                     Login, Signup, ForgotPassword,
│       │                              ResetPasswordConfirm, VerifyEmail,
│       │                              Upload, Dashboard
│       └── components/
│           ├── common/                AuthGuard, GuestGuard, CommandPalette, ...
│           ├── upload/                FileDropzone, ColumnMappingScreen
│           ├── dashboard/             SummaryStats, InsightCards, InventoryPanel,
│           │                          PnLReportTable, ForecastSummary, FilterPanel,
│           │                          DrillDownPanel, DeadStockTable, ...
│           └── charts/                ChartStudio, StudioCharts (6 Recharts views),
│                                      HeatmapGrid, TrendChart, BarChart, chartView.js
├── docs/                              existing architecture/changelog docs (see §12)
├── testing2/, TESting/                sample CSV/XLSX files for manual testing
└── .kiro/steering/ui-ux-pro-max/      design-system skill (not app code)
```

---

## 3. Backend startup sequence — `app/main.py`

1. **Import time**: `core/config.py` is imported first. It calls
   `load_dotenv()` on `backend/.env`, then reads every setting from
   `os.environ` with defaults. **Critical guard, runs at import time:**
   ```python
   if DISABLE_AUTH and ENV == "production":
       raise RuntimeError(...)
   ```
   If a stray dev flag survives into a production deploy, the process
   **refuses to boot** rather than silently serving an unauthenticated API.
2. `FastAPI(..., lifespan=lifespan)` is constructed. `lifespan` is an
   `@asynccontextmanager`:
   - **On startup**: runs `sweep_expired_uploads()` once synchronously (purge
     stale files left from a crash/previous run immediately), then spawns
     `_sweep_loop()` as a background `asyncio.Task`.
   - **`_sweep_loop()`**: `while True: sweep_expired_uploads(); sleep(interval)`
     where `interval = UPLOAD_SWEEP_INTERVAL_MINUTES * 60`. Wrapped in
     try/except so one bad sweep never kills the loop permanently.
   - **On shutdown**: cancels that task.
3. **Middleware**: only `CORSMiddleware`, `allow_origins=ALLOWED_ORIGINS`
   (env-driven list), `allow_credentials=True` (Firebase Bearer tokens travel
   from the browser), methods/headers wide open (`*`) — the real security
   boundary is the per-route Firebase check, not CORS.
4. **Routers registered:**
   | Prefix | Router | Purpose |
   |---|---|---|
   | `/upload` | `upload.router` | 2-step upload flow |
   | `/process` | `analytics.router` | legacy single-shot analysis (`GET /process/{id}`) |
   | `/analytics` | `analytics.analytics_router` | classic GET + all Pro POST endpoints |
   | `/auth` | `auth.router` | password reset |
5. `GET /health` — no auth, returns `{"status":"ok"}`. Deliberately excluded
   from Firebase checks since uptime monitors don't carry user tokens.

---

## 4. Configuration — `app/core/config.py` (every setting)

| Constant | Env var | Default | Purpose |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS allow-list (comma-split) |
| `ENV` | `ENV` | `development` | Gates the `DISABLE_AUTH` production guard |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | same | `""` | Whole service-account JSON as one string (managed-host path) |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | same | `""` | Path to a service-account file (local-dev path) |
| `FIREBASE_PROJECT_ID` | same | `senova-dashboard` | Validates token audience |
| `DISABLE_AUTH` | same | `false` | Total auth bypass — **local dev only**, blocked in production (see §3) |
| `UPLOAD_DIR` | same | `temp_uploads` | Where files + sidecars live |
| `MAX_UPLOAD_SIZE_MB` | same | `50` | Hard upload size cap |
| `UPLOAD_TTL_MINUTES` | same | `120` | File lifetime before the sweep deletes it |
| `UPLOAD_SWEEP_INTERVAL_MINUTES` | same | `30` | How often the background sweep runs |
| `FRAME_CACHE_MAX_ENTRIES` | same | `3` | LRU cache capacity (tuned for a 512MB host) |
| `FRAME_CACHE_MAX_ROWS` | same | `120000` | Frames larger than this are never cached |
| `SENDGRID_API_KEY` | same | `""` | Enables branded password-reset email |
| `SENDER_EMAIL` | same | `noreply@example.com` | Verified From address |
| `APP_DOMAIN` | same | `http://localhost:5173` | Builds the branded reset-password link |

---

## 5. The upload pipeline — step by step

### Step 1 — `POST /upload/` (`upload.py: upload_file`)
Input: multipart file. Auth required.
1. `_validate_upload_constraints` — filename must end `.csv`/`.xlsx` (400 otherwise).
2. Read full file bytes into memory; reject if `> MAX_UPLOAD_SIZE_MB` (413).
3. `save_upload(bytes, filename, owner)` (`file_handler.py`):
   - Generates `file_id = uuid4().hex` (32 lowercase hex chars).
   - Writes `{file_id}{ext}` into `UPLOAD_DIR`.
   - Writes `{file_id}.meta.json` = `{owner, original_filename[:200], uploaded_at}`.
   - **Only the extension** of the client filename is trusted for the path — the
     stem is never used on disk, which is what prevents path-traversal via a
     crafted filename.
4. `read_to_dataframe(file_id)` — for CSV: sniffs the delimiter (`,`/`;`/tab/`|`)
   from the first 2048 bytes, reads with `utf-8-sig`, falls back to `latin-1`
   on decode error (older Windows POS exports); for XLSX: `pd.read_excel` via
   `openpyxl`. Parse failure → file is deleted immediately (`cleanup`), 400.
5. Empty-file / >100-column checks → cleanup + 400.
6. `detect_column_mapping(df)` (`data_validator.py`) — heuristic guess per
   raw column (see §6).
7. Builds 5 sample rows, every cell coerced to `None`/string≤120 chars so no
   pandas/numpy dtype leaks into JSON.
8. Returns `ColumnMappingPreview`: `file_id, filename, detected_columns[],
   required_fields[], optional_fields[], field_help{}, row_count, sample_rows[]`.

**Nothing is validated or trusted yet** — this is purely a preview so the
user can correct a wrong guess before any figure is computed (e.g. mapping
`Amount` to `Selling Price` instead of `Line Total` would silently inflate
revenue by the quantity factor on every row).

### Step 2 — `POST /upload/{file_id}/confirm-mapping` (`confirm_mapping`)
Input: `{ "mapping": {raw_column: canonical_field} }`. Auth required.
1. `validate_file_id` (regex `^[0-9a-f]{32}$`) + `assert_owner` + `read_to_dataframe`
   — any failure among these three collapses to **one indistinguishable 404**
   ("File not found. Upload a file first.") — malformed id, missing file, and
   "belongs to someone else" are deliberately unified so the API can never be
   used to enumerate other users' file IDs.
2. `normalize_dataframe(df, soft_fail=True, column_mapping=mapping)` — full
   row validation (see §6). Missing-required-columns-entirely → 400.
3. `save_column_mapping(file_id, mapping)` — persists the sidecar so future
   reads never need the mapping resent.
4. **`frame_cache.invalidate(file_id)`** — drops any previously cached frame
   for this id so a corrected mapping is never shadowed by a stale parse.
5. Computes which optional fields are actually present → tells the frontend
   which extra chart axes/measures this file unlocked.
6. Returns `UploadResponse`: `file_id, filename, message, valid_count,
   error_count, errors[], date_range{min_date,max_date,span_days}, optional_fields[]`.

---

## 6. Column mapping & row validation — `app/utils/data_validator.py`

### Canonical schema
```
REQUIRED_COLUMNS        = Date, Category, Item, Quantity, Selling Price, Cost Price   (6)
OPTIONAL_MEASURE_COLUMNS   = Line Total, Discount, Tax, Stock On Hand                  (4)
OPTIONAL_DIMENSION_COLUMNS = Branch, Payment Mode, Customer, Salesperson,
                              Brand, Size, Colour, Invoice No                          (8)
```
18 canonical fields total (`MAPPABLE_FIELDS`).

### Two-layer alias resolution (`guess_canonical_column`)
1. **Exact alias map** (`COLUMN_ALIAS_MAP`, ~180 entries, case/whitespace/BOM
   insensitive) — e.g. `Voucher Date`, `Bill Date`, `Txn Date` → `Date`;
   `Stock Group`, `Item Group` → `Category`; `Rate/Unit`, `MRP` → `Selling Price`;
   `Purchase Rate`, `COGS` → `Cost Price`; `Taxable Value`, `Net Amount` →
   `Line Total` (not `Selling Price` — see correctness note below).
2. **Fuzzy substring fallback** (`_FUZZY_KEYWORDS`), order-significant so
   specific phrases pre-empt generic ones: `"discount"` checked before
   quantity keywords (it contains `"count"`); `"purchase"/"cogs"/"wholesale"`
   (→ Cost Price) checked before `"rate"/"price"` (→ Selling Price) so
   "Purchase Rate" doesn't become Selling Price.
3. Anything matching neither → `(None, "none")`, left unmapped (e.g. `"HSN"`,
   `"Remarks"`).
4. `detect_column_mapping` also **de-duplicates**: if two raw columns guess
   the same canonical field, only the first keeps the suggestion — the
   second is downgraded to `"none"` so the user must pick explicitly.

### Correctness note — why `Line Total` is a separate field
An `Amount`/`Net Amount`/`Taxable Value` column is almost always
`Quantity × Rate` — a **line total**, not a unit price. If it were mapped
straight to `Selling Price`, revenue would compute as `Quantity × LineTotal`,
inflating every row by the quantity factor. So these aliases map to
`Line Total`, and `_derive_selling_price_from_line_total` computes
`Selling Price = Line Total ÷ Quantity` only where `Quantity` is a usable
positive number — otherwise the row is correctly reported as missing rather
than guessed.

### `normalize_dataframe(df, soft_fail, column_mapping)` — the full pipeline
1. Rename columns via the confirmed mapping (or auto-guess if none given).
2. Drop duplicate canonical columns (`keep="first"`) — prevents two raw
   columns mapping to the same field from turning `df["Quantity"]` into a
   DataFrame and breaking every downstream `.astype`.
3. Derive `Selling Price` from `Line Total` where needed.
4. Validate all 6 required columns exist post-rename — hard `ValueError`
   unless `soft_fail=True` (then returns an empty frame + one schema error).
5. Drop any column not in the 18-field canonical set.
6. Snapshot raw values (for quoting the user's original text in error messages).
7. **Numeric coercion** (`_coerce_numeric`): `pd.to_numeric(errors="coerce")`,
   then for cells still failing, strip `₹$€£,` and whitespace and retry —
   handles `"₹ 1,299.00"`-style Indian currency strings. `inf`/`-inf` → NaN.
8. **Date parsing** (`_parse_dates`), ISO-first deliberately: rows matching
   `^\d{4}-\d{1,2}-\d{1,2}` are parsed with no `dayfirst` flag; the remainder
   is retried with `dayfirst=True` (DD-MM-YYYY); anything still unparsed gets
   one more untyped attempt. Applying `dayfirst=True` first would silently
   reinterpret ISO dates with day ≤ 12 (e.g. `2026-04-05` → 5 April *or*
   4 May) — this ordering is the fix for that class of bug.
9. Blank `Category`/`Item` forced to NaN so they're caught by the required-field drop.
10. **Error collection** — for each required column: distinguishes
    `"Missing X"` (blank cell) from `"Invalid X: Expected <Type>, received
    '<value>'"` (unparseable content, truncated to 80 chars); non-integer
    `Quantity` flagged; optional-column failures reported as `"Ignored <col>:
    ..."` and **do not** cause row removal.
11. `valid_df = df.dropna(subset=REQUIRED_COLUMNS)` — only rows passing every
    required check survive.
12. Final typing: `Quantity→int`, `Selling/Cost Price→float`,
    `Category/Item` stripped strings. Optional measures
    (`Discount/Tax/Line Total`) fill blank→`0.0`, clipped `≥0`. **`Stock On
    Hand` is left as NaN when absent** — never zero-filled, because "filling
    it with 0 would fake a stockout that isn't real." Optional dimensions
    blank→`"Unspecified"`.
13. `_validate_business_rules` — removes (and logs) rows with `Quantity≤0`,
    `Selling Price<0`, or `Cost Price<0`. **Deliberately not flagged:**
    `Cost Price > Selling Price` — a legitimate clearance-sale scenario that
    the margin-leak insight needs intact.

Returns `(clean_valid_df, errors_list)`.

---

## 7. Caching — `app/services/frame_cache.py`

**Why it exists:** every dashboard tab re-reads the same file; re-parsing a
30–50k row Excel export on every request is slow and could let one user
monopolize server CPU. Caching makes repeat calls near-instant while staying
bounded so the cache can't itself become a memory-exhaustion vector.

### Cache key
```python
key = (file_id, get_file_mtime(file_id), _mapping_signature(mapping))
```
- `get_file_mtime` — the raw file's on-disk mtime; a re-upload changes this,
  automatically invalidating old entries for that id.
- `_mapping_signature` — `json.dumps(mapping, sort_keys=True)` if a mapping
  was given, else the literal string `"auto"`.

So **any change to file content or column mapping** produces a different
key — exactly the guarantee needed after `confirm-mapping` persists a
corrected mapping.

### Mechanics
- `OrderedDict` gives LRU semantics directly (`move_to_end` on hit,
  `popitem(last=False)` evicts oldest when over `MAX_ENTRIES`).
- A global `threading.Lock` guards the dict (FastAPI runs sync handlers in a
  thread pool — concurrent requests genuinely race here).
- **Per-key parse locks** (`_get_key_lock`) prevent a "cache stampede": on a
  cold cache, opening the dashboard fires ~5 simultaneous requests for the
  *same* file (summary, insights, forecast, chart-data, dimensions); without
  per-key locking, all 5 would parse the same file in parallel. Different
  files still parse in full parallel since they hold different locks.
- Frames exceeding `MAX_CACHED_ROWS` (120,000 by default) are served once but
  **never cached** — "slow beats out-of-memory."
- `invalidate(file_id)` — called by `confirm_mapping`; drops every cache
  entry for that id regardless of mtime/mapping variant.

---

## 8. Authentication — Firebase + `auth_verifier.py`

### Flow
1. Frontend signs the user in via Firebase client SDK (Google popup or
   email/password).
2. `services/api.js`'s Axios request interceptor attaches
   `Authorization: Bearer <idToken>` on every backend call, auto-refreshing
   a near-expiry token.
3. Backend's `get_current_user` dependency (injected via `Depends(...)` on
   every protected route):
   - If `DISABLE_AUTH`: returns the hardcoded string `"dev-user@localhost"`
     immediately — no Firebase SDK call at all. Guarded twice: `config.py`
     refuses to boot with this true under `ENV=production`; and even in dev,
     no service-account credentials are required while it's on.
   - Otherwise: requires the `Authorization` header (401 if missing), then
     `firebase_auth.verify_id_token(token, app=..., check_revoked=True)` —
     verifies signature, issuer, audience (project id), expiry, **and**
     revocation (an extra round-trip that catches force-signed-out sessions).
   - Maps specific Firebase exceptions to specific 401 messages (expired /
     revoked / invalid), broad catch-all for anything else.
   - Returns `decoded["email"]` (preferred) or `decoded["uid"]` (fallback) —
     this string is what routes use as the file `owner` for ownership checks.
4. `get_firebase_app()` lazily initializes and memoizes the Admin SDK app.
   Credential resolution order: `FIREBASE_SERVICE_ACCOUNT_JSON` env (whole
   JSON string; auto-repairs literal `\n` sequences in `private_key`) →
   `FIREBASE_SERVICE_ACCOUNT_PATH` (file path) → hard error explaining both
   options. Does **not** fall back to Application Default Credentials
   (that only works inside GCP/Firebase Hosting and would produce confusing
   401s everywhere else).

### Password reset (`api/routes/auth.py` + `services/email_service.py`)
`POST /auth/forgot-password` (no auth required — a signed-out user forgetting
their password is by definition unauthenticated).
1. `firebase_auth.generate_password_reset_link(...)` — Firebase's own signed,
   1-hour, single-use action code; the security model is untouched.
2. **Deliverability fix**: the raw Firebase link points at an unbranded
   `*.firebaseapp.com` page. `_build_reset_link` extracts the `oobCode` from
   that link's query string and rebuilds it as
   `{APP_DOMAIN}/reset-password-confirm?oobCode=...` — the app's own branded
   page, which redeems the code client-side.
3. Sent via SendGrid (`_send_via_sendgrid`) from a domain-authenticated
   sender — Firebase's own shared sender frequently lands in Spam.
4. **Anti-enumeration guarantee**: the HTTP response
   (`"If that email exists, a reset link has been sent."`) is identical
   regardless of whether the account exists, the send fails, or SendGrid
   isn't configured. `is_email_delivery_configured()` is safe to expose
   unauthenticated because it reveals only server config, never account
   existence — the frontend uses it to decide whether to fall back to
   Firebase's own reset email.

---

## 9. Analytics — the shared slicing/aggregation engine

### `app/services/query_engine.py` — the single chokepoint

Every Pro endpoint calls `build_slice(df, time_filter, start_date, end_date,
filters)` → `(current, previous, window)`. This is the guarantee that KPI
cards, charts, insights, inventory, P&L, and PDF **never disagree** — they
all read the same rows.

**`Window` dataclass** (`start, end, previous_start, previous_end, label`) —
`end` is an **exclusive** upper bound.

**`resolve_window`** anchors every preset to `df.Date.max()` — **never the
server clock** (a file uploaded weeks ago should still show "today" as its
own last data day):
| Preset | Range |
|---|---|
| `today` | `[max, max+1d)` |
| `week` | `[max−6d, max+1d)` |
| `30days` | `[max−29d, max+1d)` |
| `month` | `[max.replace(day=1), max+1d)` |
| `custom` | `[start, end+1d)`, both required |
| `all` | `[min, max+1d)`, **no** previous-period comparison |

For every non-`all` preset, `previous = [start−span, start)` — an equal-length
immediately preceding window, so a trend arrow compares like-for-like.

**`apply_filters(df, filters: dict[str, list[str]])`**:
- Dimension key must exist in the closed `DIMENSIONS` registry (else 422).
- Time-derived columns (`day`/`weekday`/`month`) cannot be filtered.
- Uses `df[col].astype(str).isin(set(values))` — **membership test only**,
  never string-built or `eval`-based — this is the security guarantee that
  nothing user-supplied reaches `DataFrame.query`/`eval`.

**`aggregate(df, dimension, measure, top_n)`** — the generic grouping engine
behind every chart:
1. Validate `measure` ∈ 8 options, `dimension` ∈ 13 options (else 422).
2. Group by the dimension, sum `revenue/cost/profit/discount`, sum `units`,
   count `transactions`.
3. Derive the requested measure value per group (`margin_pct =
   safe_percentage(profit, revenue)`; `avg_price = revenue/units`).
4. Sort: `weekday` → forced Mon→Sun order; `day`/`month` → chronological;
   everything else → descending by value.
5. **Pareto/concentration** (additive measures, non-time dimensions only):
   walks the sorted groups accumulating a running total, stops the first
   time it reaches 80% of the grand total — `pareto_group_count` is how many
   groups make up that first 80%.
6. **Long-tail folding**: for non-time dimensions with more groups than
   `top_n`, keeps the head and folds the rest into one `"Other (<n>)"`
   bucket — keeps donut/bar charts readable without hiding revenue from totals.

**`heatmap(df, measure)`** — groups by (ISO week start, weekday); column
labels `W01`, `W02`, ... with a parallel list of real Monday dates; ships
`min_value`/`max_value` so the frontend can render a numeric legend
(never colour alone — an accessibility requirement).

### `app/services/sales_calculations.py` — KPIs, P&L, ledger

`_prepare(df)` is the single place gross→net derivation happens, consumed by
every other module downstream:
- `gross_revenue = Quantity × Selling Price`
- `discount = Discount` (0 if column absent)
- `revenue = (gross − discount).clip(lower=0)` — the **net** revenue used everywhere
- `cost = Quantity × Cost Price`
- `profit = revenue − cost`
- `tax` tracked separately, **excluded from profit** ("GST collected is not income")

**KPI trend**: `((current − previous) / previous) × 100`, or `0.0` if
`previous == 0` (treated as "no data to compare," not infinity).

**P&L construction** (`compute_pnl_report`):
- If any discount exists: 3 lines — Gross Sales, Less: Discounts Allowed, Net
  Revenue (subtotal). Else: 1 line — Gross Revenue.
- Always: Cost of Goods Sold, then Gross Profit (subtotal).
- If tax exists: a memo line below profit (a liability, not income).
- Category ledger: per-category units/revenue/cost/profit/margin%, sorted by revenue.

**Ledger** (`build_ledger_page`): paginated, sorted by date (stable sort),
`total_pages = ceil(total_rows/page_size)`, page clamped into valid range.

**Dead stock**: items with total quantity ≤ threshold over the period;
`days_since_last_sale = (data_max_date − last_sale_date).days`.

---

## 10. The three Pro intelligence engines

### 10.1 Insights (`app/services/insights_engine.py`) — 6 checks

No LLM. Every sentence is a template filled with numbers this module
computed. Checks that lack enough data are **skipped and reported as
skipped**, never computed on noise.

| # | Check | Key formula/threshold |
|---|---|---|
| 1 | **Anomaly** | Robust z-score: `z = 0.6745 × (x − median) / MAD` over the zero-filled daily series. Requires ≥7 days. If >25% of days are zero-revenue, switches to trading-days-only baseline (requires ≥7 trading days) — prevents the zero-filled median collapsing to ₹0 and flagging every trading day as an outlier. `|z|≥3.0` → critical; `|z|≥2.0` → warning (drop) or positive (spike). Max 2 cards shown, but all flagged dates ring the trend chart. |
| 2 | **Movers** | Restricted to items present in **both** periods; ranked by **absolute rupee change**, not %, so a 300% jump on a ₹50 item can't outrank a ₹40,000 collapse. Minimum ₹1 move to qualify. |
| 3 | **Margin leak** | Items ≥3% of total revenue only. Benchmark = category median (if ≥3 items in category) else shop-wide median. Negative margin items always rank worst (`gap = |margin| + 100`). Flagged if gap ≥10 margin points. |
| 4 | **Concentration** | Pareto: `cumulative_before` (share *before* adding the current item) used to find the crossing point — testing *after* inclusion would misclassify a single-item shop. Flagged only if ≤20% of items make 80% of revenue, requires ≥8 items. |
| 5 | **Timing** | Best vs worst weekday by mean revenue, each needs ≥2 observations. Flagged only if `best/worst ≥ 1.3`. |
| 6 | **Dead stock** | Items idle ≥30 days, sorted by idle time descending. |

Final list sorted by `(severity_rank, −|impact|)`, capped at 6.

### 10.2 Forecasting (`app/services/forecasting.py`)

Pure NumPy — chosen specifically to avoid a C++ toolchain dependency
(Prophet/statsmodels) on a small deployment host.

- **Guard**: refuses below 14 days of history (states why); below 21 days,
  uses trend only (no weekday seasonality).
- **Trend fit** — recency-weighted least squares:
  `weight = 0.5 ** (age_days / 14)` (14-day half-life: a 14-day-old point
  counts half, 28-day-old counts a quarter). Weighted slope/intercept
  computed from these weights.
- **Weekday seasonality**: `ratio = actual / trend_fit` per day, grouped by
  weekday using the **median** (not mean — one exceptional day shouldn't set
  the factor), normalized to average 1.0, clamped to `[0.3, 3.0]` (a festival
  day can't triple every future occurrence of that weekday).
- **Forecast point**: `max(trend_position × weekday_index, 0)` — floored at
  zero so a falling trend flattens rather than predicting negative sales.
- **Confidence band**: `spread = 1.2816 × residual_σ × √(1 + step/history_days)`
  (1.2816 = z-value for an 80% two-sided interval); widens with distance from
  the last observed day.
- **Backtest accuracy**: holds out the last 7 days, refits on the rest.
  - Normal case: **MAPE** = `mean(|actual−predicted|/actual)` over days with
    actual>0; `accuracy = clamp(100 − MAPE, 0, 100)`, basis `"daily"`.
  - Sparse case (>25% zero-revenue days): scores the **period total**
    instead (`accuracy = clamp(100 − |Σpred−Σactual|/Σactual × 100, 0, 100)`,
    basis `"total"`) — per-day error on a shop trading 1/3 of the calendar is
    dominated by *which* days were open, which nothing can predict; the
    7-day total is what a shop owner actually plans against.
- **Per-item forecasts**: compares first-third vs last-third of the window
  (middle third ignored, "less twitchy on short windows");
  `expected_units = velocity × trend_factor × horizon`, trend clamped to `[0.25, 4.0]`.

### 10.3 Inventory & reorder (`app/services/inventory_intel.py`)

Two explicit modes — never blurs them: **demand mode** (sales-only) vs
**stock-aware mode** (when `Stock On Hand` is mapped). Unmapped fields stay
`null`, never guessed.

- **Velocity**: `units / window_days` (planning rate) and separately
  `units / active_days` (rate on days it actually sold — "separates a
  steady seller from one bulk order that flattered the average").
- **Trend factor**: same first-third/last-third split as forecasting's
  item-level check, clamped to `[0.25, 4.0]`.
- **ABC classification**: sorted by revenue descending; `cumulative_before`
  (share *before* the current item) — same crossing-point correctness fix as
  the concentration insight. `A`: cumulative_before < 80%. `B`: < 95%. `C`: rest.
- **Ageing bucket**: Fresh (<15 days idle), Slow (<30), Stale (<60), Dead (≥60 or no sale).
- **Reorder priority (0–100)**: `100 × (0.50×velocity_norm + 0.30×trend_norm +
  0.20×recency_norm)` where velocity_norm is relative to the fastest mover,
  trend_norm linearly maps the `[0.25,4.0]` clamp range to `[0,1]`, recency_norm
  decays linearly to 0 over 60 idle days.
- **Stock-aware extras**: `days_of_cover = stock_on_hand / velocity_per_day`
  (`null` if velocity is 0 — "infinite cover" isn't a plottable number);
  `capital_locked = stock_on_hand × avg_cost_price`; `reorder_flag =
  days_of_cover < 7`.

---

## 11. PDF generation — `app/services/pdf_report.py`

Built on ReportLab's **Platypus** layout engine — real selectable/searchable
text and tables, not a screenshot of the dashboard. Presentation-only: every
number is computed elsewhere and simply rendered here.

**Document order** (A4, ReportLab `SimpleDocTemplate`):
1. Header — title + filename + period label.
2. **Automated findings** (insights) — printed first, "it's the summary a
   reader wants." Severity spelled out as a **word** (`URGENT`/`WATCH`/
   `GOOD`/`NOTE`), not just colour — "a printed report is often photocopied
   in black and white."
3. Profit & Loss Statement.
4. Category-wise Ledger (if non-empty).
5. Revenue Forecast (or the plain-text `reason` if unavailable).
6. Top 5 Fast-Moving Items, then Dead Stock (each omitted, not left empty, if there's nothing to show).
7. *Page break* → Reorder Priority (top 20) — stock-dependent columns
   (Stock, Cover) are structurally omitted (not blank) when no stock column was mapped.
8. *Page break* → Detailed Transaction Ledger, capped at 500 rows
   (`MAX_LEDGER_ROWS_IN_PDF`) with a footnote if truncated — "a 50,000-row
   register would produce a document nobody can open."

`POST /analytics/{id}/report.pdf` returns raw PDF bytes with
`Content-Disposition: attachment`, computed from the **same** `build_slice`
call as everything else — the PDF can never show different numbers than the
screen for the same filter state.

---

## 12. Full API surface (request/response summary)

All routes except `/health` and `/auth/forgot-password` require
`Authorization: Bearer <Firebase ID token>`.

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/upload/` | multipart file | `ColumnMappingPreview` |
| `POST` | `/upload/{id}/confirm-mapping` | `{mapping}` | `UploadResponse` |
| `GET` | `/process/{id}` | — | `AnalyticsResponse` (legacy, full file) |
| `GET` | `/analytics/{id}?time_filter=` | — | `AnalyticsResponse` (legacy presets, no `custom`) |
| `GET` | `/analytics/{id}/dimensions` | — | `DimensionsResponse` |
| `GET`/`POST` | `/analytics/{id}/report` | `AnalysisQuery` | `CAReportSummary` |
| `GET`/`POST` | `/analytics/{id}/ledger` | `LedgerQuery` | `LedgerPage` |
| `GET`/`POST` | `/analytics/{id}/report.pdf` | `AnalysisQuery` | PDF bytes |
| `POST` | `/analytics/{id}/summary` | `AnalysisQuery` | `AnalyticsResponse` |
| `POST` | `/analytics/{id}/chart-data` | `ChartQuery` | `ChartDataResponse` |
| `POST` | `/analytics/{id}/heatmap` | `ChartQuery` | `HeatmapResponse` |
| `POST` | `/analytics/{id}/insights` | `AnalysisQuery` | `InsightsResponse` |
| `POST` | `/analytics/{id}/inventory` | `AnalysisQuery` | `InventoryResponse` |
| `POST` | `/analytics/{id}/forecast` | `ForecastQuery` | `ForecastResponse` |
| `POST` | `/auth/forgot-password` | `{email}` | `ForgotPasswordResponse` |
| `GET` | `/health` | — | `{"status":"ok"}` |

**Closed enums enforced by Pydantic `Literal` types** (reject 422 before
reaching Pandas): `TimeFilter` (6 values), `DimensionKey` (13), `MeasureKey`
(8). Combined with `filters` bounds (`≤8 keys, ≤50 values each, ≤200 chars
each`), `top_n≤50`, `page_size≤1000`, `horizon≤90` — every numeric input is
clamped at the schema layer before any business logic runs.

**Security pattern applied uniformly**: verified token → `file_id` regex
check → ownership check (mismatch = 404, never 403) → confirmed-mapping
check (409 if missing) → bounded inputs. This is why "another signed-in
user asking for your `file_id` gets a 404," per the README.

---

## 13. Frontend architecture — data flow

### Zustand stores
- **`useSalesStore`** — the central store. Holds upload state (`fileId`,
  `mappingPreview`, `dateRange`, `optionalFields`), query state
  (`{timeFilter, startDate, endDate, filters}` — shaped into the API body by
  the single exported `buildQueryBody()` function, used by every fetcher
  **and** the PDF export, so no two requests can ever disagree about "the
  current view"), and one fetcher per endpoint, each cancellable via
  per-purpose `AbortController`s (a fast filter change aborts the previous
  in-flight request so a slow old response can't overwrite a newer one).
- **`useThemeStore`** — dark/light, persisted to `localStorage`, applied via
  a `data-theme` DOM attribute (matches an inline pre-React script to avoid
  a flash of the wrong theme).
- **`useDensityStore`** — compact/comfortable spacing, same DOM-attribute pattern.

### Dashboard page — URL as the durable state
`pages/Dashboard.jsx` keeps `tab`, `range` (+`from`/`to` for custom), and
`filters` (URL-encoded JSON) in `searchParams`. Every handler updates the
Zustand store **and** the URL in the same call (`syncUrl`, using
`{replace:true}` so casual filter tweaks don't spam browser history) — so a
filtered view can be refreshed or shared with an accountant, per the README.

Data-loading effects are keyed off `JSON.stringify(buildQueryBody(query))`
(a signature, not object identity, since the query object is rebuilt every
render): dimensions once per file; summary/insights/forecast whenever the
signature changes; chart data only on the Overview tab; inventory only on
its tab; P&L+ledger only on the Report tab.

### Chart Studio — 8 views, one payload
`chartView.js` is the view-model (`CHART_TYPES` ×8, `MEASURES` ×8,
dimension list, `resolveChartRequest(view)` — the single function turning a
view into an API request). Because `query_engine.aggregate` precomputes
**every** measure for every group in one response, switching chart type or
measure only triggers a new fetch when the *resolved request* actually
changes (different dimension/measure/top_n) — switching purely between bar
→ donut → pareto on the same dimension/measure re-renders the already-cached
`chartData` with a different Recharts component, no new request.

The 8 views: Bars, Ranking (horizontal bars), Donut, Combo (revenue/cost bars
+ margin line), Pareto (bars + cumulative-% line), Bubble/Scatter (price ×
units, size=revenue), Treemap, Heatmap (hand-built CSS grid, since Recharts
has no heatmap primitive). Every view has a Table toggle (scatter/treemap/
heatmap are poor for screen readers) and every bar/slice/tile/row is a
drill-down entry point into `DrillDownPanel`.

### End-to-end user journey
1. Sign up / log in (Firebase — Google popup or email+password; email
   accounts must verify before reaching the app).
2. Upload a file → preview mapping shown.
3. Confirm/fix column mapping → rows validated server-side → redirected to `/dashboard?fileId=...`.
4. Dashboard loads: Insights → KPI tiles → Forecast strip → Trend chart +
   Top items → Chart Studio → Dead stock (Overview tab); Inventory and
   Financial Report tabs lazy-load their own data on first visit.
5. User adjusts date range / filters / chart type — all server-side,
   URL-synced, and mutually consistent across every panel.
6. Click any chart element → drill-down slide-over with the underlying
   transactions.
7. Export PDF — same filtered slice, rendered server-side.

---

## 14. Testing

139 test functions counted directly across 10 backend test files (README
states "132," a slightly stale figure — see below), covering: column-alias
resolution and the `Line Total→unit price` derivation, window/filter/
aggregation correctness, all 6 insight checks, inventory ABC/ageing/reorder
math (including a single-item-shop regression test), forecast refusal/
projection/backtest, the full upload→confirm→analyze API flow with IDOR and
malformed-id checks, an independent-recomputation accuracy audit against raw
Pandas, degenerate-input edge cases, password-reset response-identity
guarantees, and Firebase-credential-resolution precedence. Frontend has its
own Vitest suite covering all 8 chart views and the four feature panels.

Run backend tests: `cd backend && pip install -r requirements-dev.txt && pytest`
Run frontend tests: `cd frontend && npm test`

---

## 15. Known documentation discrepancies (found while researching this guide)

These are worth knowing so you don't get confused cross-referencing the
older docs in `docs/`:

1. **Test count drift.** `README.md` says "132" backend tests; direct
   `def test_` count in this pass found **139**; `docs/UI_ACCURACY_PASS.md`
   claims **177** as of its own writing. None of the three numbers agree —
   likely explained by pytest parametrization (one `def` can produce many
   collected cases) plus the suite continuing to grow after each doc was written.
2. **`app/api/routes/auth.py` and `app/services/email_service.py` are
   undocumented in the architecture docs.** `docs/SESSION_2026-07-31_AUTH_SYSTEM.md`
   explicitly states "no backend changes were made or required" for that
   session, yet these two files exist, are wired into `main.py`, and have
   19 dedicated tests (`test_auth_routes.py`, `test_firebase_credentials.py`).
   They were evidently built in a session not covered by any existing doc.
3. **Date inconsistency across changelog docs**: `CHANGELOG-UI-REDESIGN.md`
   is dated 2026-07-29, but `PRO_UPGRADE.md` (whose features the redesign
   builds on top of) is dated 26 July 2026 — the ordering implied by content
   doesn't match the ordering implied by the dates.
4. **`docs/UPGRADES.md`** is explicitly a "design spec — not yet
   implemented" for three features (persistent upload history, WhatsApp
   report sharing, reorder-point/safety-stock calculation). If asked whether
   these exist: **they do not**, only the design proposal exists.

None of these are code bugs — they're documentation drift from a
fast-moving multi-session project. This guide was built by reading the
source directly rather than trusting any single prior doc, specifically to
avoid propagating them further.

---

## 16. Quick reference — every "magic number" in the codebase

| Constant | Value | Where | Meaning |
|---|---|---|---|
| MAD-to-sigma scale | `0.6745` | insights_engine | Robust z-score scaling |
| Anomaly critical / warning | `3.0` / `2.0` | insights_engine | \|z\| thresholds |
| Sparse zero-day share | `0.25` | insights, forecasting | Switches to trading-days-only stats |
| Margin leak revenue share / gap | `0.03` / `10.0 pts` | insights_engine | Item must matter + gap must matter |
| Concentration item share | `0.20` | insights_engine | ≤20% of items making 80% of revenue |
| Weekday ratio threshold | `1.3` | insights_engine | Best/worst must differ meaningfully |
| Dead stock idle days | `30` | insights_engine, sales_calculations | |
| Forecast min history | `14 days` | forecasting | Below this: refuses to forecast |
| Seasonality min history | `21 days` | forecasting | Below this: trend only |
| Recency half-life | `14 days` | forecasting | Weight = 0.5^(age/14) |
| Seasonal index clamp | `[0.3, 3.0]` | forecasting | Caps festival-day distortion |
| Confidence z-value | `1.2816` | forecasting | 80% two-sided interval |
| Backtest holdout | `7 days` | forecasting | |
| ABC boundaries | `80% / 95%` | inventory_intel | A / B / C cumulative revenue share |
| Ageing buckets | `15 / 30 / 60 days` | inventory_intel | Fresh / Slow / Stale / Dead |
| Reorder priority weights | `0.50 / 0.30 / 0.20` | inventory_intel | velocity / trend / recency |
| Trend factor clamp | `[0.25, 4.0]` | inventory_intel, forecasting | Both item-trend calculations |
| Reorder cover threshold | `7 days` | inventory_intel | Below this: reorder flag |
| Max upload size | `50 MB` | config | |
| Upload TTL | `120 min` | config | |
| Frame cache size | `3 entries / 120,000 rows` | config | Tuned for a 512MB host |
| Max filter keys/values | `8 / 50` | schemas | Bounds filter payload |
| Max ledger rows in PDF | `500` | pdf_report | |
