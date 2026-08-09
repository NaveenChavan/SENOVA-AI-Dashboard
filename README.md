# SENOVA AI Dashboard

AI-powered retail sales analytics dashboard for Indian MSMEs and garment
shops. Upload a daily sales CSV/Excel file — SENOVA validates every row,
lets you confirm your own column layout (every shop's export format is
different), and then produces automated findings, revenue forecasts,
reorder intelligence, eight ways to chart the same data, a CA-style
financial report (P&L statement + transaction ledger), and a downloadable
PDF report.

Every calculation is done in-house with Pandas/NumPy. No language model,
no third-party analytics service — your sales data never leaves your
backend, and no figure in the app is ever generated rather than computed.

## What it does

### Automated insights
A row of plain-language findings sits above the charts, each one written
from a template filled with computed numbers:

- **Revenue anomalies** — robust z-score (`0.6745 × (x − median) / MAD`) on
  the zero-filled daily series. MAD is used instead of standard deviation
  because a single freak day inflates a std-dev enough to hide itself.
  Flagged days are also ringed in red on the trend chart.
- **Movers** — the biggest gainer and decliner versus the previous period,
  ranked by rupee change (not %) so a 300% jump on a ₹50 item can't outrank
  a ₹40,000 collapse.
- **Margin leaks** — high-revenue items whose margin sits far below their
  category median, or below zero.
- **Concentration** — the Pareto check: how few items make 80% of revenue.
- **Timing** — best versus worst weekday, once each weekday has enough
  observations to mean anything.
- **Dead stock** — items with no sale for 30+ days.

Checks that the data is too small to support are skipped and reported as
skipped, rather than computed on noise.

### Forecasting
Revenue projection for the next 7/14/30 days: a recency-weighted
least-squares trend (14-day half-life) multiplied by weekday seasonal
indices (median of `actual ÷ trend`, normalised and clamped). The chart
shows a solid actual line, a dashed forecast continuation and an 80%
confidence band (`ŷ ± 1.28σ√(1 + h/n)`).

Accuracy is backtested on a 7-day holdout and shown as `100 − MAPE`, so
you can see how much to trust it. Under 14 days of history the endpoint
refuses to forecast and says why; under 21 days it uses the trend alone
without weekday seasonality.

### Inventory & reorder intelligence
Per item: sales velocity (per calendar day and per active day), trend
factor (late-window speed ÷ early-window speed), ABC class (A = the items
making the first 80% of revenue, B = the next 15%, C = the tail), ageing
bucket, and a 0–100 reorder-priority score blending velocity, trend and
recency.

If your file maps a stock column (`Stock`, `Closing Stock`, `Balance Qty`,
`On Hand`), it also computes real days-of-cover, reorder alerts and the
working capital locked in each item. Without it those columns are absent
and the panel explains how to unlock them — a guessed days-of-cover would
be worse than none.

### Chart studio — eight views, one payload
Pick any measure (revenue, profit, cost, units, transactions, margin %,
average price, discount) against any dimension the file contains, then
switch freely between:

| View | Question it answers |
|------|--------------------|
| Bars | How do groups compare? |
| Ranking (horizontal bars) | Same, when names are long |
| Donut | What is the whole made of? (top 6, rest folded into "Other") |
| Combo | Where is revenue high but margin thin? |
| Pareto | How concentrated is the business? |
| Bubble | How do price and volume relate? (size = revenue) |
| Treemap | Which groups dominate, at a glance? |
| Heatmap | Which weekdays actually sell? |

The API pre-computes every measure per group, so switching view or chart
type never triggers a new request. Every view has a **Table** toggle,
since scatter/treemap/heatmap are poor for screen readers, and clicking any
bar, slice, tile or table row drills into the transactions behind it.

### Filters and drill-down
Multi-select filters on any dimension the file contains, plus a custom
date range alongside the five presets. Filters are applied server-side
*before* aggregation, so the KPI cards, charts, insights, inventory table,
P&L and the exported PDF always describe the same slice. The whole view
state (tab, date window, filters) lives in the URL, so a filtered view can
be refreshed or shared with your accountant.

### Column mapping — built for real shop exports
The alias map covers the headers real Indian retail software produces —
Tally (`Voucher Date`, `Particulars`, `Stock Group`), Vyapar/Marg/Busy
(`Bill Date`, `Item Name`, `Rate/Unit`, `Taxable Value`, `Purchase Rate`),
GST invoice registers, and Shopify/Amazon/Flipkart order dumps — plus
optional fields that unlock extra analysis:

- **Extra amounts:** `Line Total`, `Discount`, `Tax`, `Stock On Hand`
- **Extra breakdowns:** `Branch`, `Payment Mode`, `Customer`,
  `Salesperson`, `Brand`, `Size`, `Colour`, `Invoice No`

