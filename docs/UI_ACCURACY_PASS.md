# UI/UX & Accuracy Pass

The second pass over SENOVA Pro: a rebuilt design system (compact, light-first,
token-driven), and an accuracy audit that re-derived every published number from
the raw file and fixed four real bugs.

`PRO_UPGRADE.md` documents *what the product does*. This document covers *how it
looks and whether the numbers are right*.

---

## 1. Contents

1. [Why this pass](#2-why-this-pass)
2. [The token layer](#3-the-token-layer-frontendsrcindexcss)
3. [Typography](#4-typography)
4. [Shared component classes](#5-shared-component-classes)
5. [Layout changes](#6-layout-changes)
6. [Density switch](#7-density-switch)
7. [Command palette](#8-command-palette-k--ctrl-k)
8. [Currency house rule](#9-currency-house-rule-enforced-by-a-test)
9. [Responsive behaviour](#10-responsive-behaviour)
10. [Accuracy audit — four bugs found and fixed](#11-accuracy-audit--four-bugs-found-and-fixed)
11. [Dead code removed](#12-dead-code-removed)
12. [Tests added](#13-tests-added)
13. [Verification](#14-verification)
14. [Still on the table](#15-still-on-the-table)

---

## 2. Why this pass

Three concrete complaints drove it, all visible on screen:

1. **"Ek box dekhne ke liye scroll karna padta hai."** The base font was a
   viewport-fluid `clamp(15px, 0.9vw + 12px, 19px)`, so on a desktop every card,
   control and chart grew together and a single panel outgrew the viewport.
2. **"Saare text kitne chote, dekhne ko mushkil."** Tailwind's `text-xs` resolved
   to 11.25px in dense panels, and several components used 9.5–10px labels.
3. **"Revenue box me poori value chahiye."** KPI tiles abbreviated to `₹7.2L`
   when the shop owner wants to read `₹7,20,126`.

And one thing the screenshot exposed that nobody had asked about: an insight card
reading *"0% above your normal daily level of ₹0"* — a real bug, which is what
started the accuracy audit.

The design direction comes from the installed
[ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) skill
(`.kiro/steering/ui-ux-pro-max/`), resolved for this project as a **Data-Dense
Dashboard** and rebuilt **light-first**.

---

## 3. The token layer (`frontend/src/index.css`)

No component hardcodes a size or a colour; everything reads a token, so density
and scale change in one file.

| Token | Value | Why |
|-------|-------|-----|
| `html font-size` | **15px**, stepping to 16 / 17 / 19px at 1920 / 2560 / 3840px | Fixed steps instead of a `vw` clamp — the clamp is what made whole panels overflow the screen on desktop |
| `--control-h` | **40px** on touch, **36px** on a fine pointer | One height for every button, select, chip and segment, so a toolbar row lines up exactly; touch keeps its 44px target with the row gap |
| `--card-pad` | 14 → 16 → 18 → 22px by breakpoint | One padding per surface size |
| `--gap` | 12 → 14 → 16 → 20px | One grid gap |
| `--chart-h` | 190 → 210 → 224 → 240 → 260 → 300px | "Make the charts smaller" is one edit; every chart uses `.chart-box` |
| `--chart-h-wide` | 170 → 180 → 200 → 215 → 230 → 260px | A full-width panel needs *less* height to stay readable |
| `--page-max` | 1360 → 1560 → 1840 → 2280px | A 4K/8K panel gets a wider canvas instead of one endless strip of tiny widgets |
| `--radius` / `--radius-lg` | 10 / 14px | Down from 16px; smaller radii read as denser |

Colour tokens were re-tuned for both themes: light is `#f5f7fb` canvas on
`#ffffff` cards with `#2563eb` primary; dark keeps the navy but drops the glow
effects, which read as blur on a dense grid.

---

## 4. Typography

- Base 15px, body text `0.9375rem`.
- Tailwind's smallest steps are overridden in `tailwind.config.js` so `text-xs`
  is a readable **13px** instead of 11.25px, `text-sm` 13.1px, `base` 14px —
  fixing every component at once rather than one class at a time.
- Micro-labels bottom out at **11px**; small text is **12px**; card body copy
  **12.5px**.
- KPI tiles show the **complete figure** with the font size stepping down as the
  number lengthens (`clamp` keyed on character count), so a nine-digit amount
  fits instead of clipping.
- Cards and insight text round to whole rupees; only the P&L, the register and
  the drill-down show paise, where they are the point.

---

## 5. Shared component classes

`.card` · `.card-pad` · `.panel-title` · `.panel-hint` · `.stat-tile` ·
`.chart-box` (+`--wide`) · `.btn` · `.btn-primary` · `.btn-icon` ·
`.seg` / `.seg__btn` · `.chip` · `.filter-select` · `.table` · `.scroll-x` ·
`.skeleton` · `.note[data-tone]` · `.toolbar-sticky` · `.palette*`.

The segmented control (`.seg`) is reused by the date presets, the view tabs, the
chart-type switcher and the forecast horizon — four controls that used to be four
near-misses now read as one component.

---

## 6. Layout changes

- App shell header is a fixed **52px** bar; footer is a 13px line.
- The dashboard toolbar block (title + date presets + export, filters, tabs) is
  **sticky** below the header, so the controls people reach for while scrolling
  stay reachable. It un-sticks below 640px — a short viewport can't spare rows.
- **Daily trend** and **top fast-moving items** share a row; the **chart studio**
  spans the full width beneath them at the shorter `--chart-h-wide`.
- Long lists (dead stock, category ledger, register, reorder table, filter chip
  groups, mapping table) scroll **inside** their own card with a sticky header,
  so page length is predictable and no card exceeds the viewport.
- Bars are capped at 56px (`BAR_MAX`) — a full-width panel with three groups was
  rendering three enormous blocks instead of a chart.
- Donut percentages moved **inside** the ring (names in the legend); the outside
  labels were being clipped by the card.
- The trend chart gained a **7-day trailing average** (purple, dashed): on a shop
  that trades some days the raw line is a comb of spikes, and the average is what
  shows whether the business is actually growing.
- Emoji status badges in the dead-stock table became SVG icons plus a word
  ("Critical" / "Warning" / "Recent").
- Chart animations are off everywhere: they delay the anomaly markers and add
  nothing on a panel that re-renders on every filter change.

---

## 7. Density switch

`data-density="comfortable"` on `<html>` swaps the spacing tokens (control
height, card padding, gap, chart heights, radii) for a roomier scale.

- CSS-only: nothing re-renders, and even the charts follow, because they read
  `--chart-h`.
- Persisted in `localStorage` and applied **before first paint** by the inline
  script in `index.html`, alongside the theme — no flash of the wrong spacing.
- Store: `frontend/src/store/useDensityStore.js`; control:
  `components/common/DensityToggle.jsx` (in the header, next to the theme
  toggle); also available from the palette.

---

## 8. Command palette (⌘K / Ctrl-K)

`components/common/CommandPalette.jsx` — every dashboard action in one keystroke:
the three tabs, five date presets, eight chart types, eight measures, the table
toggle, clear filters, PDF export and the density switch.

- **Subsequence matching**, not substring: `dnut` finds *Donut*.
- Arrow keys to move, Enter to run, Escape to close, click-outside to dismiss;
  focus lands in the input on open.
- The action list is built from the same constants the visible controls use, so a
  new chart type or measure appears in both places automatically — a keyboard
  user never has fewer options than a mouse user.
- It doubles as a discovery list for features a user hasn't found in the UI.

This is why the studio's view state now lives in
`components/charts/chartView.js` rather than inside the panel: the page owns it,
the panel is controlled by it, and there is no second copy to drift. `ChartStudio`
still falls back to its own internal state when rendered standalone.

---

## 9. Currency house rule (enforced by a test)

One formatter (`components/charts/chartFormat.js`), three uses:

| Surface | Helper | Example |
|---------|--------|---------|
| Tiles, cards, tables | `formatCurrency` (whole rupees) | `₹7,20,126` |
| Axes, legends, compact tiles | `formatCurrencyCompact` | `₹7.2L` |
| P&L, register, drill-down | `formatCurrencyExact` | `₹1,299.00` |

A test walks every source file and fails if any of them calls `toLocaleString`
directly. That duplication is exactly how `₹7,20,126` and `₹21,992.33` ended up
on the same screen.

---

## 10. Responsive behaviour

| Width | Layout |
|-------|--------|
| 375px | Single column, KPI tiles 2-up, toolbars wrap, segmented controls scroll horizontally, sticky toolbar disabled, drill-down is a full-screen sheet |
| 768px | KPI 3-up, insight cards 2-up, tables scroll sideways |
| 1024px | Trend + top-items side by side, insight cards 3-up |
| 1440px | Full grid at `--page-max` 1360px |
| 1920px+ | Canvas widens to 1560px, chart height and base font step up |
| 2560 / 3840px | Canvas 1840 / 2280px, insight cards 4-up, padding and gaps scale |

Accessibility baseline retained and extended: visible `:focus-visible` rings,
`prefers-reduced-motion`, a skip link, keyboard-navigable segmented controls,
table alternatives for scatter/treemap/heatmap, severity conveyed by icon **and**
word, and a numeric legend on the heatmap.

---

## 11. Accuracy audit — four bugs found and fixed

Every expected value in the audit suite is recomputed from the raw DataFrame with
plain Pandas — deliberately *not* through the application's own helpers — then
compared with what the HTTP endpoints return. It runs against a **sparse** shop
(180 days, sales on ~35% of them, five SKUs, per-line discounts, one 6× day),
because that is the shape a real small retailer's export has.

### 1. Anomaly baseline collapsed to ₹0

A shop trading a third of the calendar produced a zero-filled median of **₹0** and
a MAD of **0**, so the card read *"0% above your normal daily level of ₹0"* and
**32 of 187 days** were flagged as outliers — a statistical "outlier" that happens
every other day is noise, not a finding.

**Fix:** past `SPARSE_ZERO_DAY_SHARE` (25% zero days) the check runs on **trading
days only** — a closed shop is not an anomaly. No card is published when the
baseline is still 0, and the wording became "typical trading day".

**Result on the same data:** 1 anomaly, baseline ₹10,794.

### 2. The transaction register ignored discounts

`build_ledger_page` computed `quantity × selling_price` locally instead of reusing
the shared derived columns, so the register — and the drill-down, and the PDF
register — showed **gross** revenue while the KPI cards and the P&L showed **net**.
Gap on the audit file: **₹42,941**.

**Fix:** it now reads `_row_revenue` / `_row_profit` from `_prepare`, and
`LedgerEntry` carries a `discount` field that the UI shows as a column whenever
the file has discounts — so `revenue ≠ qty × price` is explained rather than
looking like an arithmetic error.

### 3. Forecast accuracy scored on the wrong basis

MAPE across held-out *days* on a shop that trades a third of the calendar mostly
measures "did we guess which days it opened" — a question no revenue model can
answer — so a projection that is fine in aggregate looked ~20% accurate.

**Fix:** above the same 25% sparsity threshold the backtest scores the held-out
**7-day total**; the response states which basis was used (`accuracy_basis`), and
the forecast strip reports the trading-day ratio (`68 / 187 days had sales`) so a
low daily average isn't misread as decline.

### 4. A single-item shop was its own long tail

`_classify_abc` tested the cumulative revenue share *after* including each item,
so a shop whose one product holds 100% of revenue scored `1.0 > 0.80` and landed
in class **C**.

**Fix:** the boundary is tested on the cumulative share *before* the item, which
makes the item that crosses 80% class A — and guarantees the biggest earner is
always A. (Found by an independent reviewer agent; regression test added.)

---

## 12. Dead code removed

A whole legacy calculation path was still sitting in `sales_calculations.py`,
unreachable from any route: `run_full_analysis`, `apply_time_filter`,
`filter_by_time`, the preset-based `compute_summary` / `compute_daily_trend`,
`_split_periods`, `_get_expected_range` — **214 lines**.

That duplication is exactly how bug #2 happened (two implementations of "revenue
per row", one of which forgot discounts). Slicing now happens only in
`query_engine.build_slice`, and every calculation takes the already-sliced frame.
`compute_pnl_report` also lost an unused `time_filter` parameter. `pyflakes` is
clean over `app/`.

---

## 13. Tests added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/test_accuracy_audit.py` | **24** | KPIs to the rupee · revenue net of discount · trend summing to the KPI · date span · category/item/branch totals · filter parts summing to the whole · margin & average price internally consistent · Pareto reaching 100% · heatmap total · every ledger row reachable and paging summing to the KPI · P&L identities (gross − discount = net, net − COGS = gross profit, category schedule = statement) · anomaly baseline > 0 with no "₹0" text · anomalies rare by construction · finite metrics on every card · velocity = units ÷ window, cover = stock ÷ velocity · ABC partitioning the catalogue · forecast totals = plotted days, band ordered, dates continuous · sparse-shop accuracy basis · register discount arithmetic · **all five endpoints agreeing on one filtered slice** · no NaN/Infinity · PDF builds |
| `backend/tests/test_edge_cases.py` | **13** | Degenerate uploads that must render rather than crash: a single row, one day with twelve items, a free giveaway (zero revenue), a shop that only ever sold at a loss, one item over four weeks, two years of monthly rows, fifty rows on one timestamp, absurd magnitudes (₹99,998,900,001), stock with a frozen zero-velocity item, and a discount larger than the line. Each asserts every published number is finite, no insight card carries an unresolved template or NaN, the P&L identity still holds, short history refuses to forecast, cover is `null` (not infinity) at zero velocity, and revenue floors at zero instead of going negative |
| `frontend/src/__tests__/layout.test.jsx` | **14** | Design-token contract: tokens exist, base font stepped (not `vw`-fluid), Tailwind's small steps raised, 4K/8K breakpoints present, control height 40px touch / 36px mouse, accessibility baseline intact; Card header/action alignment, five KPI tiles showing complete figures with icon+percentage trends, chart in a tokenised `.chart-box`, shared control classes on the studio toolbar, skeleton at chart height, filter bar collapsing to one row |
| `frontend/src/__tests__/interactions.test.jsx` | **14** | Command palette (closed until ⌘K, subsequence filtering, Enter runs + closes, Escape cancels, empty-state message), density toggle flipping the attribute that drives every token, chart view-model rules (donut capped at 6, part-to-whole refused on a time axis, heatmap routed to its own endpoint), the 7-day average line, forecast accuracy labelled by basis with the trading-day ratio, and the currency house rule across every source file |

Regression tests were also added to `test_inventory_and_forecast.py` (single-item
ABC, biggest earner always class A).

---

## 14. Verification

```bash
cd backend  && py -3 -m pytest          # 177 passed
cd backend  && py -3 -m pyflakes app    # clean
cd frontend && npm test                 # 55 passed (4 files)
cd frontend && npm run build            # succeeds
```

| Suite | Result |
|-------|--------|
| Backend | **177 passed** |
| Backend lint | **clean** |
| Frontend | **55 passed** |
| Build | **succeeds** |
| Format fixtures | **6/6 handled** (`py -3 testing2/verify_testing2.py`) |

Two further bugs surfaced when the six `testing2/` fixtures were run through the
pipeline — currency symbols breaking the `Line Total ÷ Quantity` derivation (a GST
register produced **zero** analysable rows), and `dayfirst=True` scrambling ISO
dates (a 100-day marketplace export spanning 337 days). Both are fixed with
regression tests; see [`testing2/README.md`](./testing2/README.md).

Two independent reviewer agents were run against the code (not the docstrings):
the first confirmed the Pro feature claims and found two cosmetic issues (a
duplicated tooltip, an orphaned `__pycache__`); the second confirmed this pass and
found the ABC boundary bug. All findings were fixed and every command re-run
green.

What could **not** be verified in this environment: real-browser rendering. There
is no headless browser available here, so pixel-level appearance, actual scroll
behaviour and true 4K/8K layout were reasoned about and constrained by tokens and
tests, not screenshotted. `npm run dev` is the way to confirm visually.

---

## 15. Still on the table

UI/UX ideas considered and not built in this pass:

1. **Chart annotations** — print the delta on an anomaly marker (`−67%`) and
   label the shaded forecast region on the chart itself, rather than only in the
   tooltip.
2. **Progressive panel streaming** — render each panel the moment its own request
   lands (they are already independent requests) instead of together.
3. **Saved views** — name a filter + chart combination and return to it, which is
   the natural next step now that the whole view state is serialisable.
4. **Print/PDF parity snapshot test** — assert the on-screen period label and
   figures match the exported PDF; needs a PDF text-extraction dependency.
5. **Virtualised tables** — the register caps at 1000 rows per page; a 50k-row
   file would benefit from windowed rendering rather than pagination.
