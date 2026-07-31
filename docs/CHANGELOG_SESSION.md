# SENOVA AI Dashboard — Session Changelog

Complete, detailed record of every change made to this project across
today's working session, in chronological order. Nothing omitted.

---

## Part 1 — Full audit (bugs, security, performance, code quality)

### Backend fixes
- **Removed duplicate function definitions** in
  `backend/app/utils/data_validator.py` — `_rename_columns()` and
  `_validate_columns_exist()` were each defined twice; the second
  definition silently overrode the first, which broke fuzzy
  column-alias matching for any file whose headers weren't an exact
  match.
- **Fixed a real currency-parsing bug**: the regex used to strip
  currency symbols before re-parsing a number (`r'[\$,€,£,]'`) was
  missing the **₹ (Indian Rupee) symbol** — valid rows containing `₹`
  in a price column were being dropped as validation errors. Fixed to
  `r'[\$,€,£,₹,]'`. Verified live: a row with `"₹1,200"` now correctly
  parses to `1200.0`.
- **Removed dead code**: deleted `backend/app/services/supabase_client.py`
  (a deprecated module that only raised `ImportError` on import) and the
  unused `run_analysis_on_clean_df()` function in `sales_calculations.py`.
- **Fixed missing authentication enforcement**: `get_current_user`
  (Firebase token verification) existed but was never actually applied
  to any route — `/upload`, `/process`, `/analytics` were all publicly
  accessible with no auth check. Wired `Depends(get_current_user)` into
  every route.
- **Fixed the file-cleanup bug**: uploaded files were only deleted on a
  validation-error path, never on success — 80+ orphaned files had
  accumulated in `backend/temp_uploads/`. Implemented a proper TTL-based
  background sweep (`sweep_expired_uploads()`) instead of delete-on-first-read
  (which would have broken date-filter re-fetching), wired into FastAPI's
  `lifespan` context manager to run at startup and every 30 minutes.
  Cleared all 80+ existing orphaned files.
- Verified calculation accuracy live (via `FastAPI TestClient`, not just
  code reading) across multiple scenarios: basic revenue/cost/profit,
  invalid-row filtering, currency symbols, zero-previous-period trend
  guard, multi-day dead-stock day-counting — all exact matches against
  independent manual calculations.

### Security work
- Replaced the entire auth approach: originally `google-auth` +
  `google.oauth2.id_token` (designed for a Google OAuth Client ID flow
  that was never actually wired up on the frontend). Switched to
  **Firebase Admin SDK** (`firebase-admin`) token verification, since the
  frontend now uses Firebase Auth for sign-in.
- Added `DISABLE_AUTH` env var as an explicit, documented local-dev-only
  bypass (never to be set `true` in production).

### Frontend fixes
- **Replaced the fake Google login**: the original `Login.jsx` set a
  hardcoded string `'mock-google-token'` into `localStorage` and called
  it done — no real authentication occurred at all. Replaced with real
  Firebase `signInWithPopup(GoogleAuthProvider)`.
- **Fixed `AuthGuard.jsx`**: was checking for the presence of that same
  fake localStorage token. Rewrote to use Firebase's `onAuthStateChanged`
  for real session detection, with a loading state while Firebase
  resolves the initial auth check (it's asynchronous on page load).
- **Fixed an API-routing inconsistency**: `useSalesStore.fetchAnalytics`
  was calling raw `axios` directly with a hardcoded `/api/` prefix,
  bypassing both the shared `api` instance's `baseURL` config and (once
  auth was added) its auth-header interceptor. Unified to use the shared
  `api` instance everywhere.
- **Fixed `vercel.json`**: the original rewrites only matched `/api/*`,
  a path prefix nothing in the actual app ever calls (the app calls
  `/upload`, `/process`, `/analytics` directly). Rewrote to explicitly
  cover each real route prefix.
- **Fixed a real UI bug in `SummaryStats.jsx`**: the "Total Revenue" and
  "Units Sold" tiles always showed an up-arrow (▲) regardless of the
  actual trend direction, and "Total Cost" never showed any trend arrow
  at all (hardcoded `null`) — misleading users about their own data's
  direction. Fixed to derive the arrow from the real `trend_percentage`
  sign returned by the backend.
