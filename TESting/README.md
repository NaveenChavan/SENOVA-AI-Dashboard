# SENOVA Testing Files

Two sample CSVs to manually verify the smart date-filter disabling feature.

## 1. narrow_range_7days.csv
- 21 rows, all dated **15-07-2025 to 21-07-2025** (7 days span).
- **Expected behaviour after upload:**
  - "Today" and "All Time" filters stay active.
  - "Last 7 Days", "This Month", "Last 30 Days" should appear **greyed out /
    disabled** (hover over them to see the tooltip explaining why).
  - A sky-blue banner should appear above the filter row saying data only
    covers 7 days and wider filters are disabled — not a bug.
  - If you select a filter that later becomes disabled, the dashboard
    automatically falls back to "All Time".

## 2. wide_range_6months.csv
- 36 rows spread across **05-01-2025 to 21-07-2025** (~6.5 months).
- **Expected behaviour after upload:**
  - All 5 filters (Today, Last 7 Days, Last 30 Days, This Month, All Time)
    should be active/clickable.
  - Each filter should show a **different** revenue/profit total, proving
    the date-window logic is working correctly at a normal data scale.
  - No transparency banner should appear (span is wide enough).

## How to test
1. Start the backend (`uvicorn app.main:app --reload` from `backend/`,
   with `DISABLE_AUTH=true` in `backend/.env` for local testing without
   Firebase).
2. Start the frontend (`npm run dev` from `frontend/`).
3. Sign in, go to Upload, drop one of these files.
4. On the column-mapping screen, the columns should auto-match (they use
   the exact canonical header names) — just click "Confirm & analyse".
5. On the Dashboard, check the date-filter row against the expected
   behaviour above.
