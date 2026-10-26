# Phase 1 Implementation Summary: Baseline, Supplied Assets, and Two-Field Upload Rule

## 1. Overview
In accordance with the **SENOVA Column Dictionary Improvement Playbook (Phase 1)**, this phase establishes:
1. **Auditable Asset Baseline**: Audited current codebase aliases and supplied assets (`SENOVA_real_world_header_starter_pack`).
2. **Two-Field Upload Rule**: Relaxed strict 6-column mandate so upload confirmation requires only:
   - **Path A**: Date + Line Total
   - **Path B**: Date + Quantity + Selling Price
   - Category, Item, Cost Price, MRP, Discount, Tax, etc., are strictly optional for upload confirmation.
3. **Honest Degradation**: Unmapped optional roles result in explicit `"Not available: needs <X>"` status rather than fabricated zeros or broken pipelines.
4. **Deterministic Classification of Unmapped Extra Columns**: Unmapped columns (up to a 30-column cap) are classified into:
   - Date-like (`date_like` -> stored-only)
   - ID-like (`id_like` -> stored-only, leading zeroes preserved)
   - Personal/PII (`personal` -> stored-only, masked, never exposed as facet or metric)
   - Numeric (`numeric` -> `x_meas:<slug>`, aggregated via sum or average if `%`/`pct`/`margin`/`rate`)
   - Low-cardinality text (`low_cardinality_text` -> `x_dim:<slug>`, extra filterable dimension)
   - Other free text (`other_text` -> stored-only)
   - Deterministic slug generation with collision handling (`_2`, `_3`).
5. **Per-File Sidecar Persistence & Key Isolation**: Sidecar `<file_id>.registry.json` persists extra column schemas; dynamic keys are validated strictly per file, rejecting cross-file or unauthorized keys with HTTP 422.
6. **Frontend Enhancements**:
   - `ColumnMappingScreen`: Enforces two-field rule for submission and presents non-blocking warnings for unmapped optional fields.
   - `FilterPanel`: Supports compact drawer mode with searchboxes for tall dimensions, staged filter updates (`Apply`), `aria-label="<N> active filter groups"` counting time filter, cascading dimensions (`fetchDimensionOptions`), and dynamic extra dimensions (`x_dim:`).
   - `ChartStudio`: Plots dynamic measures (`x_meas:`) with `(average, not sum)` badges where appropriate and slices by dynamic dimensions (`x_dim:`).
   - `SchemaOverviewPanel`: Displays the column coverage report detailing mapped columns, extra dimensions, extra measures, and stored-only classifications.
   - `SummaryStats`: Displays `"—"` and `"Not available: needs <X>"` rather than ₹0.

---

## 2. Modified & New Files

### Backend
- `backend/app/services/extra_columns.py` *(New)*:
  - Deterministic classification engine for unmapped columns (`classify_extra_columns`, `make_safe_slug`, PII detection, ID detection, date detection, average metric heuristic).
- `backend/app/services/file_handler.py`:
  - Added `save_extra_registry(file_id, registry)` and `load_extra_registry(file_id)`.
- `backend/app/models/schemas.py`:
  - Updated `MetricValue` with `available: bool = True` and `reason: str | None = None`.
  - Added `ExtraColumnInfo` and `ColumnCoverageReport` models.
  - Allowed dynamic `DimensionKey` and `MeasureKey` strings.
  - Added `extra_measures` and `extra_registry` to `DimensionsResponse` and `DynamicSchema`.
- `backend/app/utils/data_validator.py`:
  - Added `check_required_columns(cols)` enforcing Date + Line Total OR Date + Quantity + Selling Price.
  - Updated `_validate_columns_exist` and `normalize_dataframe` to preserve extra columns (up to 30), coerce extra measures, sanitize low-cardinality extra dimensions, preserve leading zeroes in string IDs, and only drop rows missing mandatory two-field requirements.
- `backend/app/services/sales_calculations.py`:
  - Guarded missing `Quantity`, `Selling Price`, `Cost Price`, and `Item` to emit `available=False` with `"Not available: needs <X>"` instead of calculating ₹0.
  - Updated `_prepare` to derive gross revenue directly from `Line Total` when unit rates are absent.
- `backend/app/services/query_engine.py`:
  - Added support for `x_dim:` and `x_meas:` across `aggregate`, `_dimension_series`, `apply_filters`, `dimension_options`.
  - Supported `mean` aggregation for average measures and `sum` for additive measures.