One correctness note worth knowing: an `Amount` / `Net Amount` /
`Taxable Value` column holds a **line total**, not a unit price, so it maps
to `Line Total` and the unit price is derived as `Line Total ÷ Quantity`.
Mapping it to `Selling Price` would inflate revenue by the quantity factor
on every row.

## Project structure

```
senova-ai-dashboard/
├── frontend/   React 18 + Vite + Tailwind CSS + Firebase Auth + Recharts + Zustand
├── backend/    FastAPI + Pandas + NumPy + ReportLab (PDF generation)
├── docs/       Architecture, changelogs and session notes (see docs/README.md)
└── testing/    Sample CSV files for manual testing
```

Frontend and backend are deployed **separately** — frontend to Vercel,
backend to any Python host (Railway, Render, Fly.io, etc.).

## Documentation

Deeper technical docs, changelogs and past session notes live in
[`docs/`](docs/README.md) — start there for architecture, the Pro
upgrade feature reference, and the UI/accuracy audit.

## API

All routes require a verified Firebase ID token, and every file is bound
to the user who uploaded it — another signed-in user asking for your
`file_id` gets a 404.

### Upload (two steps, because every export differs)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload/` | Save the file, return the guessed column mapping, the optional fields available, and sample rows |
| `POST` | `/upload/{file_id}/confirm-mapping` | Apply the confirmed mapping, validate every row, report the data's real date span |

### Analytics — Pro (`POST`, shared `AnalysisQuery` body)

Body: `{ "time_filter": "all|today|week|30days|month|custom", "start_date": …, "end_date": …, "filters": { "branch": ["MG Road"] } }`

| Path | Returns |
|------|---------|
| `/analytics/{id}/summary` | KPIs with trend arrows, top items, category split, daily trend, dead stock |
| `/analytics/{id}/chart-data` | Chart-ready points (+ `dimension`, `measure`, `top_n`) with every measure precomputed |
| `/analytics/{id}/heatmap` | Weekday × week intensity grid with a numeric legend range |
| `/analytics/{id}/insights` | Automated findings + the dates flagged as anomalies |
| `/analytics/{id}/inventory` | Velocity, ABC, ageing, reorder priority (+ cover/capital when stock is mapped) |
| `/analytics/{id}/forecast` | Projection with confidence band and backtested accuracy (+ `horizon`) |
| `/analytics/{id}/report` | CA-style P&L + category ledger |
| `/analytics/{id}/ledger` | Paginated transaction register (+ `page`, `page_size`) — also powers drill-down |
| `/analytics/{id}/report.pdf` | Full PDF: findings, P&L, category ledger, forecast, reorder list, register |
| `GET /analytics/{id}/dimensions` | Which dimensions this file supports, their values, and its date range |

### Analytics — classic (`GET`, unchanged for existing consumers)

`GET /process/{id}`, `GET /analytics/{id}?time_filter=`,
`/analytics/{id}/report`, `/analytics/{id}/ledger`,
`/analytics/{id}/report.pdf`, and `GET /health`.

## Security

- **Firebase ID token** verified on every route (signature, expiry,
  revocation).
- **Ownership check on every read.** The uploader's identity is stored in a
  `{file_id}.meta.json` sidecar and re-checked on every request; a mismatch
  returns 404, not 403, so the API never confirms that another user's file
  exists.
- **`file_id` format validation** (`^[0-9a-f]{32}$`) before any filesystem
  access.
- **No dynamic query construction.** Dimensions and measures are closed
  enums; filter values are applied with `Series.isin`. Nothing user-supplied
  ever reaches `DataFrame.query`, `eval` or a string-built expression.
- **Bounded inputs:** ≤8 filter keys, ≤50 values each, `top_n` ≤ 50,
  `page_size` ≤ 1000, forecast horizon ≤ 90 days, ≤100 columns per upload,
  upload size capped by `MAX_UPLOAD_SIZE_MB`.
- **Bounded compute:** normalised frames are cached in a small LRU (8
  entries, ≤300k rows) keyed on file mtime + mapping, so repeated filter
  changes don't re-parse a 50k-row Excel file — and an unbounded cache
  can't become a memory DoS.
- **NaN/Infinity are never serialised.** Every number leaving the API goes
  through `safe_float`/`safe_int`, because bare `NaN` is invalid JSON and
  would break `JSON.parse` in the browser.
- **Uploads are temporary** — a TTL sweep removes files and both sidecars
  after `UPLOAD_TTL_MINUTES`.
- **One new frontend dependency, pinned exactly.** The UI redesign added
  [`motion`](https://motion.dev) (the actively-maintained successor to
  Framer Motion) at an exact pinned version (`12.42.2`, no `^`/`~` range) for
  entrance/exit animation and the drill-down panel's slide-over transition.
  It ships no network calls and has no access to sales data — it only
  animates DOM nodes already rendered by React. This is intentionally the
  **only** new third-party runtime dependency introduced by the redesign; no
  icon libraries, animation-adjacent utility packages, or CSS frameworks
  were added beyond it. The backend added nothing.

