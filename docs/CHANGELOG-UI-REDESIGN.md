# SENOVA Digital Lab — UI/UX Redesign Changelog

**Date:** 2026-07-29
**Scope:** Frontend only (React 18 + Vite + Tailwind CSS). No backend, no
calculation, no analytics logic was modified at any point — verified by
grep audit and a full backend test run after every round of changes.

---

## 1. Foundation — Design Tokens, Font, Dependency

| Change                                                                                                                                                              | File(s)                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Added `motion` (Framer Motion successor), pinned to exact version `12.42.2` (`npm install motion@12.42.2 --save-exact`)                                             | `package.json`                     |
| Added **Space Grotesk** display typeface (weights 400/500/600/700) via Google Fonts, used for headlines only — body/UI text stays on Plus Jakarta Sans              | `index.html`, `tailwind.config.js` |
| New CSS tokens: `--gradient-accent`, `--gradient-accent-soft`, `--shadow-glow`, `--shadow-glow-hover`, `--font-display` — added to both light and dark theme blocks | `index.css`                        |
| New utility classes: `.card-gradient`, `.glow-blue`/`.glow-emerald`, `.btn-gradient`, `.badge-glow`, `.text-display`                                                | `index.css`                        |
| Deeper dark-mode `--shadow-high` for more visual depth                                                                                                              | `index.css`                        |

---

## 2. Shared Primitives

| Change                                                                                                                                    | File(s)      |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| `Button.jsx` — added a `gradient` variant (maps to `.btn-gradient`), existing variants (`primary`/`secondary`/`ghost`/`danger`) untouched | `Button.jsx` |
| `Card.jsx` — added an optional `gradient` prop to opt a single panel into the hairline gradient-border treatment, kept rare by design     | `Card.jsx`   |
| `.stat-tile`, `.chip--active`, `.seg__btn[aria-selected]` — upgraded from flat accent-blue to the gradient treatment with glow shadows    | `index.css`  |
| `Icon.jsx` — reviewed, no changes needed (already theme-safe via `currentColor`)                                                          | —            |

---

## 3. Login Page — Full Redesign

- Hero rewritten with a dominant headline (`.text-display`) and a gradient-text
  accent on "zero spreadsheets."
- New **animated SVG forecast graphic** — a bar cluster with a drawn trend
  line and a dashed forecast projection, echoing the product's real forecast
  chart (built from scratch, no external image).
- Feature bullets converted to staggered, hover-interactive cards.
- Google sign-in button upgraded to the premium gradient CTA (`.btn-gradient`).
- **Brand mark redesign** — logo + wordmark restyled as a stacked lockup
  ("SENOVA" + small tracked-out "Digital Lab" subtitle), pinned to the
  page's top-left corner via absolute positioning, fully detached from the
  flowing hero content (previously it was inline with the hero text block).
- Logo now sits in a plain bordered tile — no gradient chip or blend mode,
  since the actual logo is a detailed illustrated navy/blue/green hexagon
  mark that would have been muddied by either treatment.
- **Theme toggle added directly to the login page** (top-right corner) since
  the page no longer renders the global app header.

**File:** `pages/Login.jsx`

---

## 4. Upload Page — Full Redesign

- **Pipeline stepper** added: _Upload → Confirm columns → Validate rows →
  Build dashboard_, with the active step derived from **real store state**
  (`mappingPreview`, `isLoading`, `uploadDone`) — not a fake progress value.
- `FileDropzone.jsx` — animated states for idle / dragging / uploading, with
  a lifting icon and glowing border on drag-over.
- "Computed analytics engine" badge upgraded to `.badge-glow` (animated
  breathing gradient border, respects `prefers-reduced-motion`).

**Files:** `pages/Upload.jsx`, `components/upload/FileDropzone.jsx`

---

## 5. Dashboard — Full Redesign (all tabs, all components)

| Area                               | Change                                                                                                                                                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shell / toolbar / tabs             | Staggered entrance motion on load; header title uses `.text-display`; skeleton loader added for the Financial Report tab (replacing a spinner)                                                            |
| `SummaryStats.jsx`                 | KPI tiles get a staggered fade-in and a gradient top-accent on hover — `.stat-tile` class and all currency-text assertions preserved exactly                                                              |
| `TrendChart.jsx`                   | Confidence-band area now uses a gradient fill (was flat colour) — zero change to any calculation, animation stays off (`isAnimationActive={false}`) as required for instant filter response               |
| `InsightCards.jsx`                 | Cards get staggered entrance + a subtle glow ring for critical/positive severities                                                                                                                        |
| `InventoryPanel.jsx`               | ABC-class badges upgraded to filled pills; reorder-priority bar uses the gradient fill for high-priority items                                                                                            |
| `DeadStockTable.jsx`               | Status badges upgraded to pill chips                                                                                                                                                                      |
| `PnLReportTable.jsx`               | The P&L statement card is the one "engine computed this" surface with the gradient-border treatment; the category ledger stays plain by design                                                            |
| `ChartStudio` / `StudioCharts.jsx` | All **8 chart types** (Bars, Ranking, Donut, Combo, Pareto, Bubble, Treemap, Heatmap) restyled with gradient fills where appropriate — every `isAnimationActive={false}` preserved, no data logic touched |
| `HeatmapGrid.jsx`                  | Cells get a hover scale + glow on high-intensity values; numeric legend and accessibility structure untouched                                                                                             |
| `FilterPanel.jsx`                  | Expandable filter section now animates open/closed via `AnimatePresence`                                                                                                                                  |
| `DrillDownPanel.jsx`               | Slide-over now animates in/out via `AnimatePresence` — the existing focus-on-open and Escape-to-close logic (`useEffect` hooks) was **left byte-for-byte unchanged**                                      |