- `backend/app/api/routes/upload.py`:
  - Persisted extra registry sidecar on `confirm-mapping`.
- `backend/app/api/routes/analytics.py`:
  - Loaded extra registry in `_load_frame`.
  - Added dynamic key validation returning HTTP 422 for unauthorized, cross-file, or PII/stored-only keys.
  - Populated `ColumnCoverageReport` in `DynamicSchema`.
- `backend/tests/test_phase1_extra_columns.py` *(New)*:
  - Phase 1 acceptance suite verifying the 10-row fixture, Delivery Charge sum (22,480), GST % avg (15.05), City (4 values), Sales Rep (3 values), Order ID, Notes, Customer Phone, dynamic key isolation, and Path A/B uploads.

### Frontend
- `frontend/src/components/upload/ColumnMappingScreen.jsx`:
  - Enabled submit button whenever Date + Line Total OR Date + Quantity + Selling Price is mapped.
  - Added non-blocking guidance for unmapped optional fields.
- `frontend/src/components/dashboard/FilterPanel.jsx`:
  - Implemented drawer mode with staged filter actions (`Apply`), active filter group counter (`aria-label="<N> active filter groups"`), searchboxes for tall dimensions, and cascading options.
- `frontend/src/components/dashboard/SummaryStats.jsx`:
  - Renders `"—"` and unavailability reason when metrics are uncomputable.
- `frontend/src/components/charts/ChartStudio.jsx`:
  - Displays extra measures with `(average, not sum)` annotation and extra dimensions.
- `frontend/src/components/dashboard/SchemaOverviewPanel.jsx`:
  - Renders column coverage breakdown and unmapped column classifications.
- `frontend/src/store/useSalesStore.js` & `frontend/src/pages/Dashboard.jsx`:
  - Added support for `extraMeasures` and `extraRegistry`.

---

## 3. Verification & Test Results

### 1. Electronics Fixture Regression Check
```powershell
backend\.venv\Scripts\python.exe validation/verify_fixture.py
```
**Output:**
```
C2 fixture validation: PASS
Latest day: 2026-06-17 | rows=7 | revenue=49180 | profit=19750
Latest day + Power: rows=2 | revenue=13893
2026-03-19..2026-04-17 + Power: rows=60 | revenue=510327 | cost=301950 | profit=208377 | units=273
```
- Revenue: 5,757,679 | Cost: 3,450,780 | Profit: 2,306,899 | Units: 2,621 | Discount Given: 1,211,000 | Discount %: 17.38 *(Exact match)*.

### 2. Phase 1 Acceptance Suite
```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase1_extra_columns.py -v
```
**Output:**
```
============================= test session starts =============================
collected 5 items

backend/tests/test_phase1_extra_columns.py::test_extra_column_classification PASSED [ 20%]
backend/tests/test_phase1_extra_columns.py::test_thirty_column_cap_and_collision_handling PASSED [ 40%]
backend/tests/test_phase1_extra_columns.py::test_two_field_upload_path_a_date_and_line_total PASSED [ 60%]
backend/tests/test_phase1_extra_columns.py::test_two_field_upload_path_b_date_qty_selling_price PASSED [ 80%]
backend/tests/test_phase1_extra_columns.py::test_end_to_end_phase1_acceptance PASSED [100%]

============================== 5 passed in 2.62s ==============================
```

### 3. Full Backend Test Suite
```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/ -q
```
**Output:**
```
516 passed, 399 warnings in 48.20s
```

### 4. Full Frontend Vitest Suite
```powershell
cd frontend && npx vitest run
```
**Output:**
```
Test Files  10 passed (10)
     Tests  128 passed (128)
  Duration  28.03s
```

---

## 5. Phase 1 Corrected Replacement Overlay (`SENOVA_phase1_corrected_replacement.zip`)

Applied as a file overlay on 2026-10-12 following safety backup (`_backup_pre_corrected_overlay_1791759311.zip`).