- Removed the unused `@react-oauth/google` npm dependency (dead after
  the Firebase auth switch).
- Upgraded `axios` `1.7.9` → `1.18.1`, fixing 3 known moderate/high CVEs
  (DoS via `formDataToJSON` recursion, prototype pollution in auth
  subfields). Ran `npm audit fix` for pre-existing transitive
  vulnerabilities in `dompurify`/`form-data` (jspdf/html2canvas
  dependencies at the time) — reduced to 0 vulnerabilities.
- UI/UX polish pass: replaced a blocking `alert()` in `FileDropzone.jsx`
  with an inline error message; added keyboard accessibility
  (`role="button"`, `tabIndex`, Enter/Space key handling); made the
  Dashboard header responsive (stacks on mobile, horizontally scrollable
  filter pills); redesigned `Login.jsx` as a split-screen layout (brand
  story + feature highlights on desktop, centered card on mobile).

### Infrastructure
- Added a root-level `.gitignore` (none existed before) covering
  `backend/temp_uploads/`, `__pycache__/`, `.env` files, and
  `frontend/node_modules/`, `dist/`, `.env` files.

---

## Part 2 — Fixing the "login works but upload fails with 401" bug

**Root cause found**: `backend/.env` did not exist, and even if it had,
nothing in the codebase ever loaded it — `python-dotenv` wasn't a
dependency and `load_dotenv()` was never called. This meant
`FIREBASE_SERVICE_ACCOUNT_PATH` was always empty and `DISABLE_AUTH`
always defaulted to `false`, so Firebase Admin tried (and failed) to use
Google Cloud's "Application Default Credentials" — which don't exist on
a local Windows machine — producing a 401 on every single request.

**Fixes**:
- Added `python-dotenv` as a dependency; `backend/app/core/config.py`
  now calls `load_dotenv()` pointed at `backend/.env` before reading any
  `os.getenv()` values.
- Created `backend/.env` with `DISABLE_AUTH=true` for local development.
- Hardened `auth_verifier.py`: if `DISABLE_AUTH=false` and no service
  account path is configured, it now raises a **clear, actionable error**
  message (500) instead of silently falling back to Application Default
  Credentials and producing a confusing 401 on every request.
- Verified via `TestClient`: upload now returns `201` locally without
  any shell environment variables set — purely from `.env`.

**Security clarification provided**: Firebase ID tokens are already
RS256-signed JWTs, cryptographically verified against Google's rotating
public keys — this **is** already a proper JWT-based auth system.
Building a custom JWT scheme instead would be strictly weaker (manual key
rotation/revocation management) rather than more secure.

### Login page redesign (requested alongside the auth fix)
Rebuilt `Login.jsx` as a proper split-screen layout:
- **Left panel** (desktop only): brand mark, "Retail intelligence, zero
  spreadsheets." headline, 3 feature highlights with icons.
- **Right panel**: sign-in card with better error handling (specific
  messages for popup-blocked, network-error, vs. generic failure), and
  a "Secured by Firebase Authentication" trust indicator.

---

## Part 3 — Bug diagnosis: "This Month" and "Last 7 Days" showing identical results

**Diagnosis**: Not a calculation bug. Reproduced and confirmed via
synthetic data tests — when an uploaded file's data spans only a few
days near the start of a calendar month, "This Month" (1st of month to
max date) and "Last 7 Days" (max date − 7 days to max date) mathematically
capture the exact same rows, because there simply isn't more data outside
that narrow window to differentiate them. Verified this is expected
behaviour, not an error, by constructing a test case with data confined
to a 6-day window and confirming both filters returned bit-identical
results by design.

**Advice given** (implemented in a later part): rather than a fixed
5-preset filter set, disable filters that are wider than the data's
actual span, and surface *why* via a transparency banner — a pattern used
by production analytics dashboards (Google Analytics, Shopify) when data
range is too narrow for a given comparison window.