---

## 6. Bug Fixes (post-redesign polish round)

| #   | Issue reported                                                                                                  | Root cause                                                                                                                                                                                                          | Fix                                                                                                                                                                                                                                            |
| --- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Header (Upload/Dashboard nav + account avatar) appeared on top of the login screen; page had a forced scrollbar | `App.jsx` wrapped _every_ route, including `/login`, in the global header/footer shell — Login.jsx already builds its own full-screen layout, so it was double-chromed                                              | `App.jsx` now detects `/login` and skips the shell entirely on that route                                                                                                                                                                      |
| 2   | Dark-mode text unreadable on gradient buttons/tabs/badges                                                       | Dark mode's `--gradient-accent` started at a light cyan (`#38bdf8`), but white text was hardcoded on top of every gradient surface — failed WCAG contrast                                                           | Darkened dark-mode gradient's stops so white text holds ≥4.5:1 contrast across the whole gradient; light-mode gradient (already dark enough) untouched                                                                                         |
| 3   | Sign-in card felt too small/narrow for the window                                                               | Fixed `maxWidth: 320` stranded in a much wider column                                                                                                                                                               | Widened to 420px, larger padding, bigger CTA and headline on large screens                                                                                                                                                                     |
| 4   | Login page had no way to switch theme                                                                           | Removing the header (fix #1) also removed the only `ThemeToggle` on that route                                                                                                                                      | Added `<ThemeToggle />` directly to the login page, top-right corner                                                                                                                                                                           |
| 5   | Dashboard toolbar/tabs overlapped chart content while scrolling                                                 | `.toolbar-sticky` was hardcoded to `top: 52px`, assuming the header always physically occupies that space — but the new auto-hiding header slides fully away on scroll, leaving the toolbar glued to a stale offset | Toolbar now reads a `--header-offset` CSS variable kept in sync with the header's real visibility state                                                                                                                                        |
| 6   | Site loaded in dark mode on first visit                                                                         | Original logic used the OS/browser's `prefers-color-scheme` to pick the _default_ theme for a first-time visitor                                                                                                    | Removed the OS-preference fallback entirely — a fresh visit is now **always light** unless the user has explicitly toggled dark before (checked in both `index.html`'s pre-mount script and `useThemeStore.js`, kept in sync to avoid a flash) |
| 7   | Navbar hide/show and toolbar shift felt laggy, looked like two separate jumps instead of one motion             | Header animated via Motion's `transform` (GPU-smooth); toolbar animated via a CSS `top` change routed through React state — a layout-reflow property, always a frame behind a transform                             | Toolbar switched to `transform: translateY()` (same technique as the header) and its driving CSS variable is now written **directly to the DOM in the same scroll-event tick** as the header's own animation — both move in the same frame     |

---

## 7. Verification (every round)

- `npm run build` — succeeded after every change.
- `npm test` (Vitest) — **55/55 frontend tests passing** throughout, including
  smoke tests for all 8 chart types against realistic data and exact
  KPI-figure assertions (e.g. `₹18,40,000`).
- `python -m pytest -q` (backend) — **132/132 tests passing**, confirming
  zero impact on anomaly detection, forecasting, ABC classification,
  reorder scoring, P&L computation, or any other calculation.
- Targeted `grep` audits after each round confirmed no UI-layer change
  (`motion`, `headerHidden`, `ThemeToggle`, etc.) ever touched `backend/` or
  `useSalesStore.js` (the store holding every fetched analytics result).

---

## 8. New Dependencies & README Updates

- **One new runtime dependency:** `motion@12.42.2` (exact-pinned, no
  `^`/`~` range). Ships no network calls, no access to sales data — animates
  already-rendered DOM nodes only.
- **One new font:** Space Grotesk (Google Fonts `<link>`, not an npm
  package).
- `README.md` updated: Security section now discloses `motion` accurately
  (previously claimed "no new dependencies," which was corrected); Tech
  Stack section lists Motion and Space Grotesk.
