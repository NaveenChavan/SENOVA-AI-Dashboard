# C2 change manifest

## Backend

- `backend/app/models/schemas.py`
  - Added `row_count` to analytics responses.
  - Added `DimensionOptionsRequest` and richer `DimensionOption` metadata.
  - Raised allowed filter-value count to 5000.

- `backend/app/services/query_engine.py`
  - Custom date range validation and clamping to file min/max.
  - Latest-day window resolved from the file's max date.
  - Dimension-option search and cascade endpoint logic.
  - Time window is resolved before dimension filters so `Latest day` never changes because of a category filter.
  - Dynamic option totals/selected counts.

- `backend/app/api/routes/analytics.py`
  - Added `POST /analytics/{file_id}/dimensions/options`.
  - Analytics payloads now report explicit `row_count`.

## Frontend

- `frontend/src/components/dashboard/FilterPanel.jsx`
  - Compact bar, active chips, group badge.
  - Fixed/portalled drawer with Apply / Clear all.
  - Searchable Item and Invoice No options.
  - Category ↔ Item cascade.
  - Date presets, validation, clamping.
  - Tall scrollable option list.

- `frontend/src/store/useSalesStore.js`
  - Added dimension-option fetcher.
  - Added both cancellation and latest-request sequence protection.

- `frontend/src/pages/Dashboard.jsx`
  - Latest-day label from file data.
  - Explicit row-count empty-state handling.
  - Loading-safe Overview.
  - Separate sticky tab bar so tables do not sit underneath it.

- `frontend/src/index.css`
  - Drawer/bar/table sticky styles only; existing theme variables remain in use.

## Tests

- `backend/tests/test_c2_filters.py`
  - Required numerical regression cases.
  - Date clamp/reverse validation.
  - Item/category cascading.
  - Server-side Invoice search.

- `frontend/src/__tests__/panels.test.jsx`
  - Group-count badge.
  - Search boxes / tall list controls.
  - Latest-day label.
  - Apply semantics.
  - Cascading options.
  - Loading-state behavior.

- `frontend/src/__tests__/interactions.test.jsx`
  - Stale-response guard.

## Validation status

- Backend Python syntax: PASS.
- Frontend JS/JSX syntax parse: PASS.
- CSS parse: PASS.
- Independent fixture numerical checks: PASS.
- Full repository backend suite: **not runnable from the supplied partial archive**.
- Full repository frontend suite: **not runnable from the supplied partial archive**.
