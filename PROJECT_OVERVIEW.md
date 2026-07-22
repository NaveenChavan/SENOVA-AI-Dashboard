# SENOVA AI Dashboard — Project Overview

Complete reference documentation for the SENOVA AI Dashboard project —
what it does, how it's built, and how every part of it works.

---

## 1. What is SENOVA?

SENOVA is an AI-powered retail sales analytics dashboard built for
**Indian MSMEs and garment/retail shops**. A shop owner uploads their
daily/weekly/monthly sales data (CSV or Excel export from whatever
billing software they use — Tally, Excel, custom POS, etc.), and SENOVA:

1. **Auto-detects their column layout** and lets them confirm/correct it
   (every shop's export format is different — SENOVA never assumes a
   fixed template).
2. **Validates every row** — flags bad dates, missing prices, negative
   quantities, etc. — but still processes every valid row instead of
   rejecting the whole file for one bad row ("partial success" model).
3. **Generates instant analytics**: revenue, profit, margin, top-selling
   items, dead stock (slow-moving inventory), category breakdowns, daily
   trend charts.
4. **Produces a CA-style (Chartered Accountant) financial report**: a
   proper Profit & Loss statement, a category-wise ledger, and a
   paginated row-by-row transaction register — presented as real tables,
   not just charts.
5. **Exports a structured PDF report** — real text and tables (built with
   ReportLab), not a screenshot — so it can be printed/shared/filed like
   an actual accounting document.
6. **Supports dark and light themes**, both designed to feel premium, with
   full responsive support from mobile phones up to 8K displays.

---

## 2. Who is this for?

Small and medium retail businesses in India — garment shops, general
stores, small distributors — who:
- Track sales in a spreadsheet or basic billing software (not a full ERP).
- Don't have an in-house data analyst.
- Want to see revenue/profit trends and identify slow-moving stock without
  manually building pivot tables every week.
- Need a report they can actually hand to their accountant.

---

## 3. Project structure

```
senova-ai-dashboard/
├── README.md                      Root-level project + deployment guide
├── PROJECT_OVERVIEW.md             This file
├── ARCHITECTURE.md                 Technical deep-dive (data flow, API contracts)
├── .gitignore                      Root-level ignore rules for both frontend & backend
│
├── frontend/                       React 18 + Vite SPA
│   ├── public/
│   │   ├── assets/logo.jpeg        Brand logo (dark navy hexagon, metallic "S")
│   │   ├── favicon.ico, favicon-*.png, apple-touch-icon.png, android-chrome-*.png
│   │   ├── icons.svg, site.webmanifest, sitemap.xml
│   ├── src/
│   │   ├── main.jsx                React root, wraps App in Router + HelmetProvider
│   │   ├── App.jsx                 Header (logo, nav, theme toggle, account menu) + layout shell
│   │   ├── index.css               Design system: CSS variables for dark/light themes,
│   │   │                           fluid typography, card/button/badge component classes
│   │   ├── routes/
│   │   │   └── AppRoutes.jsx       /login, /upload, /dashboard route definitions + AuthGuard wrapping
│   │   ├── pages/
│   │   │   ├── Login.jsx           Split-screen sign-in page (brand story + Google sign-in)
│   │   │   ├── Upload.jsx          File dropzone → column-mapping confirmation flow
│   │   │   └── Dashboard.jsx       Main analytics view: KPI tiles, charts, CA report tab, PDF export
│   │   ├── components/
│   │   │   ├── common/             Card, Button, Loader, ErrorBoundary, AuthGuard, ThemeToggle
│   │   │   ├── upload/              FileDropzone, ColumnMappingScreen
│   │   │   ├── dashboard/           SummaryStats, TopItems, DeadStockTable, RowErrorsBanner,
│   │   │   │                        PnLReportTable, TransactionLedgerTable
│   │   │   └── charts/              BarChart, LineChart, CategoryPieChart, useChartTheme (hook)
│   │   ├── store/
│   │   │   ├── useSalesStore.js    Zustand store: upload flow, analytics fetch, CA report, ledger
│   │   │   └── useThemeStore.js    Zustand store: dark/light theme state + persistence
│   │   └── services/
│   │       ├── api.js              Axios instance with Firebase-auth request interceptor
│   │       └── firebase.js         Firebase app init, Google sign-in, ID token helper
│   ├── index.html                  HTML shell, theme-flash-prevention inline script, Google Fonts
│   ├── vite.config.js              Dev server proxy (/upload, /process, /analytics, /health → :8000)
│   ├── tailwind.config.js          Custom breakpoints (xs, 3xl, 4k, 8k), font families
│   ├── vercel.json                 Vercel build config + API rewrites
│   ├── package.json / package-lock.json
│   ├── .env.example                Firebase web config + VITE_API_URL template
│   └── .env                        Actual local secrets (gitignored)
│
├── backend/                         FastAPI + Pandas + ReportLab
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, router registration, TTL-sweep background task
│   │   ├── core/
│   │   │   └── config.py           Env var loading (.env via python-dotenv), all config constants
│   │   ├── api/routes/
│   │   │   ├── upload.py           POST /upload/, POST /upload/{file_id}/confirm-mapping
│   │   │   └── analytics.py        GET /process/{id}, /analytics/{id}, /analytics/{id}/report,
│   │   │                            /analytics/{id}/ledger, /analytics/{id}/report.pdf
│   │   ├── services/
│   │   │   ├── file_handler.py     Disk I/O: save/read uploads, column-mapping persistence, TTL sweep
│   │   │   ├── sales_calculations.py  Core analytics engine (all Pandas aggregations)
│   │   │   └── pdf_report.py       ReportLab-based structured PDF generator
│   │   ├── models/
│   │   │   └── schemas.py          All Pydantic request/response models
│   │   └── utils/
│   │       ├── data_validator.py   Column-mapping detection + row-level validation/coercion
│   │       └── auth_verifier.py    Firebase ID token verification (FastAPI dependency)
│   ├── temp_uploads/                Uploaded files land here (gitignored except .gitkeep)
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                        Actual local secrets (gitignored)
│
└── testing/                         Sample CSV files for manual testing
    ├── README.md                   Explains what each test file demonstrates
    ├── narrow_range_7days.csv       7-day span — demonstrates filter auto-disabling
    ├── wide_range_6months.csv      ~6.5-month span — demonstrates all filters working
    ├── senova_stress_test_50k.csv  50,000-row large-file stress test
    ├── senova_ultimate_test_25k.csv 25,000-row test file
    ├── senova_30k_test_data.xlsx   30,000-row Excel test file
    └── generate_data.py / generate_test_v2.py  Scripts that generated the above test files
```

