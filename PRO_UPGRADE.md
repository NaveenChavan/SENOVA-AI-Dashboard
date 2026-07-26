# SENOVA Pro Upgrade — Implementation Reference

Everything that was built in the Pro upgrade, in one place: what each feature
does, the maths behind it, which file owns it, the API surface, the security
rules, and how it was verified.

- **Date:** 26 July 2026
- **Scope:** Features 1 (insights), 2 (forecasting), 3 (inventory/reorder),
  5 (filters + drill-down), an 8-view chart engine, expanded column-keyword
  mapping, and two security fixes.
- **New runtime dependencies:** none. Only dev/test tooling was added.

---

## 1. Contents

1. [At a glance](#2-at-a-glance)
2. [Feature 1 — AI insight cards](#3-feature-1--ai-insight-cards)
3. [Feature 2 — Forecasting](#4-feature-2--forecasting)
4. [Feature 3 — Inventory & reorder intelligence](#5-feature-3--inventory--reorder-intelligence)
5. [Feature 5 — Filters & drill-down](#6-feature-5--filters--drill-down)
6. [Chart engine — 8 views, one payload](#7-chart-engine--8-views-one-payload)
7. [Column mapping & keyword coverage](#8-column-mapping--keyword-coverage)
8. [Security](#9-security)
9. [API reference](#10-api-reference)
10. [File map](#11-file-map)
11. [Design system applied](#12-design-system-applied)
12. [Tuning constants](#13-tuning-constants)
13. [Verification](#14-verification)
14. [Known limitations](#15-known-limitations)
15. [Suggested next steps](#16-suggested-next-steps)

---

## 2. At a glance

| Area | Before | After |
|------|--------|-------|
| Charts | 3 fixed (bar, donut, line) | 8 selectable views, any measure × any dimension |
| Insights | none | 6 statistical checks written as plain-language cards |
| Forecast | none | 7/14/30-day projection + 80% band + backtested accuracy |
| Inventory | dead-stock list only | velocity, ABC, ageing, reorder priority (+ real cover when stock is mapped) |
| Filters | 5 date presets | presets + custom range + multi-select on every available dimension |
| Drill-down | none | click any bar/slice/tile/row → the transactions behind it |
| Mapped columns | 6 required | 6 required + 12 optional (4 measures, 8 dimensions) |
| Ownership check | **missing (IDOR)** | enforced on every read, 404 on mismatch |
| Tests | none | 132 backend + 27 frontend |

Everything is computed in-house with Pandas/NumPy. No language model, no
third-party analytics service — sales data never leaves the backend, and no
number shown in the app is generated rather than calculated.

---

## 3. Feature 1 — AI insight cards

**Owner:** `backend/app/services/insights_engine.py` → `frontend/src/components/dashboard/InsightCards.jsx`
**Endpoint:** `POST /analytics/{file_id}/insights`

A row of findings above the charts, each with a headline, a sentence of
explanation containing real numbers, and a suggested action. Severity is
`critical` / `warning` / `positive` / `neutral`, shown as an icon **and** a
word (Urgent / Watch / Good news / Note) so meaning survives greyscale
printing and colour-blindness.

### The six checks

| Check | Method | Skipped when |
|-------|--------|--------------|
| Revenue anomaly | Robust z-score on the zero-filled daily series: `z = 0.6745 × (x − median) / MAD`. Falls back to std-dev if MAD = 0. Flags \|z\| ≥ 2 (warning) / ≥ 3 (critical) | fewer than 7 days |
| Movers | Biggest gainer and decliner vs the previous period, ranked by **rupee** change | no previous period, or item absent from one side |
| Margin leak | Top-quartile-revenue items whose margin is negative, or ≥10 points below their category median (shop-wide median as fallback) | category too small **and** no shop-wide median |
| Concentration | Cumulative revenue share — how few items make 80% | fewer than 8 items, or share > 20% (not risky) |
| Weekday timing | Mean revenue per weekday, best vs worst | any weekday seen < 2 times, or gap < 1.3× |
| Dead stock | Items with no sale for 30+ days | none idle |

### Why MAD instead of standard deviation

A single freak day inflates the standard deviation enough to hide *itself* —
the outlier raises the very threshold meant to catch it. The median absolute
deviation doesn't move, so the bad day still scores as an outlier.

### Why templates and not an LLM

Every sentence is an f-string filled with numbers this module computed. A card
therefore cannot hallucinate a figure, costs nothing per request, works
offline, and keeps the shop's data on the server. Each card also carries a
machine-readable `metrics` object so the UI formats the numbers itself
(₹1,84,000 — Indian grouping, with L/Cr above a lakh).

### Honesty rule

Checks the data can't support are **omitted and reported as skipped** in the
response `note`, rather than computed on noise. If nothing qualifies at all,
the panel says so and tells the user what would fix it.

---

## 4. Feature 2 — Forecasting

**Owner:** `backend/app/services/forecasting.py` → `ForecastSummary.jsx` + `TrendChart.jsx`
**Endpoint:** `POST /analytics/{file_id}/forecast` (body carries `horizon`)

### The model, step by step

1. Build the **zero-filled** daily revenue series — a closed day is a real 0,
   not a missing value.
2. Fit a trend by **weighted least squares**, weights decaying exponentially
   with a 14-day half-life, so last week matters more than last quarter.
3. Compute **weekday seasonal indices**: median of `actual ÷ trend` per
   weekday, normalised to average 1.0, clamped to [0.3, 3.0] so one festival
   Saturday can't triple every future Saturday.
4. Forecast `ŷ(t) = trend(t) × index(weekday(t))`, floored at 0 — revenue
   cannot be negative.
5. Confidence band from the in-sample residual spread:
   `ŷ ± 1.28 σ √(1 + h/n)` (80% interval, widening with horizon).
6. **Backtest:** hold out the last 7 days, refit on the rest, report
   `100 − MAPE` so the user can judge how much to trust the line. Days with
   zero actual revenue are excluded from MAPE (division by zero).

### Why NumPy only

Prophet needs a C++ toolchain and statsmodels is a heavy install — both make
deployment on a small Python host fragile. For daily shop revenue, trend +
weekday seasonality captures nearly all of the signal and every step stays
inspectable.

### Refusal rules

| History | Behaviour |
|---------|-----------|
| < 14 days | `available: false` with a plain-language reason. No line is drawn. |
| 14–20 days | Trend only; seasonality disabled and stated in `reason`. |
| ≥ 21 days | Full model. |
| ≥ 21 days | Accuracy backtest also reported. |

A confident-looking forecast built on four days of data would be worse than no
forecast, so this path is deliberate rather than an error state.

### Per-item demand

Top 20 items only (bounded compute): `velocity × trend factor × horizon`. The
inventory table joins these in as a "Next period" column, turning "what sells
fast" into "how many to buy".

---

## 5. Feature 3 — Inventory & reorder intelligence

**Owner:** `backend/app/services/inventory_intel.py` → `InventoryPanel.jsx`
**Endpoint:** `POST /analytics/{file_id}/inventory`

### Two modes, never blurred

| Mode | Trigger | What you get |
|------|---------|--------------|
| **Demand** (default) | file is a pure sales register | velocity, trend, ABC, ageing, reorder priority |
| **Stock-aware** | a stock column is mapped (`Stock`, `Closing Stock`, `Balance Qty`, `On Hand`) | the above **plus** real days-of-cover, reorder alerts, capital locked |

In demand mode `days_of_cover` and `capital_locked` come back as `null` and the
panel explains how to unlock them. A guessed days-of-cover would be worse than
none — it would drive a purchase decision from a number nobody measured.

### Per-item metrics

| Metric | Formula / meaning |
|--------|-------------------|
| `velocity_per_day` | units ÷ every calendar day in the window (planning rate) |
| `velocity_active` | units ÷ days it actually sold on — separates a steady seller from one bulk order |
| `trend_factor` | last-third velocity ÷ first-third velocity, clamped [0.25, 4.0]; the middle third is ignored to reduce twitchiness |
| `abc_class` | cumulative revenue share: ≤80% = A, ≤95% = B, rest = C |
| `ageing_bucket` | Fresh <15d, Slow 15–29d, Stale 30–59d, Dead 60+d idle |
| `reorder_priority` | `100 × (0.5·velocity_norm + 0.3·trend_norm + 0.2·recency)` — velocity scaled against the fastest mover, so it answers "what do I buy first?" |
| `days_of_cover` | stock ÷ velocity (stock-aware only); `null` when velocity is 0, because "infinite cover" isn't a plottable number |
| `capital_locked` | stock × average cost price (stock-aware only) |

Response is capped at 200 rows (`MAX_ITEMS_RETURNED`), highest priority first;
the UI shows the top 12 with a "show all" toggle and five sort options.

---

## 6. Feature 5 — Filters & drill-down

**Owner:** `backend/app/services/query_engine.py` → `FilterPanel.jsx` + `DrillDownPanel.jsx`

### One slice, every widget

`query_engine.build_slice()` is the single place a request becomes rows:

```
apply_filters()  →  resolve_window()  →  slice_window()  →  (current, previous, window)
```

Every Pro endpoint calls it, so the KPI cards, charts, insight cards, inventory
table, P&L, ledger and the exported PDF are mathematically incapable of
describing different data.

### Window resolution

- Presets are anchored to the **newest date in the file**, never the server
  clock — a CSV uploaded months later still gives a sensible "Last 7 Days".
- The comparison period is always the same length, immediately before the
  selected one, so "vs previous period" means the same thing for a preset and
  for a hand-picked range.
- `all` has no previous period by definition — the whole file *is* the period.

### Filters

`{dimension_key: [values]}`, applied with `Series.isin` after the key is
checked against the dimensions the uploaded file actually contains. An unknown
key returns **422** rather than being ignored — a silently dropped filter would
show numbers that contradict the chips on screen. An empty value list means "no
restriction", not "show nothing".

### Drill-down

Clicking a bar, slice, tile or table row opens a slide-over with the
transactions behind it, paginated 25 at a time.

- Category / item / branch-style groups become an extra filter.
- A clicked **day** or **month** becomes a custom date range instead, because
  time dimensions are (deliberately) rejected as filters.
- A clicked **weekday** doesn't drill: it isn't a contiguous range, so there is
  nothing honest to show.

Dialog contract: focus moves in on open, Escape closes, backdrop is
click-to-close.

### Deep links

Tab, date window, custom range and filters are mirrored into the URL
(`?fileId=…&tab=overview&range=custom&from=…&to=…&filters=…`), so a filtered
view survives a refresh and can be shared with an accountant. A hand-edited or
truncated `filters` param is caught and ignored rather than breaking the page.

---

## 7. Chart engine — 8 views, one payload

**Owner:** `frontend/src/components/charts/` → `POST /analytics/{file_id}/chart-data`

`aggregate()` returns every measure per group, so switching view or chart type
**never triggers a new request**.

| View | Question it answers |
|------|--------------------|
| Bars | How do groups compare? |
| Ranking (horizontal) | Same, when names are long |
| Donut | What is the whole made of? (top 6, rest folded into "Other") |
| Combo | Where is revenue high but margin thin? (bars + margin-% line) |
| Pareto | How concentrated is the business? (bars + cumulative curve) |
| Bubble | How do price and volume relate? (size = revenue) |
| Treemap | Which groups dominate, at a glance? |
| Heatmap | Which weekdays actually sell? (weekday × week) |

- **Measures:** revenue, profit, cost, units, transactions, margin %, average
  price, discount.
- **Dimensions:** category, item, day, weekday, month + every optional
  dimension the file provided.
- **Top-N folding:** groups past the limit collapse into one muted "Other"
  bucket, so totals stay honest while the chart stays readable. Time
  dimensions are never folded and stay in chronological order (weekdays Mon→Sun).
- **Ratios:** margin % and average price can't be summed, so `share_pct` and
  `cumulative_pct` come back `null` for them instead of a meaningless number.
- **Table toggle** on every view. Scatter, treemap and heatmap are rated poor
  for screen readers; the guidance for all three is a table alternative, and
  table rows are clickable exactly like bars.
- **Preferences** (type, measure, dimension, table mode) persist in
  `localStorage`, tolerant of a blocked or corrupt store.

The heatmap is a CSS-grid `<table>` rather than a chart library component
(Recharts has none) — no extra dependency, and every cell is a real cell with a
text label.

---

## 8. Column mapping & keyword coverage

**Owner:** `backend/app/utils/data_validator.py` → `ColumnMappingScreen.jsx`

### Field groups

| Group | Fields |
|-------|--------|
| Required (6) | Date, Category, Item, Quantity, Selling Price, Cost Price |
| Optional measures (4) | Line Total, Discount, Tax, Stock On Hand |
| Optional dimensions (8) | Branch, Payment Mode, Customer, Salesperson, Brand, Size, Colour, Invoice No |

The mapping screen builds its dropdowns from the server's field lists (grouped
into "Required / extra amounts / extra breakdowns") with a one-line helper text
per field, so adding a supported field on the backend surfaces automatically.

### Header coverage

Real headers from Tally (`Voucher Date`, `Particulars`, `Stock Group`),
Vyapar / Marg / Busy (`Bill Date`, `Item Name`, `Rate/Unit`, `Taxable Value`,
`Purchase Rate`, `Balance Qty`), GST invoice registers, and Shopify / Amazon /
Flipkart dumps (`Lineitem quantity`, `quantity-purchased`, `Ordered On`).

### The `Amount` correctness fix

An `Amount` / `Net Amount` / `Taxable Value` column holds a **line total**, not
a unit price. Mapping it to Selling Price makes revenue come out as
`Quantity × line total` — inflated by the quantity factor on *every row*.

So those aliases map to `Line Total`, and when no unit price column exists the
unit price is derived:

```
Selling Price = Line Total ÷ Quantity      (only where Quantity > 0)
```

Selling Price therefore stops being a required mapping once Line Total is
mapped, and the screen says what it will do.

### Other validation behaviour

- Two raw columns that look like the same field: only the first keeps the
  suggestion, the second is downgraded to "no guess" so the user picks
  explicitly (and a duplicate rename can never turn a Series into a DataFrame).
- Currency and grouping symbols are stripped on retry — `₹ 1,299.00` is a
  normal value in these exports.
- Dates are parsed twice: `dayfirst=True` for DD-MM-YYYY, then ISO for the rows
  the first pass rejected.
- Blank optional dimension → `Unspecified`, so no row silently disappears from
  a branch breakdown.
- Revenue is reported **net of discount**; GST/Tax is tracked separately and
  sits below the profit line as a memo, because tax collected is not income.
- Selling below cost is **not** flagged — clearance sales are legitimate, and
  removing those rows would delete exactly what the margin-leak check needs.
- Unmapped extras (`Remarks`, `HSN`, …) are dropped after mapping, so nothing
  unexpected reaches the cache, the JSON, or the PDF.

---

## 9. Security

### Two gaps found in the existing code and fixed

1. **IDOR — no ownership check.** Any authenticated user holding another user's
   `file_id` could read their whole sales ledger and download their P&L. The
   uploader's identity is now written to a `{file_id}.meta.json` sidecar and
   re-checked on every read; a mismatch returns **404, not 403**, so the API
   never confirms that someone else's file exists.
2. **NaN / Infinity in JSON.** Several ratios can produce `NaN` (margin on zero
   revenue). Pydantic serialises that as bare `NaN`, which is invalid JSON and
   makes `JSON.parse` throw in the browser. Every number now leaves through
   `safe_float` / `safe_int` / `safe_div` / `safe_percentage`.

### Applied to all new code

| Control | Detail |
|---------|--------|
| Auth | Verified Firebase ID token on every route (signature, expiry, revocation) |
| Authorisation | Ownership re-checked on every read; 404 on mismatch |
| Path safety | `file_id` matched against `^[0-9a-f]{32}$` before any filesystem access; only the *extension* of a client filename is ever used to build a path |
| No dynamic queries | Dimensions and measures are Pydantic `Literal` enums; filters use `Series.isin`. Nothing user-supplied reaches `DataFrame.query`, `eval` or a string-built expression |
| Bounded inputs | ≤8 filter keys, ≤50 values each (≤200 chars), `top_n` ≤ 50, `page_size` ≤ 1000, `horizon` ≤ 90, ≤100 columns per upload, size capped by `MAX_UPLOAD_SIZE_MB` |
| Bounded compute | LRU cache of 8 normalised frames (≤300k rows each), keyed on file mtime + mapping — repeated filter changes don't re-parse a 50k-row Excel file, and an unbounded cache can't become a memory DoS |
| Bounded output | Inventory ≤200 rows, item forecasts ≤20, dimension values ≤200 per dimension, PDF ledger ≤500 rows |
| Error hygiene | Client sees generic messages; no stack traces or filesystem paths cross the API boundary |
| Frontend | All text rendered as React children (auto-escaped); no `dangerouslySetInnerHTML` anywhere |
| Supply chain | Zero new runtime dependencies on either side |
| Retention | TTL sweep removes the file and both sidecars after `UPLOAD_TTL_MINUTES` |

---

## 10. API reference

All routes require a verified Firebase ID token and file ownership.

### Upload — two steps, because every export differs

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload/` | Save the file (bound to the caller), return the guessed mapping, the optional fields available, helper text, and sample rows |
| `POST` | `/upload/{file_id}/confirm-mapping` | Apply the confirmed mapping, validate every row, report the real date span and which optional fields were unlocked |

### Pro analytics — `POST`, shared `AnalysisQuery` body

```json
{
  "time_filter": "all | today | week | 30days | month | custom",
  "start_date": "2026-02-01",
  "end_date": "2026-02-28",
  "filters": { "branch": ["MG Road"], "payment_mode": ["UPI"] }
}
```

| Path | Extra body fields | Returns |
|------|-------------------|---------|
| `/analytics/{id}/summary` | — | KPIs with trend arrows, top items, category split, daily trend, dead stock |
| `/analytics/{id}/chart-data` | `dimension`, `measure`, `top_n` | Chart points with every measure precomputed, plus the Pareto group count |
| `/analytics/{id}/heatmap` | `measure` | Weekday × week grid with a numeric legend range |
| `/analytics/{id}/insights` | — | Findings + the dates flagged as anomalies |
| `/analytics/{id}/inventory` | — | Velocity, ABC, ageing, reorder priority (+ cover/capital when stock is mapped) |
| `/analytics/{id}/forecast` | `horizon` | Projection with confidence band and backtested accuracy |
| `/analytics/{id}/report` | — | CA-style P&L + category ledger |
| `/analytics/{id}/ledger` | `page`, `page_size` | Paginated transaction register — also powers drill-down |
| `/analytics/{id}/report.pdf` | — | Full PDF: findings, P&L, category ledger, forecast, reorder list, register |

`GET /analytics/{id}/dimensions` — which dimensions this file supports, their
distinct values, the optional measures present, and the file's date range. The
filter panel and chart dropdowns are built from this, which is why an unmapped
column can never become a filter.

### Classic routes — unchanged for existing consumers

`GET /process/{id}`, `GET /analytics/{id}?time_filter=`,
`/analytics/{id}/report`, `/analytics/{id}/ledger`,
`/analytics/{id}/report.pdf`, `GET /health`.

### Status codes worth knowing

| Code | Meaning |
|------|---------|
| 404 | Unknown, malformed, or someone else's `file_id` — indistinguishable on purpose |
| 409 | Column mapping not confirmed yet → send the user back to the mapping screen |
| 422 | Unknown dimension/measure/filter key, oversized filter payload, or an incomplete custom range |
| 413 | Upload larger than `MAX_UPLOAD_SIZE_MB` |

---

## 11. File map

### Backend — new

| File | Responsibility |
|------|----------------|
| `app/utils/safe_json.py` | `safe_float` / `safe_int` / `safe_div` / `safe_percentage` — nothing unserialisable leaves the API |
| `app/services/frame_cache.py` | Bounded LRU of normalised frames, keyed on mtime + mapping |
| `app/services/query_engine.py` | Dimension/measure registries, window resolution, filtering, generic aggregation, heatmap, filter-panel metadata |
| `app/services/insights_engine.py` | Feature 1 — the six checks and their prose |
| `app/services/inventory_intel.py` | Feature 3 — velocity, ABC, ageing, reorder priority, stock-aware cover |
| `app/services/forecasting.py` | Feature 2 — trend, seasonality, band, backtest, item demand |

### Backend — changed

| File | Change |
|------|--------|
| `app/services/file_handler.py` | `validate_file_id`, owner sidecar + `assert_owner`, `get_file_mtime`, cleanup of both sidecars |
| `app/utils/data_validator.py` | Required + optional field groups, much wider alias map, `Line Total` fix and unit-price derivation, duplicate-suggestion handling, dimension/measure introspection |
| `app/services/sales_calculations.py` | Net-of-discount revenue + tax column, `compute_summary_between`, `compute_daily_trend_between`, discount/GST lines in the P&L, previous-period trend bug fixed |
| `app/api/routes/analytics.py` | Ownership + mapping guards, classic GETs kept, 10 Pro routes added, PDF assembly shared |
| `app/api/routes/upload.py` | Owner recorded on upload, cache invalidated on re-mapping, optional fields + helper text returned, column-count cap |
| `app/models/schemas.py` | `AnalysisQuery` / `ChartQuery` / `LedgerQuery` / `ForecastQuery` + every Pro response model, with validators for the input caps |
| `app/services/pdf_report.py` | Findings, forecast and reorder sections added; severity printed as a word so a photocopy still reads |

### Frontend — new

| File | Responsibility |
|------|----------------|
| `components/charts/chartFormat.js` | Indian currency/number/percent formatting, axis tick factories, label truncation |
| `components/charts/ChartTooltip.jsx` | Studio / trend / simple tooltips + legend (dash pattern for the forecast series) |
| `components/charts/ChartDataTable.jsx` | The accessible table alternative, clickable like a bar |
| `components/charts/StudioCharts.jsx` | Bars, ranking, donut, combo, Pareto, bubble, treemap |
| `components/charts/HeatmapGrid.jsx` | CSS-grid heatmap with a numeric legend |
| `components/charts/TrendChart.jsx` | Actual line + dashed forecast + 80% band + anomaly rings |
| `components/charts/ChartStudio.jsx` | The shell: type/measure/dimension/table controls, preference persistence |
| `components/common/Icon.jsx` | 13 inline SVG paths — no emoji as icons |
| `components/dashboard/InsightCards.jsx` | Feature 1 UI |
| `components/dashboard/InventoryPanel.jsx` | Feature 3 UI (ABC tiles, ageing, reorder table) |
| `components/dashboard/ForecastSummary.jsx` | Feature 2 UI (range, trend, accuracy, horizon toggle) |
| `components/dashboard/FilterPanel.jsx` | Feature 5 UI (chips, custom range, per-dimension groups) |
| `components/dashboard/DrillDownPanel.jsx` | Feature 5 UI (slide-over dialog, paginated) |

### Frontend — changed

| File | Change |
|------|--------|
| `store/useSalesStore.js` | Query state, `buildQueryBody`, per-endpoint abort controllers, all Pro fetchers, `openDrillDown` |
| `pages/Dashboard.jsx` | Three tabs, URL state sync, filter panel wiring, SVG empty states, POST PDF export |
| `components/upload/ColumnMappingScreen.jsx` | Grouped optional fields, helper text, Line-Total-aware requirement |
| `components/charts/useChartTheme.js` | Semantic roles (actual/forecast/anomaly) + 8-colour categorical ramp |
| `components/charts/BarChart.jsx` | Uses the shared tooltip and formatters instead of its own |
| `index.css` | `:focus-visible` rings, `prefers-reduced-motion`, skip-link |
| `vite.config.js`, `package.json` | Vitest config and `npm test` |

**Deleted:** `components/charts/CategoryPieChart.jsx`, `components/charts/LineChart.jsx`
(superseded by the studio and `TrendChart`; no imports remained).

---

## 12. Design system applied

Installed with `uipro init --ai kiro --force` →
`.kiro/steering/ui-ux-pro-max/`. Resolved for this project as a
**Data-Dense Dashboard** (navy `#1E40AF` + amber `#F59E0B` accents).

What it actually changed:

- SVG icons only; the emoji empty state was replaced.
- Visible `:focus-visible` rings app-wide; `prefers-reduced-motion` honoured;
  chart animations switched off so filter changes are instant (and so anomaly
  markers aren't delayed behind a sweep).
- Severity, trend and ABC class conveyed by text/icon **and** colour, never
  colour alone.
- Donut capped at 6 slices; treemap tiles get white 2–3px borders; bubbles at
  0.7 opacity so overlaps show density; heatmap ships a numeric legend.
- Table alternative for scatter / treemap / heatmap.
- Every table wrapped in `overflow-x-auto`; every empty state offers the action
  that fixes it; skeletons reserve real layout height so nothing jumps.
- Deep-linkable view state; keyboard-navigable tabs; drill-down dialog with
  focus management and Escape-to-close.
- 44px minimum touch targets on controls; responsive at 375 / 768 / 1024 / 1440.

---

## 13. Tuning constants

All thresholds are named module-level constants — change them in one place.

### `insights_engine.py`

| Constant | Value | Meaning |
|----------|-------|---------|
| `ANOMALY_Z_CRITICAL` / `ANOMALY_Z_WARNING` | 3.0 / 2.0 | Outlier severity cut-offs |
| `MIN_DAYS_FOR_ANOMALY` | 7 | Below this, no "normal level" exists |
| `MAX_ANOMALY_CARDS` | 2 | Worst days only |
| `MARGIN_LEAK_MIN_REVENUE_SHARE` | 0.03 | Item must matter to the top line |
| `MARGIN_LEAK_GAP_POINTS` | 10.0 | Margin points below the benchmark |
| `CONCENTRATION_ITEM_SHARE` | 0.20 | Flag when ≤20% of items make 80% |
| `MIN_OBS_PER_WEEKDAY` / `MIN_WEEKDAY_RATIO` | 2 / 1.3 | Weekday check guards |
| `DEAD_STOCK_DAYS` | 30 | Idle threshold |

### `forecasting.py`

| Constant | Value |
|----------|-------|
| `MIN_DAYS_FOR_FORECAST` | 14 |
| `MIN_DAYS_FOR_SEASONALITY` | 21 |
| `WEIGHT_HALF_LIFE_DAYS` | 14.0 |
| `SEASONAL_INDEX_CLAMP` | (0.3, 3.0) |
| `Z_80_PERCENT` | 1.2816 |
| `BACKTEST_DAYS` | 7 |
| `MAX_ITEM_FORECASTS` | 20 |

### `inventory_intel.py`

| Constant | Value |
|----------|-------|
| `ABC_A_THRESHOLD` / `ABC_B_THRESHOLD` | 0.80 / 0.95 |
| `AGEING_FRESH_DAYS` / `SLOW` / `STALE` | 15 / 30 / 60 |
| `WEIGHT_VELOCITY` / `TREND` / `RECENCY` | 0.50 / 0.30 / 0.20 |
| `TREND_CLAMP` | (0.25, 4.0) |
| `REORDER_COVER_DAYS` | 7 |
| `MAX_ITEMS_RETURNED` | 200 |

### `query_engine.py` / `frame_cache.py` / `schemas.py`

| Constant | Value |
|----------|-------|
| `MAX_DIMENSION_VALUES` | 200 |
| `MAX_ENTRIES` / `MAX_CACHED_ROWS` | 8 / 300 000 |
| `MAX_FILTER_KEYS` / `VALUES` / `VALUE_LENGTH` | 8 / 50 / 200 |

---

## 14. Verification

### Commands

```bash
# Backend — 132 tests
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest

# Frontend — 27 tests + production build
cd frontend
npm install
npm test
npm run build
```

### Results

| Suite | Command | Result |
|-------|---------|--------|
| Backend | `py -3 -m pytest` | **132 passed** |
| Frontend | `npm test` | **27 passed** (2 files) |
| Build | `npm run build` | **succeeds** |

### Backend test files

| File | Tests | Covers |
|------|-------|--------|
| `tests/conftest.py` | — | 90-day synthetic shop: seeded weekend uplift, one deliberately crushed day, one item priced ₹20 above cost, one item that stops selling after two weeks, plus Branch / Payment Mode / Discount / Stock columns |
| `test_data_validator.py` | 41 | Real-world header aliases, `Amount` → `Line Total` + derived unit price, keyword-order traps (`Total Qty`, `Discount` vs `count`), duplicate downgrade, currency/date parsing, business rules, soft-fail, unknown mapping targets rejected |
| `test_query_engine.py` | 17 | Window anchoring and equal-length previous period, custom ranges, filter application and rejection, aggregate totals reconciling with raw data, top-N folding preserving totals, time-dimension ordering, ratio measures having no share, Pareto count, heatmap consistency, dimension exposure |
| `test_insights_engine.py` | 15 | The seeded bad day is found with the right sign and z-score, the margin leak and dead-stock items are named, the weekend pattern is detected, cards are complete and severity-sorted with no unresolved placeholders, short history skips the anomaly check, movers require a previous period, Indian number formatting |
| `test_inventory_and_forecast.py` | 14 | Velocity reconciles with units ÷ window, ABC partitions the catalogue, ageing flags the idle item, priority ranks movers above idle stock, stock-aware cover/capital are real, demand mode never guesses, forecast refuses short history, horizon length and band ordering, totals matching the plotted days, seasonality + accuracy present, horizon cap |
| `test_api.py` | 45 | Full upload → confirm → analyse flow; **IDOR blocked on 6 routes with an indistinguishable 404**; malformed/traversal ids rejected; 409 before mapping; 422 for unknown dimensions, oversized filters, `top_n`/`page_size`/`horizon` out of range, and incomplete custom ranges; filters actually reduce revenue; trend arrows have a previous period; every dimension and every measure renders; heatmap/insights/inventory/forecast/ledger/report; discount lines in the P&L; the PDF really starts with `%PDF`; classic GETs still work; empty filter result returns a zeroed payload; **no `NaN` or `Infinity` in any response body** |

### Frontend test files

| File | Tests | Covers |
|------|-------|--------|
| `src/__tests__/charts.test.jsx` | 16 | All 8 studio views render against a real API-shaped payload, controls present, concentration fact in words, heatmap rows + numeric legend, empty state, table alternative with Indian formatting and click-to-drill, trend chart with and without a forecast, anomaly ring labelled, empty period |
| `src/__tests__/panels.test.jsx` | 11 | Insight cards (severity as words, Indian formatting, empty note), inventory in both modes (cover/capital present vs absent with explanation), forecast (range + accuracy vs refusal with no invented number), filter chips and opened panel, drill-down dialog and its null case |

`ResponsiveContainer` is stubbed with fixed dimensions in the chart tests —
jsdom reports every element as 0×0, so without it the chart internals would
never execute and the tests would pass vacuously. That stub is what caught a
real Recharts treemap prop bug during development.

### Independent audit

A separate reviewer agent re-checked the code (not the docstrings) against
every claim above and ran both suites. All five claim areas verified; the only
findings were cosmetic — a duplicated tooltip in the legacy bar chart and an
orphaned `__pycache__` entry from a previously deleted module. Both were fixed
and all three commands re-run green.

---

## 15. Known limitations

| Limitation | Why / what would fix it |
|------------|-------------------------|
| Days-of-cover and locked capital need a stock column | A sales register says what left the shop, not what's on the shelf. Map `Stock` / `Closing Stock` / `Balance Qty` / `On Hand`. |
| Forecast needs 14+ days, seasonality 21+ | Refusing is deliberate; upload a longer export or use All Time. |
| Weekday groups can't be drilled into | A weekday isn't a contiguous date range and isn't a filterable column. |
| Uploads expire after `UPLOAD_TTL_MINUTES` (default 120) | Storage is temporary by design. Persistent history would need object storage or a database. |
| Cached frames are per-process | Multiple backend workers each keep their own small cache; correctness is unaffected (mtime + mapping key), only warm-up. |
| Dimension values capped at 200 per dimension | A file can have thousands of invoice numbers; the response flags `truncated: true`. |
| Filter chips have no "select all" | Multi-select only; an empty selection already means "no restriction". |
| No scheduled/emailed reports | Would need SMTP configuration and a scheduler. |

---

## 16. Suggested next steps

Not built — from the original options list, in the order I'd tackle them:

1. **What-if margin simulator** — price/cost/discount sliders that recompute
   revenue, profit and margin instantly. Highest visible value, and the
   aggregation layer already exposes every number it needs.
2. **Comparison mode** — this period vs previous (or two uploaded files) side
   by side with delta columns. Needs upload history to be worth it.
3. **"Ask SENOVA" query bar** — a deterministic intent parser mapping plain
   questions onto the existing query layer ("top 5 items last month"). No API
   key, no cost, but the most UX design work.
4. **Upload history / persistence** — replace the TTL sweep with object storage
   plus a per-user file list; a prerequisite for (2).
5. **Basket analysis** — items bought together, only meaningful when
   `Invoice No` is mapped; note the pairwise cost needs bounding.