### Key Refinements Addressed
1. **Long-History Path A Safe Forecasting**: Revenue forecast works across 30+ day horizons on `Date + Line Total` files without crashing when `Item` and `Quantity` are absent; item-level demand forecasts remain cleanly empty (`[]`).
2. **Explicit P&L Honest Degradation**: Cost of Goods Sold and Gross Profit line items are preserved in the P&L report table with `amount = null` (rendered as `—`) and explicit reasons (`"Not available: needs Quantity and Cost Price"`), never fabricated as ₹0.
3. **PII Precedence Over Date Shapes**: PII classification strictly precedes date parsing; date-like personal fields (such as `Customer DOB`) are classified as `personal`/`stored_only` and values are normalized as `[redacted]`.
4. **Strict Handling of Incomplete Numeric Extra Measures**: Unmapped numeric columns with missing/unparseable values are preserved as NaN and reject chart/heatmap aggregation with HTTP 422 `QueryError` rather than silently distorting calculations with zero-fills.
5. **Leading-Zero Identifier Preservation**: CSV string identifiers (e.g. `Order ID: 00101`) retain leading zeros without numeric truncation.
6. **Frontend Fix in `ChartStudio.jsx`**: Added `schemaReady = true` prop default to ensure Vitest suite and ChartStudio render without unhandled reference exceptions.
7. **End-to-End Test Suite**: Expanded `test_phase1_extra_columns.py` to 14 comprehensive tests covering 30-day Path A forecasting, PDF generation, PII date masking, and weighted average aggregations.

### Verification Run Results
- `python -m compileall -q app tests`: **0 errors** (PASSED)
- `python -m pytest tests/test_phase1_extra_columns.py tests/test_data_validator.py tests/test_dynamic_schema.py tests/test_pdf_exports.py -q`: **84 passed** (PASSED)
- `python -m pytest tests/ -q`: **514 passed** (PASSED)
- `npm test -- --run`: **128 passed** across 10 test files (PASSED)
- `npm run build`: **Built successfully** in 21.11s (PASSED)
- End-to-end Path A / Path B / Date PII / Dynamic Key Isolation verification script: **100% PASSED**

---

## 6. Phase 2.1 — Deterministic Evidence Rules Engine (`Module 2.1`)

Implemented strictly in accordance with the **SENOVA Playbook Phase 2 Module 2.1**:

### Key Deliverables
1. **Deterministic Ambiguity Engine (`backend/app/services/ambiguity_engine.py`)**:
   - Intercepts unresolved columns before escalation to Tier 2 (Gemini Flash).
   - Examines statistical distributions, neighbour columns, and value patterns locally with zero network calls and sub-millisecond execution.
   - **5 Core Rule Families**:
     - **Percentage Columns**: Detects standard Indian GST slabs ({0%, 5%, 12%, 18%, 28%}) to map to Tax, flags discount markers to Discount %, asks when ambiguous.
     - **Amount / Total Columns**: Protects against double-counting repeating invoice-level totals across multi-line orders (`_check_invoice_repeat`), auto-confirms line totals when `Qty × SP ≈ Value` matches ≥ 85% of rows.
     - **Rate / Price Columns**: Confirms line-level `Selling Price` when `Rate × Qty ≈ Line Total` matches, guards against invoice-constant rates (MRP / fixed fee), maps GST percentages.
     - **Name Disambiguation**: Resolves ambiguous name headers by checking categorical neighbours (e.g. if Customer / Client already mapped, second name column defaults to Item / Product, or flags Sales Rep / Vendor).
     - **Auxiliary Dates**: Confirms primary `Date` (mapped as canonical), routes secondary date columns (Delivery Date, ETA, Ship Date) as `stored_only` (`suggested_field=None`) with semantic labels.
   - **Defensive Safeguards**: Minimum row and invoice-group thresholds (`MIN_ROWS_FOR_EVIDENCE=5`, `MIN_GROUPS_FOR_INVOICE_EVIDENCE=2`), strict numeric coercion with NaN filtering, fallback to `decision="ask"` on any unexpected data or exception.

2. **Pipeline Integration (`backend/app/services/column_understanding.py`)**:
   - Sits directly between Tier 1 collision resolution and Tier 2 Gemini invocation.
   - Slices candidate columns (`needs_review=True` and not `recognised_unused`) and runs `evaluate_batch`.
   - When `decision="auto"`: updates `suggested_field`, sets `source="evidence"`, `route="local"`, marks `needs_review=False`, and attaches human-readable evidence facts.
   - When `decision="ask"`: preserves column for Tier 2 / manual mapping while pre-populating `evidence_facts` and `evidence_candidates` for Module 2.2.
   - Added `evidence_ms` to `PipelineTimings` tracking engine wall-clock execution time.