---

## Part 4 — Major feature build-out (biggest single block of work)

User feedback drove 4 parallel initiatives, implemented in this priority
order: column-mapping flexibility → CA-style tables → PDF generation →
filter redesign.

### 4a. Column-mapping flexibility
**Problem addressed**: the app previously assumed every uploaded file
used SENOVA's own fixed template column names — unrealistic, since every
shop's export format differs.

**Backend**:
- Refactored `data_validator.py`: added `guess_canonical_column()`
  (single-column best-guess with a confidence level), `detect_column_mapping()`
  (full-file preview report), `apply_column_mapping()` (explicit,
  user-confirmed rename — the primary path for real uploads).
  `normalize_dataframe()` now accepts an optional `column_mapping` param.
- **Split the upload flow into two steps**:
  - `POST /upload/` now only saves the file and returns a
    `ColumnMappingPreview` (detected columns + best guesses + confidence
    + sample rows) — no validation or analysis runs yet.
  - New `POST /upload/{file_id}/confirm-mapping` accepts the user's
    confirmed (or corrected) mapping, runs full validation, and persists
    the mapping to a `{file_id}.mapping.json` sidecar file via new
    `file_handler.save_column_mapping()`/`load_column_mapping()` functions.
  - `GET /analytics/{file_id}` and `/process/{file_id}` now load this
    saved mapping and return **409 Conflict** if it was never confirmed
    (rather than silently re-guessing a possibly-wrong mapping).
- `sales_calculations.run_full_analysis()` updated to accept and pass
  through the confirmed `column_mapping`.

**Frontend**:
- New component `ColumnMappingScreen.jsx`: an editable table — one row
  per detected raw column, showing a sample value, a dropdown to assign
  it to one of the 6 canonical fields (or "Ignore this column"), and a
  confidence badge. Validates no duplicate field assignments and that
  all 6 required fields are covered before enabling "Confirm & analyse."
- `useSalesStore.js`: `uploadFile()` now only performs step 1 (stores
  the mapping preview); new `confirmMapping()` action performs step 2;
  new `cancelMapping()` action to abandon and re-pick a file.
- `Upload.jsx`: conditionally renders the full-width mapping screen when
  a preview is pending, otherwise the normal dropzone flow.

**Verified live** with a deliberately non-standard shop CSV
(`SlNo, Sold On, Dept, Product, Qty., Rate, Cost, Notes`): unrelated
columns (`SlNo`, `Notes`) correctly returned no suggestion; real columns
correctly matched via exact/fuzzy detection; analytics correctly blocked
with 409 before the mapping was confirmed; after confirming, revenue
calculated exactly correctly.

### 4b. CA-style tabular financial report
**Problem addressed**: results were only shown as charts; the user
wanted numbers presented the way a Chartered Accountant would — labelled
line items, running totals, a full transaction register — not just bars
on a graph.

**Backend** — new Pydantic schemas in `schemas.py`:
`PnLLineItem`, `CategoryLedgerRow`, `CAReportSummary`, `LedgerEntry`,
`LedgerPage`, `DataDateRange` (added in a later part).

New functions in `sales_calculations.py`:
- `compute_pnl_report()` — builds the 3-line P&L statement (Gross
  Revenue → COGS → Gross Profit, the last marked as a bold subtotal) plus
  the category-wise ledger.
- `build_ledger_page()` — paginated, chronologically-sorted transaction
  entries; **never materializes the full dataset into one response** —
  critical for the 50k-row files this app is actually tested against.

New routes: `GET /analytics/{file_id}/report` (P&L),
`GET /analytics/{file_id}/ledger?page=&page_size=` (paginated register).

**Frontend** — new components:
- `PnLReportTable.jsx`: renders the P&L statement (with bold, ruled-off
  subtotal styling) and the category ledger as real HTML tables.
- `TransactionLedgerTable.jsx`: paginated register with Previous/Next
  controls, loading/empty states.
