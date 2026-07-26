import { useCallback, useEffect, useState } from 'react'

/**
 * The chart studio's *view model*: which chart type, measure and dimension are
 * selected, how that maps onto an API request, and how the choice persists.
 *
 * It lives in its own module (not inside ChartStudio) for two reasons:
 * - the page owns the state so the command palette can change the chart type
 *   from outside the panel — a second copy inside the component would drift;
 * - the panel itself stays lazily loaded, because importing this module doesn't
 *   pull Recharts into the page bundle.
 */

const STORAGE_KEY = 'senova.chartStudio.v1'

/** The eight selectable views, each with the question it answers. */
export const CHART_TYPES = [
  { value: 'bar', label: 'Bars', hint: 'Compare groups side by side' },
  { value: 'bar-h', label: 'Ranking', hint: 'Horizontal bars — best for long names' },
  { value: 'donut', label: 'Donut', hint: 'Share of the whole (top 6)' },
  { value: 'combo', label: 'Combo', hint: 'Revenue bars vs margin % line' },
  { value: 'pareto', label: 'Pareto', hint: '80/20 concentration curve' },
  { value: 'scatter', label: 'Bubble', hint: 'Price vs volume, size = revenue' },
  { value: 'treemap', label: 'Treemap', hint: 'Area = share, at a glance' },
  { value: 'heatmap', label: 'Heatmap', hint: 'Weekday × week intensity' },
]

/** Measures the API can plot; labels match the server's own labels. */
export const MEASURES = [
  { value: 'revenue', label: 'Revenue' },
  { value: 'profit', label: 'Profit' },
  { value: 'cost', label: 'Cost' },
  { value: 'units', label: 'Units sold' },
  { value: 'transactions', label: 'Transactions' },
  { value: 'margin_pct', label: 'Margin %' },
  { value: 'avg_price', label: 'Avg selling price' },
  { value: 'discount', label: 'Discount given' },
]

/** Dimensions that always exist, plus the time ones derived from the date. */
export const BASE_DIMENSIONS = [
  { key: 'category', label: 'Category' },
  { key: 'item', label: 'Item' },
  { key: 'day', label: 'Day' },
  { key: 'weekday', label: 'Weekday' },
  { key: 'month', label: 'Month' },
]

/** Chart types that make no sense on a continuous time axis. */
export const NON_TIME_ONLY = new Set(['donut', 'pareto', 'scatter', 'treemap'])

export const DEFAULT_VIEW = {
  chartType: 'bar',
  measure: 'revenue',
  dimension: 'category',
  showTable: false,
}

function loadPreferences() {
  // A corrupt or absent localStorage entry must never break the dashboard.
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function savePreferences(preferences) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
  } catch {
    // Private-browsing mode blocks writes; preferences just won't persist.
  }
}

/** View state + persistence. Returns ``[view, update]``; update takes a patch. */
export function useChartView() {
  const [view, setView] = useState(() => ({ ...DEFAULT_VIEW, ...(loadPreferences() ?? {}) }))

  useEffect(() => {
    savePreferences(view)
  }, [view])

  const update = useCallback((partial) => {
    setView((previous) => ({ ...previous, ...partial }))
  }, [])

  return [view, update]
}

/**
 * Turn a view into the request the API needs.
 *
 * Two rules live here rather than in the component, so the page and the panel
 * can never disagree about what is being fetched:
 * - a donut is capped at 6 slices (a pie stops being readable past ~6);
 * - donut/Pareto/scatter/treemap on a day/month axis is nonsense, so those fall
 *   back to Category instead of rendering something misleading.
 */
export function resolveChartRequest(view) {
  const dimension =
    NON_TIME_ONLY.has(view.chartType) && ['day', 'month'].includes(view.dimension)
      ? 'category'
      : view.dimension

  return {
    dimension,
    measure: view.measure,
    top_n: view.chartType === 'donut' ? 6 : 10,
    needsHeatmap: view.chartType === 'heatmap',
  }
}
