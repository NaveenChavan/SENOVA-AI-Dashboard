# SENOVA C2 — Filters & UI package

This folder contains the complete **C2 Filters & UI scope** for the supplied SENOVA code bundle, merged on top of the working C1 column-routing fix dependencies that were available in the uploaded source.

## What is included

- Compact filter bar + fixed/portalled filter drawer.
- Group-count badge (Category / Item / Payment Mode / Date range, not individual values).
- Searchable Item and Invoice No selectors with tall scroll areas, `N of M selected`, Select all and Clear.
- Server-side searchable/cascade-aware dimension options to avoid the legacy 200-value UI limitation.
- Category ↔ Item cascading and impossible-combination pruning.
- Friendly zero-result state: `No rows match these filters` with Clear.
- Latest-day semantics from the uploaded file's max date, not the computer clock.
- Quick date presets plus custom range validation and backend clamping to the actual data range.
- Loading-safe overview state and request sequence guards so stale responses cannot overwrite newer results.
- Sticky tabs/table offsets coordinated to prevent overlap.
- Mobile-safe drawer with no horizontal overflow.
- No intentional colour/font changes and no unrelated screen changes.
- Backend regression tests and frontend regression tests requested for C2.
- `validation/verify_fixture.py` independently checks the required fixture numbers without importing the incomplete backend bundle.
- `apply_c2.sh` backs up only the files in this package before copying them into a real project tree.

## Important scope note

The uploaded repository archive is **partial**. It does not contain the complete application source tree or the normal package/test configuration (`package.json`, pytest config, and several backend modules are absent). Therefore this package is complete for the **C2 files changed/supplied here**, but it is not a standalone replacement for the user's entire SENOVA repository.

## C2 design decisions

1. Analytics calculations remain on the same aggregation path; filter selection is staged in the drawer and only `Apply` commits a new query.
2. The time window is resolved against the full file before dimension filters are applied. This preserves the meaning of `Latest day` even when the selected category has no sale on the file's final date.
3. Item and Invoice No options are loaded through a dedicated POST endpoint so search works beyond the legacy static 200-value metadata cap.
4. Category and Item option queries exclude the dimension currently being edited, while keeping the other staged filters. This is what creates true bidirectional cascading.
5. Empty-state UI is driven by explicit `row_count`, not inferred from revenue being zero.
6. Request cancellation is paired with a latest-request/sequence guard because abort alone is not a complete stale-response guarantee.
7. The drawer is rendered through a portal so `position: fixed` is not trapped by sticky/transformed ancestors.

## Required fixture numbers

Using `testing2/03_electronics_shopify_orders.csv`:

- Latest day (17 Jun 2026): 7 transactions, revenue 49,180, cost 29,430, profit 19,750.
- Latest day + Category Power: 2 transactions, revenue 13,893.
- 2026-03-19 → 2026-04-17 + Category Power: 60 transactions, revenue 510,327, cost 301,950, profit 208,377, units 273.

Run `python validation/verify_fixture.py` from this folder to independently verify those numbers.

## Applying to the real project

From the real project root, run:

```bash
bash /path/to/senova-c2-complete/apply_c2.sh /path/to/your/senova-project
```

The script creates a timestamped backup of every existing target file before replacing it. It does not touch files outside the C2 manifest.

## Test execution honesty

Static syntax validation was performed on all supplied backend Python files, all supplied frontend JS/JSX files, and the supplied CSS. The independent fixture-number validation passes.

The C2 pytest file cannot be collected against this extracted bundle because the archive is missing backend modules such as `app.services.sales_calculations`. A full Vitest run likewise requires the real repository's frontend package/test setup, which is not present in this bundle. Do not treat this folder's static validation as a full-repository suite result.

C2 deployment/production start is not performed by this package.