- `Dashboard.jsx` gained a **tab switcher** ("Charts" vs. "Financial
  Report") — the Financial Report tab's data is fetched lazily, only on
  first activation.

**Verified live** with a 12-row, 2-category test dataset: P&L
revenue/cost/profit exactly matched a manual sum; category ledger
correctly split by category with accurate margin percentages; pagination
correctly split 12 rows into 3 pages of 5/5/2 at `page_size=5`.

### 4c. Real backend PDF generation
**Problem addressed**: the existing "Export PDF" button used
`html2canvas` + `jsPDF` to screenshot the DOM and paste it into a PDF —
not searchable, not properly formatted, unprofessional for an accounting
document.

**Backend**:
- Installed `reportlab`. New module `backend/app/services/pdf_report.py`:
  `generate_ca_report_pdf()` builds a real, structured PDF using
  ReportLab's Platypus layout engine (`SimpleDocTemplate`, `Table`,
  `TableStyle`, `Paragraph`) — genuine selectable/searchable text and
  tables, not an image.
  - Sections, in order: header (brand + reporting period), P&L
    statement table, category ledger table, top-5-items table,
    dead-stock table, then a page-broken detailed transaction ledger.
  - `MAX_LEDGER_ROWS_IN_PDF = 500`: since a 50k-row file would produce
    an impractically long PDF if every row were printed, the ledger
    section is capped at 500 rows with an explicit footnote
    ("Showing the first 500 of 50,000 transactions…") rather than
    silently truncating or generating a multi-hundred-page document.
- New route `GET /analytics/{file_id}/report.pdf` streams the generated
  PDF with a proper `Content-Disposition: attachment` header.
- New `get_original_filename()` helper in `file_handler.py` so the PDF
  and upload-confirmation responses can show a real filename.

**Frontend**:
- `Dashboard.jsx`'s `exportPDF()` rewritten to call the new backend
  endpoint via the authenticated `api` instance (`responseType: 'blob'`),
  then trigger a browser download via a temporary `<a download>` link
  and a blob URL.
- Removed the now-unused `html2canvas` and `jspdf` npm dependencies
  entirely (confirmed zero remaining references before removing).

**Verified live** via `TestClient` + `pypdf` text extraction: the PDF
returns `200`, `Content-Type: application/pdf`, starts with the `%PDF`
magic bytes, and its extracted text confirms real structured content
(not a screenshot) — with P&L numbers matching category-ledger sums
exactly.

**Verified at 50k-row scale**: PDF generation completed in ~1.29 seconds,
produced a 57.3KB, 16-page document, with the 500-row ledger cap and its
explanatory footnote both correctly present.

