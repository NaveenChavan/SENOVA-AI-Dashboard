# Review findings — Phase 1

This review found that the initial delivered patch was not enough to claim Phase 1 complete without further fixes. The supplied archive was an overlay of 16 files, not a full repo. The replacement archive includes those file paths plus focused changes/tests needed to address the findings below.

## Concrete issues repaired

1. **Accepted Path A was not end-to-end safe for long histories.** Revenue forecasting eventually attempted to group by `Item` and `Quantity`, which are optional in `Date + Line Total` uploads. The forecast now returns revenue predictions without item-demand forecasts when item/quantity inputs are absent/incomplete; a 30-day Path A API test exercises forecasting and PDF export.
2. **P&L availability was too quiet.** Cost of Goods Sold and Gross Profit lines were omitted entirely if inputs were missing. Those lines now remain present with a null amount (rendered as `—`) and explicit `Not available: needs ...` reasons; report consistency checks skip null amounts.
3. **PII-shaped dates could bypass masking.** Because date-shape classification ran before header-based PII detection, a column like `Customer DOB` could be classed as date-like and retain values. PII now takes precedence and normalized values are redacted.
4. **Arbitrary extra numeric fields could mislead users.** Blank/unparseable cells were being turned into zero for every extra measure, distorting sums/averages. They are now preserved as missing, and chart/heatmap requests for incomplete extra measures return a clear 422-style `QueryError` rather than a partial or fabricated result.
5. **Phase 1 tests were out of sync with the new contract.** Tests that expected blank Category/Item to discard a valid row were updated because these fields are now explicitly optional. An existing PDF test module also lacked `import pandas as pd`, preventing full backend test collection.

## Verification performed in this review environment

- `python -m compileall -q app tests`: passed.
- Phase 1 + affected validation/schema/PDF suite: **87 passed**.
- Broad backend suite except `tests/test_auth_routes.py`: **506 passed, 1 skipped**.
- Full backend suite including auth/email integration was not fully verified because this container lacks the real Firebase Admin SDK and SendGrid package. Failures in those tests were dependency-environment related, not Phase 1 test failures.
- Modified frontend files: TypeScript transpile-based syntax check **12/12 passed**. Vitest/production build was not run because `frontend/node_modules` is absent in this environment.
- Screen recording: the Gemini timeout message appears while deterministic insight cards/dashboard remain; original deterministic narrative fallback keeps the dashboard useful. This replacement does not change the gated Gemini phase.

## Recommendation

Use this ZIP as a candidate Phase 1 replacement overlay. Apply it on a backed-up branch, inspect the diff, run tests with project dependencies, manually test Path A/Path B, and only then approve Phase 1. Do not start Phase 2 until explicitly approved.
