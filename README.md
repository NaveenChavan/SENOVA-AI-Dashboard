# SENOVA AI Dashboard

AI-powered retail sales analytics dashboard for Indian MSMEs and garment
shops. Upload a daily sales CSV/Excel file — SENOVA validates every row,
lets you confirm your own column layout (every shop's export format is
different), and generates instant revenue/profit/margin analytics, a
CA-style financial report (P&L statement + transaction ledger), and a
downloadable PDF report.

## Project structure

```
senova-ai-dashboard/
├── frontend/   React 18 + Vite + Tailwind CSS + Firebase Auth + Recharts
├── backend/    FastAPI + Pandas + ReportLab (PDF generation)
└── testing/    Sample CSV files for manual testing
```

Frontend and backend are deployed **separately** — frontend to Vercel,
backend to any Python host (Railway, Render, Fly.io, etc.).

## Local development

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env      # fill in Firebase service-account path, or set DISABLE_AUTH=true for local testing
uvicorn app.main:app --reload
```

Runs on `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env      # fill in your Firebase web config + leave VITE_API_URL empty for local dev
npm run dev
```

Runs on `http://localhost:5173`. The Vite dev server proxies `/upload`,
`/process`, `/analytics`, `/health` to the backend at `127.0.0.1:8000`
(see `frontend/vite.config.js`) — no extra setup needed locally.

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
  Recharts, React Router
- **Backend:** FastAPI, Pandas, ReportLab (PDF), Firebase Admin SDK
  (token verification)