### 4d. Date filter redesign
Per an earlier UX recommendation (professional dashboards typically use
Today/Last-7-Days/Last-30-Days-default/This-Month rather than defaulting
to "All Time"):
- Backend `TimeFilter` literal extended from
  `{all, 30days, month, week}` to `{all, today, week, 30days, month}`,
  with the endpoint default changed from `"all"` to `"30days"`.
  `_apply_time_filter`/`filter_by_time`/`_split_periods`/`_get_expected_range`
  in `sales_calculations.py` all gained `"today"` handling (the single
  calendar day of the data's own max date).
- Renamed the previously-private `_apply_time_filter` to a public
  `apply_time_filter` since it's now imported directly by the analytics
  routes (used by the new `/report` and `/ledger` endpoints too).
- Frontend `Dashboard.jsx`'s `DATE_FILTERS` reordered to
  Today / Last 7 Days / Last 30 Days (default) / This Month / All Time.

---

## Part 5 — Permanent fix for "filters showing identical results"

Following on from Part 3's diagnosis, implemented the recommended
permanent solution (approved by the user) rather than a one-off patch:

**Backend**:
- New `DataDateRange` Pydantic schema (`min_date`, `max_date`, `span_days`).
- New `compute_data_date_range()` function — computes the whole-day span
  of a normalized DataFrame's `Date` column.
- `POST /upload/{file_id}/confirm-mapping`'s response now includes a
  `date_range` field, computed from the just-validated data.

**Frontend**:
- `useSalesStore.js`: new `dateRange` state, populated from the
  confirm-mapping response, cleared on `clearData()`.
- `Dashboard.jsx`: each filter now has a `minSpanDays` threshold (`today`:
  1, `week`: 8, `30days`: 31, `month`: 8, `all`: 1). A new
  `isFilterMeaningful()` helper disables any filter whose window exceeds
  the data's actual span — rather than hiding it, the button is greyed
  out (35% opacity, `cursor: not-allowed`) with a `title` tooltip
  explaining exactly why ("Your data only spans N days — this filter
  would show the same results as 'All Time'").
- A transparency banner appears whenever `0 < span_days < 8`, explaining
  in plain language why some filters are disabled — explicitly framed as
  "not a bug."
- A `useEffect` auto-corrects the selected filter to `"all"` if it
  becomes disabled once the real `span_days` is known (e.g. the default
  "Last 30 Days" selection on a 4-day file).

**Test files created** in `testing/` at the user's request:
- `narrow_range_7days.csv` — 21 rows, exactly 15–21 July 2025 (7-day
  span) — demonstrates the filter-disabling + banner.
- `wide_range_6months.csv` — 37 rows, 5 January – 21 July 2025
  (~198-day span) — demonstrates all 5 filters working normally.
- `testing/README.md` — documents the exact expected behaviour for each
  file so they can be used for manual verification.

**Verified live**: narrow file → `span_days=7`, confirmed Week/30-Days/
Month filters would be disabled per the frontend's threshold logic,
Today/All-Time stay enabled; wide file → `span_days=198`, all 5 filters
enabled. Row counts double-checked against actual file line counts.

---

## Part 6 — Premium UI/UX overhaul

A large, explicit design-quality request: logo integration, full
dark/light theming, mobile-to-8K responsiveness, typography polish, and
Vercel-deployment readiness.

### Logo integration
Found the existing brand asset at `frontend/public/assets/logo.jpeg`
(dark navy hexagon, metallic "S," blue/green glow accents) and wired it
into the header (`App.jsx`, replacing an inline SVG placeholder) and the
login page (both the desktop brand panel and the mobile-only brand mark).

### Dark/light theme system
- Complete rewrite of `frontend/src/index.css`: every colour is now a
  CSS custom property under `[data-theme="dark"]` / `[data-theme="light"]`
  blocks, rather than hardcoded values. New tokens added beyond the
  original set: `--bg-header`, `--bg-input`, `--bg-skeleton`,
  `--border-strong`, `--accent-purple`, `--accent-amber`, `--accent-red`,
  `--shadow-elevation-{low,medium,high}`, `--text-on-accent`.
- Added a universal 150ms transition on background/border/colour/shadow
  for a smooth (not jarring) theme switch.
- Added fluid typography: `html { font-size: clamp(15px, 0.9vw + 12px, 19px) }`
  — scales smoothly from small phones up through 4K/8K displays.
- Added `.app-container` (max-width 1600px) so content doesn't stretch
  into an unreadable single strip on very large monitors.
- New Zustand store `useThemeStore.js`: reads `localStorage['senova-theme']`
  or falls back to `prefers-color-scheme`, persists on every change.
- New `ThemeToggle.jsx` component: a sliding pill switch with sun/moon
  icons, added to the header.
- **Flash-of-wrong-theme fix**: added an inline `<script>` in
  `index.html`, executed before `<div id="root">` even parses, that
  synchronously sets `data-theme` on `<html>` from
  `localStorage`/`prefers-color-scheme` before React mounts.

### Full component theme-awareness audit
Every component that previously used hardcoded Tailwind colour classes
(`slate-*`, `emerald-*`, raw hex values) was rewritten to use the CSS
variables instead: `Loader.jsx`, `Card.jsx`, `Button.jsx`,
`ErrorBoundary.jsx`, `FileDropzone.jsx`, `ColumnMappingScreen.jsx`,
`RowErrorsBanner.jsx`, `SummaryStats.jsx`, `PnLReportTable.jsx`,
`TransactionLedgerTable.jsx`, `App.jsx`, `Dashboard.jsx`, `Upload.jsx`.

**Charts required a different approach**: Recharts renders SVG with
literal JS colour strings, which can't read CSS classes. Created
`frontend/src/components/charts/useChartTheme.js` — reads the *live*
resolved value of each CSS variable via `getComputedStyle`, re-computed
whenever the theme store's `theme` changes. Rewrote `LineChart.jsx`,
`BarChart.jsx`, `CategoryPieChart.jsx` to consume this hook.

A full-codebase grep sweep confirmed zero remaining hardcoded
theme-breaking colours; the only intentional exceptions are semantic
status badges (red/amber/green — meant to stay visually consistent
regardless of theme) and Google's fixed 4-colour "G" logo on the sign-in
button.

### Typography & premium font
Added **Plus Jakarta Sans** (a premium geometric sans-serif, loaded via
Google Fonts with `preconnect` for performance) as the primary typeface,
and **JetBrains Mono** for numeric/tabular data. `tailwind.config.js`
registers these as `fontFamily.sans`/`.mono`, and adds new large-display
breakpoints: `xs` (400px), `3xl` (1920px), `4k` (2560px), `8k` (3840px).

### Mobile-first responsive fixes
- Wrapped the P&L statement table in `overflow-x-auto` (it was missing
  horizontal scroll on narrow screens).
- Made the `PnLReportTable` header and the `TransactionLedgerTable`
  pagination row stack vertically on mobile instead of squeezing into a
  single row.
- Increased touch targets to a 40px minimum on: date-filter buttons,
  view-tab buttons, header nav links, and the `.filter-select` dropdown
  (used by the column-mapping screen) — all previously below the ~44px
  accessibility guideline.
- Confirmed `.app-container`'s 1600px cap already correctly bounds the
  charts grid on 4K/8K displays without needing an extra grid column
  (which would have made individual charts too cramped).

### Vercel deployment compatibility
- `frontend/vercel.json` gained explicit `buildCommand`,
  `outputDirectory`, and `framework: "vite"` fields, alongside the
  existing rewrites (confirmed the `/upload/(.*)` and `/analytics/(.*)`
  wildcard patterns already correctly cover every new sub-route added
  this session — `/confirm-mapping`, `/report`, `/ledger`,
  `/report.pdf` — since `(.*)` captures the entire remaining path).
- Verified via a test build with `VITE_API_URL` set that the value is
  correctly statically embedded into the built JS bundle — confirming
  the recommended production setup (point `VITE_API_URL` directly at the
  deployed backend) works as intended.
- `backend/.env.example`'s `CORS_ORIGINS` comment expanded to explicitly
  instruct adding the Vercel production domain post-deployment.
- Root `.gitignore` gained `frontend/.vercel/` (the Vercel CLI's local
  cache directory).

### Light-theme visibility fixes (follow-up correction)
After the initial theme system shipped, the user reported the light
theme's background was too flat/bright and cards had no visible
separation from it — the opposite problem of dark mode, where content
"pops" clearly. Retuned every light-theme CSS variable:
- `--bg-primary`: `#f6f7fb` → `#eef1f6` (a slightly deeper blue-gray tint,
  so white cards visibly separate from it).
- Card shadows (`--shadow-elevation-*`): changed from single soft shadows
  to **dual-layer shadows** with meaningfully higher opacity (e.g. low
  elevation went from one `0.06`-opacity shadow to two stacked
  `0.08`/`0.06`-opacity shadows) — cards are now clearly visible, not
  just theoretically distinguishable.
- `--border-subtle`/`--border-strong`: opacity increased so card edges
  are clearly defined.
- `--text-secondary`: darkened from `#475569` to `#334155` for stronger
  readability.
- All accent colours (`--accent-blue`, `--accent-green`, etc.) deepened
  slightly for better contrast against the lighter surface.
- `--bg-input` given a subtly different shade (`#f8fafc`) from the page
  background so inputs/dropdowns have their own visual depth.

### Login page left-panel light-theme fix (second follow-up correction)
The user reported that on the login page specifically, the left brand
panel's background stayed dark-navy in **both** themes (an oversight —
it was intentionally hardcoded, as a "permanent brand panel" design
choice like Stripe/Linear signup pages), which meant in light mode its
text (reading CSS variables tuned for a *light* background) rendered as
near-invisible dark-on-dark.

**Fix**: `Login.jsx` now reads the active theme via `useThemeStore` and
picks between two fully-defined colour sets for the left panel — a dark
navy gradient with light text/icons for dark mode, and a new soft light
blue-gray gradient (`#e0ecf7` → `#eef3fa` → `#f4f7fb`) with dark text/icons
for light mode. Every element inside the panel (brand name, headline,
body copy, all 3 feature-list items' titles/descriptions/icon boxes,
copyright line) now uses this theme-resolved colour set instead of the
global CSS variables (which are tuned for a light *page* background, not
this panel's own switching background).

---

## Part 7 — Deployment troubleshooting (in progress)

User attempted to deploy to Vercel and hit a `react-scripts: command not
found` build error, plus a GitHub Pages 404, plus noted the repo had no
README.

**Diagnosis**:
- The `react-scripts` error indicates Vercel's dashboard **Root
  Directory** setting is not pointed at `frontend/` (or a stale
  "Create React App" framework preset is cached from initial project
  setup) — confirmed via a full-repo grep that no file anywhere
  references `react-scripts`; this project has never used Create React
  App, only Vite.
- The GitHub Pages 404 is unrelated to this app's actual deployment
  target — GitHub Pages was seemingly enabled on the repo at some point,
  but this app was never built for static-only hosting (it needs a
  backend API), and no GitHub Pages workflow exists in the repo.

**Fixes applied**:
- Created the root-level `README.md` (previously missing) with full
  project structure, local dev setup, and step-by-step Vercel deployment
  instructions — including the exact "Root Directory → frontend" fix.
- Documented that GitHub Pages should be explicitly disabled in the
  repo's Settings → Pages (Source → "None") to avoid the confusing 404,
  since this SPA fundamentally cannot run on Pages' static-only hosting.

When Vercel then suggested a "multi-service" monorepo `vercel.json`
(auto-detecting both `frontend/` as a Vite web service and `backend/` as
a FastAPI web service), it was flagged as **incompatible with this
backend's architecture**: Vercel/Netlify's Python support is
serverless-only, and this backend depends on persistent local-disk file
storage between requests plus a long-running background `asyncio` sweep
task — neither of which survives in a stateless, per-invocation
serverless container. Recommended keeping the existing split-deployment
model (frontend on Vercel/Netlify, backend on an always-on host like
Render/Railway/Fly.io) rather than adopting the multi-service preset,
pending the user's final decision.

*(This part of the session was still in progress — pure documentation
was requested next, which produced this file plus `PROJECT_OVERVIEW.md`
and `ARCHITECTURE.md`.)*

---

## Files created this session

- `README.md` (root)
- `PROJECT_OVERVIEW.md` (root)
- `ARCHITECTURE.md` (root)
- `CHANGELOG_SESSION.md` (root, this file)
- `.gitignore` (root)
- `backend/.env`, `backend/.env.example`
- `backend/app/services/pdf_report.py`
- `frontend/.env`, `frontend/.env.example`
- `frontend/src/services/firebase.js`
- `frontend/src/store/useThemeStore.js`
- `frontend/src/components/common/ThemeToggle.jsx`
- `frontend/src/components/upload/ColumnMappingScreen.jsx`
- `frontend/src/components/dashboard/PnLReportTable.jsx`
- `frontend/src/components/dashboard/TransactionLedgerTable.jsx`
- `frontend/src/components/charts/useChartTheme.js`
- `testing/narrow_range_7days.csv`
- `testing/wide_range_6months.csv`
- `testing/README.md`

## Files deleted this session

- `backend/app/services/supabase_client.py` (dead/deprecated)
- `frontend`'s `html2canvas` and `jspdf` npm dependencies (uninstalled)
- `@react-oauth/google` npm dependency (uninstalled)
- 80+ orphaned files in `backend/temp_uploads/`