---

## 4. Tech stack

### Frontend
| Library | Purpose |
|---|---|
| React 18 | UI framework |
| Vite | Build tool / dev server |
| Tailwind CSS | Utility-first styling, extended with custom design tokens |
| Zustand | Lightweight global state (sales data, theme) |
| Firebase Auth (`firebase` SDK) | Google sign-in, ID token issuance |
| Axios | HTTP client, with an auth-token request interceptor |
| Recharts | Bar / line / pie charts |
| React Router | Client-side routing (`/login`, `/upload`, `/dashboard`) |
| react-helmet-async | Per-page `<title>` / meta tags |

### Backend
| Library | Purpose |
|---|---|
| FastAPI | Web framework / routing / OpenAPI docs |
| Pandas | All data validation and analytics calculations |
| Pydantic | Request/response schema validation |
| firebase-admin | Verifies Firebase ID tokens issued to the frontend |
| ReportLab | Generates the structured PDF financial report |
| openpyxl | Reads `.xlsx` uploads |
| python-dotenv | Loads `backend/.env` into the process environment |
| Uvicorn | ASGI server |

---

## 5. Core user flow

```
1. User signs in with Google (Firebase Auth) on /login
2. User drops a CSV/Excel file on /upload
   → POST /upload/ saves the file, returns a best-guess column mapping
3. User reviews/corrects the column mapping on-screen
   → POST /upload/{file_id}/confirm-mapping validates every row,
     persists the confirmed mapping, returns valid/error counts + date range
4. User is redirected to /dashboard?fileId=...
   → GET /analytics/{file_id}?time_filter=30days (default) loads:
     summary KPIs, top items, category breakdown, daily trend, dead stock
5. User can switch date filters (Today / Last 7 Days / Last 30 Days /
   This Month / All Time) — filters that would show identical results to
   "All Time" (because the data doesn't span that far) are auto-disabled
   with an explanatory tooltip + banner.
6. User can switch to the "Financial Report" tab
   → GET /analytics/{file_id}/report (P&L statement + category ledger)
   → GET /analytics/{file_id}/ledger?page=1&page_size=50 (paginated
     transaction register)
7. User can click "Export PDF"
   → GET /analytics/{file_id}/report.pdf streams a real structured PDF
     (not a screenshot) containing all of the above, capped at 500
     ledger rows with a note if the file has more.
8. User can toggle dark/light theme any time — persists across visits.
```

---

## 6. Data model — the 6 canonical fields

Every uploaded file, regardless of its original column names, is mapped
to these 6 fields before any analysis runs:

| Canonical field | Type | Example |
|---|---|---|
| `Date` | Date | `15-07-2025` or `2025-07-15` (both parsed) |
| `Category` | Text | `Electronics`, `Jackets` |
| `Item` | Text | `Wireless Mouse` |
| `Quantity` | Integer (> 0) | `10` |
| `Selling Price` | Number (≥ 0) | `1200.00` |
| `Cost Price` | Number (≥ 0) | `800.00` |

From these 6 fields, every metric in the app is derived:
- `Revenue = Quantity × Selling Price`
- `Cost = Quantity × Cost Price`
- `Profit = Revenue − Cost`
- `Margin % = Profit / Revenue × 100`

**Note:** `Cost Price > Selling Price` is explicitly allowed (not flagged
as an error) — clearance/loss-leader sales are a legitimate retail
scenario and should show as negative profit, not be rejected.

---

## 7. Authentication & security model

- **Frontend**: Firebase Authentication with the Google sign-in provider.
  On sign-in, Firebase issues a short-lived ID token (a signed JWT).
- **Every API request** from the frontend attaches this token as
  `Authorization: Bearer <token>` (handled automatically by an Axios
  interceptor in `frontend/src/services/api.js`).
- **Backend** verifies this token on every protected route using the
  Firebase Admin SDK (`firebase_admin.auth.verify_id_token`), which
  cryptographically checks the token's signature against Google's
  rotating public keys, plus expiry and issuer. This is standard
  JWT-based authentication — no custom token scheme was built, since
  Firebase's is already industry-standard and would only be weakened by
  reinventing it.
- **`DISABLE_AUTH=true`** is a local-development-only escape hatch (skips
  token verification, returns a fixed `dev-user@localhost`). It must never
  be set in a deployed/production environment.
- **CORS** is restricted to an explicit allow-list (`CORS_ORIGINS` env
  var) — not wildcarded.

---

## 8. Environment variables reference

### `backend/.env`
| Variable | Purpose | Example |
|---|---|---|
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:5173,https://your-app.vercel.app` |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to Firebase service-account JSON | `./firebase-service-account.json` |
| `FIREBASE_PROJECT_ID` | Firebase project ID | `senova-dashboard` |
| `DISABLE_AUTH` | Skip token verification (local dev only) | `false` in production |
| `UPLOAD_DIR` | Where uploaded files are stored on disk | `temp_uploads` |
| `MAX_UPLOAD_SIZE_MB` | Max accepted upload size | `50` |
| `UPLOAD_TTL_MINUTES` | How long a file stays on disk before the sweep deletes it | `120` |
| `UPLOAD_SWEEP_INTERVAL_MINUTES` | How often the cleanup sweep runs | `30` |

### `frontend/.env`
| Variable | Purpose |
|---|---|
| `VITE_FIREBASE_API_KEY` | Firebase web config (safe to expose client-side) |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase web config |
| `VITE_FIREBASE_PROJECT_ID` | Firebase web config |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase web config |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase web config |
| `VITE_FIREBASE_APP_ID` | Firebase web config |
| `VITE_API_URL` | Backend base URL (empty for local dev; set to deployed backend URL in production) |

---

## 9. Deployment model

- **Frontend** → any static host that supports SPA routing (Vercel,
  Netlify, etc.). Configured for Vercel via `frontend/vercel.json`.
- **Backend** → must be an **always-on** Python host (Render, Railway,
  Fly.io, a VPS, etc.) — **not** a serverless platform (Vercel Functions,
  Netlify Functions, AWS Lambda). This is because the backend:
  - Stores uploaded files on local disk between requests (not
    object storage), which serverless containers don't persist.
  - Runs a background `asyncio` task for the upload-cleanup sweep, which
    requires a long-lived process — serverless functions are invoked
    per-request and don't keep background tasks alive.

  Moving the backend to a serverless platform would require replacing
  local disk storage with S3/cloud storage and replacing the background
  sweep with a scheduled/cron job — a real architecture change, not a
  config tweak.

See `README.md` for step-by-step deployment instructions.

---

## 10. Known intentional design decisions (not bugs)

- **Filters can be disabled**: if an uploaded file's data only spans a
  few days, filters wider than that span (e.g. "This Month" on a 4-day
  file) are greyed out with a tooltip, and a banner explains why — this
  is by design, not a calculation error.
- **The PDF caps the printed transaction ledger at 500 rows**: files with
  tens of thousands of rows would produce an impractically long PDF; the
  in-app paginated ledger remains the way to browse every row.
- **Login page's left brand panel is intentionally dark in both themes'
  early design**, now fixed to switch between a dark and light gradient
  depending on the active theme (see `CHANGELOG_SESSION.md`).
