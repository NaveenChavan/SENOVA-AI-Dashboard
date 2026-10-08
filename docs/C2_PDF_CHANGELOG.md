# SENOVA PDF redesign change log

## Changed

- Replaced the single CA-style PDF renderer with a dual renderer:
  - one-page visual executive PDF
  - detailed multi-page financial PDF
- Added daily financial summary: every calendar date in the selected window, with transactions, units, revenue, cost, profit and margin.
- Detailed ledger export now includes every row in the selected slice instead of the old 500-row print cap.
- Added fail-closed reconciliation between KPI totals, P&L, category totals and daily totals.
- Added `POST /analytics/{file_id}/visual-report.pdf`.
- Kept `POST /analytics/{file_id}/report.pdf` as the detailed report endpoint.
- Changed the existing single dashboard CTA to request both PDFs using the same filter state.
- Added scoped PDF regression tests.

## Intentionally unchanged

- Dashboard financial calculation logic.
- AI column mapping / Tier 2 routing.
- Existing filter calculations.
- Unrelated screens and styles.

## Validation limitation

The supplied source bundle is partial and does not contain the full repository test configuration or the full query engine module, so a full-repository suite cannot honestly be claimed as executed from this bundle alone. The PDF renderer itself was syntax-checked and exercised against the supplied electronics fixture; the visual export rendered to exactly one A4 landscape page.
