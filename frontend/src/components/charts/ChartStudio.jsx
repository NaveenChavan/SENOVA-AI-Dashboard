import { useEffect, useMemo, useState } from 'react'

import ChartDataTable from './ChartDataTable'
import HeatmapGrid from './HeatmapGrid'
import { BarView, ComboView, DonutView, ParetoView, ScatterView, TreemapView } from './StudioCharts'
import { formatByMeasure } from './chartFormat'

/**
 * The chart studio: one card, seven selectable chart types, any measure, any
 * dimension the uploaded file actually contains.
 *
 * Design decisions worth knowing:
 * - The chart type, measure and dimension are *questions*, not decoration, so
 *   each option carries a plain-language hint about what it answers.
 * - Donut requests top_n=6 because a pie stops being readable past ~6 slices;
 *   the rest is folded into "Other" server-side without losing the total.
 * - Every view has a "Table" toggle. Scatter, treemap and heatmap in particular
 *   are poor for screen readers, and the accessibility guidance for all three
 *   is to provide a table alternative.
 * - Selecting a bar/slice/tile/row drills down (the parent decides what that
 *   means) — the studio just reports which group was chosen.
 * - Selections persist in localStorage, so a shop owner who always looks at
 *   "profit by branch" gets it back on their next visit.
 */

const STORAGE_KEY = 'senova.chartStudio.v1'

/** The seven chart types, each with the question it answers. */
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
const BASE_DIMENSIONS = [
  { key: 'category', label: 'Category' },
  { key: 'item', label: 'Item' },
  { key: 'day', label: 'Day' },
  { key: 'weekday', label: 'Weekday' },
  { key: 'month', label: 'Month' },
]

/** Chart types that make no sense on a time axis. */
const NON_TIME_ONLY = new Set(['donut', 'pareto', 'scatter', 'treemap'])

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

