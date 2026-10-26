# SENOVA Phase 1 — Corrected Replacement Overlay

## Important: this is a file overlay, not a complete repository

This ZIP contains only the source/test files that need to be added or replaced. It does **not** contain the entire SENOVA repository, dependencies, environment files, secrets, or uploaded business data.

## Safe apply procedure

1. Make a backup or commit your current branch before copying anything.
2. Extract this ZIP into the **repository root** (the folder containing `backend/` and `frontend/`), preserving folder paths, and allow it to replace matching files.
3. Review the complete diff before accepting it. Do not merge or commit automatically.
4. Run the backend checks shown below in the project's intended Python environment.
5. Run the frontend tests/build in the project's intended Node environment. This review container did not have `frontend/node_modules`, so the Vitest suite could not be run here.
6. Do **not** begin Phase 2 until the project owner reviews the diff and explicitly approves Phase 1.

## Backend checks

From repository root:

```powershell
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests/test_phase1_extra_columns.py backend/tests/test_data_validator.py backend/tests/test_dynamic_schema.py backend/tests/test_pdf_exports.py -q
python -m pytest backend/tests/ -q
```

Or from `backend/`:

```powershell
python -m compileall -q app tests
python -m pytest tests/test_phase1_extra_columns.py tests/test_data_validator.py tests/test_dynamic_schema.py tests/test_pdf_exports.py -q
python -m pytest tests/ -q
```

Use the project's real installed dependencies for the complete suite. In the review container, `firebase-admin` and SendGrid were unavailable, so auth/email integration tests were not considered verified. The broad backend test run excluding `test_auth_routes.py` passed: **506 passed, 1 skipped**. The affected Phase 1/validation/schema/PDF tests passed: **87 passed**. There was one existing Pandas date parsing warning.

## Frontend checks

From `frontend/`:

```powershell
npm ci
npm test
npm run build
```

The modified JSX/JS source files passed a TypeScript transpile-based syntax check (12/12). This is not a substitute for Vitest or a production build.

## Scope of this replacement

- Two supported upload paths: `Date + Line Total`, or `Date + Quantity + Selling Price`.
- Missing `Category`, `Item`, `Cost Price`, and other optional fields do not reject otherwise valid sales rows.
- Revenue can continue from `Line Total` when optional quantity/rate cells are blank; unsupported dependent metrics remain unavailable.
- Per-file registry/strict dynamic-key validation for extra columns stays in place.
- Extra PII is stored-only and masked in the normalized analytics frame; PII classification takes priority over date-like shape (for example, a Customer DOB column).
- CSV identifiers retain leading zeros; Excel cells formatted with a pure zero mask (for example `00000`) are restored best-effort.
- Unknown/incomplete extra numeric measures are not silently treated as zero; charts/heatmaps explain that invalid or blank values must be corrected.
- Forecasting a long `Date + Line Total` file no longer crashes just because Item/Quantity are absent. The revenue forecast stays available; item-demand forecasts are empty/unavailable.
- P&L rows for unavailable cost/profit are retained with a dash and an explicit reason instead of silently omitting the lines or fabricating zeros.
- Blank Category/Item values preserve sales rows as `Unspecified`.
- Existing report routes and PDF export are regression-tested against the minimal Path A upload.

## Notes about the screen recording

The recording showed `The AI service timed out.` while deterministic insight cards and the dashboard remained visible. The Gemini prose step is optional and the current failure handling retains original deterministic insight text. This is not evidence that the core Phase 1 sales calculations failed. Root-cause work on Gemini/network/model credentials belongs in the explicitly gated later AI phase; do not change it without approval.