3. **Schema Extensions (`backend/app/models/schemas.py`)**:
   - `ColumnGuess`: Added `source: Literal["local", "gemini", "fallback", "pending", "evidence"]`.
   - `ColumnGuess`: Added additive optional fields `evidence_facts: List[str]`, `evidence_candidates: List[str]`, `evidence_reason: Optional[str]`.
   - `PipelineTimings`: Added `evidence_ms: float = 0.0`.

4. **Comprehensive Test Suite (`backend/tests/test_ambiguity_engine.py`)**:
   - 53 unit and regression tests covering all 5 rule families, statistical utilities (`_check_invoice_repeat`, `_check_multiplicative_identity`), batch evaluation, timing metrics, and Phase 1 Path A / Path B compatibility.

### Verification Run Results
- `python -m compileall -q app tests`: **0 errors** (PASSED)
- `pytest tests/test_ambiguity_engine.py`: **78 passed** in 1.58s (PASSED)
- `pytest tests/test_phase1_extra_columns.py tests/test_data_validator.py tests/test_dynamic_schema.py tests/test_pdf_exports.py tests/test_phase1_recording_fixes.py`: **95 passed, 1 skipped** (PASSED)
- Combined Module 2.1 + Phase 1 regression suite: **207 passed, 1 skipped** in 11.23s (PASSED)
- Full backend pytest suite (`tests/`): **603 passed, 1 skipped** in 47.98s (PASSED)
- Full frontend vitest suite (`npm test -- --run`): **130 passed across 10 test files** (PASSED)

---

## 7. Phase 2.1 Final Targeted Verification & Hardening

Completed targeted verification and edge-case hardening before Phase 2.1 sign-off:

1. **`_find_canonical_neighbour` Hardening**:
   - Accurately resolves mapping dicts (`{"Qty": "Quantity", "Amt": "Line Total"}`), canonical sets (`{"Quantity", "Line Total"}`), raw column sets (`{"Qty", "Amt"}`), and direct canonical headers.
   - Fixed tuple unpacking on `guess_canonical_column` (`guess, _ = guess_canonical_column(col)`) so alias matches correctly evaluate.
   - When multiple unmapped candidate columns alias to the same role without explicit mapping (e.g. `["Price1", "Price2"]`), returns `None` to prevent arbitrary or false matches.
   - When a column in `already_mapped` is committed to another role (e.g. `Rate -> MRP`), it is excluded from being falsely matched as a neighbour for `Selling Price`.
   - Added `exclude` parameter so the column currently being evaluated cannot match as its own neighbour.

2. **Claimed Role Isolation (`_is_claimed_by_another`)**:
   - Uniqueness guards for `Selling Price` and `Line Total` now use dedicated `_is_claimed_by_another` checking `already_mapped`, ensuring unmapped sibling columns in `df` are never misdiagnosed as already-claimed mappings.

3. **Selling Price Evidence Boundaries**:
   - Rejects fewer than 5 eligible rows (`MIN_ROWS_FOR_EVIDENCE = 5`).
   - Ignores null, non-numeric, zero, or negative quantities/prices (`qty > 0` and `price > 0` required for product match test).
   - Allows up to 1% rounding tolerance with a 0.01 floor to support GST tax-inclusive back-calculations and decimal rounding.
   - Strict 90% match threshold: exactly 90% (9/10) resolves cleanly to `Selling Price`; 80% (8/10) falls back to `ask`.
   - Batch evaluation with multiple candidate price columns correctly resolves the first and flags subsequent ones for user confirmation.

4. **Invoice Repeat Group Isolation & Missing Invoice ID Guarding**:
   - Single-row invoices are excluded from repeat ratio calculation (invoices with 1 line item trivially have 1 unique value and provide no repeat evidence).
   - Requires `MIN_GROUPS_FOR_INVOICE_EVIDENCE = 2` multi-row invoice groups (`len(g) >= 2`) before concluding a field repeats across line items.
   - Null (`None`, `NaN`), blank (`""`), whitespace-only (`"   "`), and placeholder tokens (`"nan"`, `"none"`, `"null"`, `"n/a"`) are strictly filtered out before grouping, preventing missing invoice IDs from being grouped together into fabricated multi-row invoice groups.
   - Correctly isolates repeated invoice totals from varying line-item amounts across mixed single-row, multi-row, and missing-ID datasets.