## Accessibility & UX

Built against the [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
design guidance (installed at `.kiro/steering/ui-ux-pro-max/`), resolved
for this project as a **Data-Dense Dashboard**:

- SVG icons only — no emoji as icons.
- Visible `:focus-visible` rings everywhere; `prefers-reduced-motion` is
  honoured; chart animations are off so filter changes are instant.
- Severity, trend and class are conveyed by text/icon *and* colour, never
  colour alone; heatmaps ship a numeric legend; scatter/treemap/heatmap all
  have a table alternative.
- Every table scrolls horizontally instead of breaking the layout; every
  empty state offers the action that fixes it; skeletons reserve real
  layout height so nothing jumps.
- Deep-linkable view state, keyboard-navigable tabs, and a drill-down
  dialog with focus management and Escape-to-close.

## Local development

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env      # fill in Firebase service-account path, or set DISABLE_AUTH=true for local testing
uvicorn app.main:app --reload
```

Runs on `http://127.0.0.1:8000`.

Tests (132 of them, covering the alias map, window/filter logic,
aggregation, insight maths, inventory, forecasting, and the API's security
rules):

```bash
pip install -r requirements-dev.txt
pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env      # fill in your Firebase web config + leave VITE_API_URL empty for local dev
npm run dev
```

Runs on `http://localhost:5173`. The Vite dev server proxies `/api/*` to the
backend at `127.0.0.1:8000`, stripping the `/api` prefix (see
`frontend/vite.config.js`) — no extra setup needed locally. The prefix exists
so API traffic can't collide with the SPA's own client-side routes: proxying
`/upload` directly meant a page reload at `/upload` was forwarded to the
backend instead of serving the app.

Component tests (all eight chart views plus the four feature panels):

```bash
npm test
```

## Deploying the frontend to Vercel

**Important — Root Directory setting:** this is a monorepo (frontend +
backend in one repo). When creating the Vercel project:

1. Import the GitHub repo into Vercel.
2. In **Project Settings → General → Root Directory**, set it to
   `frontend` (not the repo root). This is required — without it, Vercel
   can't find `frontend/package.json` and may fall back to a wrong
   auto-detected framework/build command.
3. Vercel should auto-detect **Vite** as the framework once Root
   Directory is set (confirmed by `frontend/vercel.json`, which also sets
   `buildCommand`, `outputDirectory`, and `framework` explicitly as a
   safety net).
4. Add these Environment Variables in Vercel (Project Settings →
   Environment Variables) — copy values from `frontend/.env.example`:
   - `VITE_FIREBASE_API_KEY`
   - `VITE_FIREBASE_AUTH_DOMAIN`
   - `VITE_FIREBASE_PROJECT_ID`
   - `VITE_FIREBASE_STORAGE_BUCKET`
   - `VITE_FIREBASE_MESSAGING_SENDER_ID`
   - `VITE_FIREBASE_APP_ID`
   - `VITE_API_URL` — your deployed backend's full URL (e.g.
     `https://your-backend.onrender.com`). This makes the frontend call
     the backend directly; the rewrites in `frontend/vercel.json` are a
     fallback and can be left as-is or removed once `VITE_API_URL` is set.
5. Deploy. If a build still fails with a `react-scripts` or other
   Create-React-App-related error, it means Root Directory (step 2) is
   not actually saved — re-check that setting; it's the most common cause
   of this specific error, since nothing in this codebase uses CRA.

## Deploying the backend

Any host that runs a Python ASGI app works (Railway, Render, Fly.io,
etc.). Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set these environment variables on the host (see `backend/.env.example`
for the full list and explanations):

- `CORS_ORIGINS` — include your Vercel production domain here, e.g.
  `https://your-app.vercel.app`
- `FIREBASE_SERVICE_ACCOUNT_PATH` and `FIREBASE_PROJECT_ID` — required
  unless `DISABLE_AUTH=true` (local dev only — never set this in
  production)
- `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `UPLOAD_TTL_MINUTES`,
  `UPLOAD_SWEEP_INTERVAL_MINUTES` — upload storage tuning, sensible
  defaults are already set

## Note on GitHub Pages

This app is **not** configured for GitHub Pages and won't work there —
it's a client-side-routed React SPA that needs a backend API, which
GitHub Pages (static hosting only) can't provide. Use Vercel (frontend)
+ a Python host (backend) as described above.

## Tech stack

- **Frontend:** React 18, Vite, Tailwind CSS, Zustand, Firebase Auth,
  Recharts, React Router, [Motion](https://motion.dev) (animation), Space
  Grotesk (display typeface, headlines only — body/UI text stays on Plus
  Jakarta Sans) (tests: Vitest + Testing Library)
- **Backend:** FastAPI, Pandas, NumPy, ReportLab (PDF), Firebase Admin SDK
  (token verification) (tests: pytest)
