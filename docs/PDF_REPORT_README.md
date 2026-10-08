# SENOVA Dual Financial PDF Export

This patch adds two separate PDF products behind the existing single export CTA:

- `senova-visual-financial-report-<id>.pdf` - one-page landscape executive report.
- `senova-detailed-financial-report-<id>.pdf` - multi-page financial/audit report.

Both reports use the same filtered analytics slice. The PDF layer is presentation-only; it does not invent figures or maintain a second financial calculation engine.

Before either report is returned, the backend reconciles KPI totals with P&L, category totals, and the daily summary. A mismatch returns HTTP 500 rather than silently producing a misleading report.

The detailed export includes every selected transaction row. The in-app ledger remains paginated for interactive browsing.

## Replace paths

Copy these files to the same locations in the existing project:

```text
backend/app/services/pdf_report.py
backend/app/services/sales_calculations.py
backend/app/api/routes/analytics.py
backend/tests/test_pdf_exports.py
frontend/src/pages/Dashboard.jsx
```

No duplicate `*_new.py` / `*_backup.jsx` source files should be created in `src/`.

## Download behaviour

The existing `Export PDF` control remains a single visible button; its label is upgraded to `Download Financial Report`. One click requests both PDFs with the exact same `buildQueryBody(query)` payload.

Browser multiple-download policies can still require the user to allow multiple downloads for the localhost origin. No second permanent export button is introduced.