---

## 8. Module 2.2 — Grouped Clarification Dialog

### Overview
Implemented **Module 2.2: Grouped Clarification Dialog** as specified in the SENOVA Execution Playbook (pages 6–7) and user adjustments:
1. **Single Grouped Clarification Dialog (`GroupedClarificationDialog.jsx`)**:
   - Consolidates all open ambiguous column questions into a single accessible modal dialog (`role="dialog"`, `aria-modal="true"`), eliminating fragmented separate popups.
   - Displays human-readable explanations (`evidence_reason` or `reason`) and bullet points (`evidence_facts`) produced by the Module 2.1 evidence engine.
   - Shows 2–3 evidence-based candidate chips per ambiguous column directly from `evidence_candidates` without forcing arbitrary candidates. Any additional alternatives are visually distinguished as secondary options and are never auto-selected.
   - Strictly displays pre-masked sample values from `sampleRows` (`[redacted]`, `[email]`, `[phone]`, `[number]`), preserving all existing PII safeguards.
   - Includes "Something else" allowing the user to enter a sanitized, bounded clarification note (max 150 chars). Note text is treated purely as clarification metadata and requires an explicit valid role selection before a mapping is applied.
   - Includes per-column "Ignore this column" and dialog-level "Skip for now".

2. **Non-blocking Skip & Upload Rule Preservation**:
   - Dismissing or skipping the dialog never modifies or resets existing mappings.
   - Preserves the Phase 1 upload rule: Date + Line Total (Path A) OR Date + Quantity + Selling Price (Path B).
   - If the required conditions are met, skipping clarification leaves the "Confirm & analyse" button enabled and allows immediate analysis without blockers.

3. **Consistent User Choice Labeling**:
   - When the user selects a mapping in the dialog (or manually adjusts a table dropdown), it overrides automated suggestions for that upload.
   - In `ColumnMappingScreen`, columns chosen by the user display a dedicated `User choice` pill badge (`var(--accent-blue)`) with source tooltip `from your selection`.

4. **Backend Payload Validation (`backend/app/api/routes/upload.py`)**:
   - Validates `POST /upload/{file_id}/confirm-mapping` payload:
     - Rejects unknown column headers not present in `df.columns` with HTTP 400.
     - Rejects unknown or fabricated canonical targets with HTTP 400.
     - Rejects duplicate assignments to the same non-empty canonical role with HTTP 400.
     - Preserves legitimate empty/ignored column mappings (`""`).
     - Reuses existing `normalize_dataframe` two-field rule enforcement.

### Modified & New Files
- `frontend/src/components/upload/GroupedClarificationDialog.jsx` *(New)*:
  - Grouped modal component for ambiguous columns with evidence-backed candidates, pre-masked sample values, "Something else" note input and role select, and non-blocking skip.
- `frontend/src/components/upload/ColumnMappingScreen.jsx`:
  - Integrated `GroupedClarificationDialog`, clarification banner with count badge and trigger button, `userSelected` tracking, and `User choice` / `from your selection` badge in `ConfidenceBadge`.
- `backend/app/api/routes/upload.py`:
  - Added server-side validation in `confirm_mapping` rejecting nonexistent raw columns, invalid canonical fields, and duplicate target mappings.
- `frontend/src/__tests__/clarification_dialog.test.jsx` *(New)*:
  - 9 Vitest tests covering single dialog rendering, evidence candidate buttons, PII preservation, "Something else", non-blocking skip, and "User choice" badge updates.
- `backend/tests/test_confirm_mapping_validation.py` *(New)*:
  - 6 Pytest unit tests verifying Path A, Path B, unknown canonical fields, duplicate roles, nonexistent columns, and empty/ignored column preservation.

### Verification Results
- Vitest suite (`npm test -- --run`): **139 passed across 11 test files (0 failures)**
- Frontend production build (`npm run build`): **Success (0 errors, 47.68s)**
- Backend Module 2.2 focused tests (`pytest tests/test_confirm_mapping_validation.py`): **6 passed in 9.81s**
- Phase 1 regression suite (`pytest tests/test_phase1_extra_columns.py tests/test_phase1_recording_fixes.py tests/test_data_validator.py tests/test_pdf_exports.py`): **73 passed**
- Full backend suite (`pytest tests/`): **609 passed, 1 skipped**