export default function ChartStudio({
  chartData,
  heatmapData,
  loading,
  availableDimensions = [],
  onQueryChange,
  onDrillDown,
  selectedLabel,
}) {
  const saved = useMemo(loadPreferences, [])
  const [chartType, setChartType] = useState(saved?.chartType ?? 'bar')
  const [measure, setMeasure] = useState(saved?.measure ?? 'revenue')
  const [dimension, setDimension] = useState(saved?.dimension ?? 'category')
  const [showTable, setShowTable] = useState(saved?.showTable ?? false)

  // The optional dimensions come from the file itself (Branch, Payment Mode…),
  // so a column the user never mapped can never appear here.
  const dimensions = useMemo(() => {
    const extras = availableDimensions.filter(
      (option) => !BASE_DIMENSIONS.some((base) => base.key === option.key),
    )
    return [...BASE_DIMENSIONS, ...extras]
  }, [availableDimensions])

  // A time dimension with a donut/Pareto/scatter/treemap selected is nonsense;
  // fall back to Category rather than rendering something misleading.
  const effectiveDimension = NON_TIME_ONLY.has(chartType) && ['day', 'month'].includes(dimension)
    ? 'category'
    : dimension

  // Ask the parent for the data this combination needs. Donut is capped at 6
  // slices; the heatmap needs its own endpoint.
  useEffect(() => {
    onQueryChange?.({
      dimension: effectiveDimension,
      measure,
      top_n: chartType === 'donut' ? 6 : 10,
      needsHeatmap: chartType === 'heatmap',
    })
  }, [chartType, measure, effectiveDimension, onQueryChange])

  useEffect(() => {
    savePreferences({ chartType, measure, dimension, showTable })
  }, [chartType, measure, dimension, showTable])

  const activeType = CHART_TYPES.find((type) => type.value === chartType)
  const isHeatmap = chartType === 'heatmap'
  const hasData = isHeatmap ? heatmapData?.cells?.length : chartData?.points?.length

  return (
    <section className="card p-4 sm:p-5" aria-label="Chart studio">
      {/* ── Controls ─────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 mb-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Chart studio
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {activeType?.hint}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              <span className="sr-only">Measure</span>
              <select
                className="filter-select cursor-pointer"
                value={measure}
                onChange={(event) => setMeasure(event.target.value)}
                aria-label="Measure to plot"
              >
                {MEASURES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            {!isHeatmap && (
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                <span className="sr-only">Group by</span>
                <select
                  className="filter-select cursor-pointer"
                  value={effectiveDimension}
                  onChange={(event) => setDimension(event.target.value)}
                  aria-label="Dimension to group by"
                >
                  {dimensions.map((option) => (
                    <option key={option.key} value={option.key}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <button
              type="button"
              onClick={() => setShowTable((previous) => !previous)}
              aria-pressed={showTable}
              className="text-xs font-medium rounded-lg px-3 cursor-pointer transition-colors"
              style={{
                minHeight: 40,
                border: '1px solid var(--border-subtle)',
                background: showTable ? 'var(--accent-blue-glow)' : 'var(--bg-input)',
                color: showTable ? 'var(--accent-blue)' : 'var(--text-secondary)',
              }}
            >
              {showTable ? 'Chart view' : 'Table view'}
            </button>
          </div>
        </div>

        {/* Chart-type switcher. role=tablist + arrow keys make it keyboard-usable. */}
        <div
          role="tablist"
          aria-label="Chart type"
          className="flex items-center gap-1 p-1 rounded-xl overflow-x-auto"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}
        >
          {CHART_TYPES.map((type) => {
            const active = chartType === type.value
            return (
              <button
                key={type.value}
                role="tab"
                aria-selected={active}
                title={type.hint}
                onClick={() => setChartType(type.value)}
                className="text-xs font-medium rounded-lg whitespace-nowrap cursor-pointer transition-colors"
                style={{
                  padding: '8px 12px',
                  minHeight: 36,
                  background: active
                    ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                    : 'transparent',
                  color: active ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                }}
              >
                {type.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────────────── */}
      {loading && !hasData ? (
        // Skeleton rather than a spinner: it reserves the chart's height, so
        // the page doesn't jump when the data lands.
        <div className="h-64 sm:h-72 md:h-80 rounded-lg animate-pulse" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
      ) : !hasData ? (
        <p className="text-sm py-16 text-center" style={{ color: 'var(--text-muted)' }}>
          Nothing to plot for this selection. Try a wider date range or clear a filter.
        </p>
      ) : isHeatmap ? (
        <HeatmapGrid data={heatmapData} />
      ) : showTable ? (
        <ChartDataTable data={chartData} onSelect={onDrillDown} selectedLabel={selectedLabel} />
      ) : (
        <ChartView type={chartType} data={chartData} onSelect={onDrillDown} />
      )}

      {/* ── Footer: totals + the concentration fact, in words ────────── */}
      {!isHeatmap && chartData?.points?.length > 0 && (
        <p className="text-xs mt-3 pt-3" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
          {chartData.group_count} {chartData.dimension_label.toLowerCase()} group(s) ·{' '}
          {chartData.measure_label} total{' '}
          <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
            {formatByMeasure(chartData.total, chartData.measure_format)}
          </span>
          {chartData.pareto_group_count != null && (
            <>
              {' '}· top {chartData.pareto_group_count} make 80% of it
            </>
          )}
          {' '}· click any {showTable ? 'row' : 'bar or slice'} to drill down
        </p>
      )}
    </section>
  )
}

/** Map the selected type onto its renderer. */
function ChartView({ type, data, onSelect }) {
  switch (type) {
    case 'bar-h':
      return <BarView data={data} horizontal onSelect={onSelect} />
    case 'donut':
      return <DonutView data={data} onSelect={onSelect} />
    case 'combo':
      return <ComboView data={data} onSelect={onSelect} />
    case 'pareto':
      return <ParetoView data={data} onSelect={onSelect} />
    case 'scatter':
      return <ScatterView data={data} onSelect={onSelect} />
    case 'treemap':
      return <TreemapView data={data} onSelect={onSelect} />
    case 'bar':
    default:
      return <BarView data={data} onSelect={onSelect} />
  }
}
