import { useEffect, useMemo } from 'react'

import ChartDataTable from './ChartDataTable'
import HeatmapGrid from './HeatmapGrid'
import { BarView, ComboView, DonutView, ParetoView, ScatterView, TreemapView } from './StudioCharts'
import { formatByMeasure } from './chartFormat'
import { BASE_DIMENSIONS, CHART_TYPES, MEASURES, resolveChartRequest, useChartView } from './chartView'

/**
 * The chart studio: one card, eight selectable views, any measure, any dimension
 * the uploaded file actually contains.
 *
 * Design decisions worth knowing:
 * - The chart type, measure and dimension are *questions*, not decoration, so
 *   each option carries a plain-language hint about what it answers.
 * - Every view has a "Table" toggle. Scatter, treemap and heatmap in particular
 *   are poor for screen readers, and the accessibility guidance for all three
 *   is to provide a table alternative.
 * - Selecting a bar/slice/tile/row drills down (the parent decides what that
 *   means) — the studio just reports which group was chosen.
 * - The view state and the request it maps to live in ``chartView.js``, so the
 *   page (and its command palette) can drive the panel without a second copy of
 *   the state.
 */

export default function ChartStudio({
  chartData,
  heatmapData,
  loading,
  availableDimensions = [],
  extraMeasures = [],
  measureAvailability = [],
  schemaReady = true,
  onQueryChange,
  onDrillDown,
  selectedLabel,
  wide = false,
  view: controlledView,
  onViewChange,
}) {
  // Controlled when the page passes a view (so the palette can drive it),
  // self-contained otherwise — the panel stays usable on its own.
  const [ownView, setOwnView] = useChartView()
  const view = controlledView ?? ownView
  const update = onViewChange ?? setOwnView

  const { chartType, measure, showTable } = view

  // The optional dimensions come from the file itself (Branch, Payment Mode…),
  // so a column the user never mapped can never appear here.
  const dimensions = useMemo(() => {
    const presentKeys = new Set((availableDimensions || []).map((option) => option.key))
    // Category and Item are optional. Date-derived dimensions remain available
    // even though they are not real columns in the uploaded file.
    const base = BASE_DIMENSIONS.filter(
      (option) => ['day', 'weekday', 'month'].includes(option.key) || presentKeys.has(option.key),
    )
    const extras = (availableDimensions || []).filter(
      (option) => !BASE_DIMENSIONS.some((baseOption) => baseOption.key === option.key),
    )
    return [...base, ...extras]
  }, [availableDimensions])

  // Keep only built-in measures that the uploaded file can calculate. Before
  // capability metadata arrives, retain the old option list for compatibility;
  // once received, unavailable values are not offered as if they were real zeros.
  const measures = useMemo(() => {
    const knownAvailability = new Map((measureAvailability || []).map((item) => [item.key, item]))
    const hasAvailability = knownAvailability.size > 0
    const base = hasAvailability
      ? MEASURES.filter((option) => knownAvailability.get(option.value)?.available === true)
      : MEASURES
    const extras = (extraMeasures || []).map((m) => {
      const isAvg = m.aggregation === 'avg' || m.aggregation === 'average' || m.additive === false
      return {
        value: m.key,
        label: isAvg ? `${m.label} (average, not sum)` : m.label,
      }
    })
    return [...base, ...extras]
  }, [extraMeasures, measureAvailability])

  const availableDimensionKeys = dimensions.map((option) => option.key)
  const defaultDimension = availableDimensionKeys.includes('category')
    ? 'category'
    : availableDimensionKeys.includes('item')
      ? 'item'
      : availableDimensionKeys[0] || 'day'
  const availableMeasureKeys = measures.map((option) => option.value)
  const effectiveMeasure = availableMeasureKeys.includes(view.measure)
    ? view.measure
    : availableMeasureKeys.includes('revenue')
      ? 'revenue'
      : availableMeasureKeys[0] || 'revenue'
  const effectiveView = {
    ...view,
    measure: effectiveMeasure,
    dimension: availableDimensionKeys.includes(view.dimension) ? view.dimension : defaultDimension,
  }
  const request = useMemo(() => {
    const resolved = resolveChartRequest({
      ...view,
      measure: effectiveMeasure,
      dimension: effectiveView.dimension,
    })
    const knownKeys = new Set(dimensions.map((option) => option.key))
    // resolveChartRequest traditionally falls back to category for non-time
    // charts. When Category is absent, use the already-validated available axis.
    if (!knownKeys.has(resolved.dimension)) {
      resolved.dimension = effectiveView.dimension
    }
    return resolved
  }, [view.chartType, effectiveMeasure, effectiveView.dimension, dimensions])
  const effectiveDimension = request.dimension

  useEffect(() => {
    if (!schemaReady) return
    if (view.measure !== effectiveMeasure || view.dimension !== effectiveView.dimension) {
      update({ measure: effectiveMeasure, dimension: effectiveView.dimension })
    }
  }, [schemaReady, view.measure, view.dimension, effectiveMeasure, effectiveView.dimension, update])

  // Do not issue a speculative invalid query or rewrite the saved chart axis
  // while file-specific dimensions/measures are still loading.
  useEffect(() => {
    if (!schemaReady) return
    onQueryChange?.(request)
  }, [schemaReady, request, onQueryChange])

  const activeType = CHART_TYPES.find((type) => type.value === chartType)
  const isHeatmap = chartType === 'heatmap'
  const hasData = isHeatmap ? heatmapData?.cells?.length : chartData?.points?.length

  return (
    <section className="card" aria-label="Chart studio">
      {/* ── Header row: title + measure/dimension/table controls ───────── */}
      <header
        className="flex items-center justify-between gap-2 px-[var(--card-pad)] flex-wrap"
        style={{ minHeight: 42, paddingTop: 6, paddingBottom: 6, borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="min-w-0">
          <h3 className="panel-title truncate">Chart studio</h3>
          <p className="panel-hint truncate">{activeType?.hint}</p>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <select
            className="filter-select"
            value={effectiveMeasure}
            onChange={(event) => update({ measure: event.target.value })}
            aria-label="Measure to plot"
          >
            {measures.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          {!isHeatmap && (
            <select
              className="filter-select"
              value={effectiveDimension}
              onChange={(event) => update({ dimension: event.target.value })}
              aria-label="Dimension to group by"
            >
              {dimensions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => update({ showTable: !showTable })}
            aria-pressed={showTable}
            className="btn"
            title={showTable ? 'Show the chart' : 'Show the same data as a table'}
          >
            {showTable ? 'Chart' : 'Table'}
          </button>
        </div>
      </header>

      {/* ── Chart-type switcher ────────────────────────────────────────── */}
      <div className="px-[var(--card-pad)] pt-[var(--card-pad)]">
        <div className="seg w-full" role="tablist" aria-label="Chart type">
          {CHART_TYPES.map((type) => (
            <button
              key={type.value}
              role="tab"
              type="button"
              className="seg__btn"
              aria-selected={chartType === type.value}
              title={type.hint}
              onClick={() => update({ chartType: type.value })}
            >
              {type.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      {/* When the panel spans the full page width it overrides --chart-h with
          the shorter --chart-h-wide: a wide chart stays readable at less
          height, and every child (chart, skeleton, empty state) inherits the
          override through the CSS variable rather than needing its own prop. */}
      <div className="card-pad" style={wide ? { '--chart-h': 'var(--chart-h-wide)' } : undefined}>
        {loading && !hasData ? (
          // Skeleton at the chart's exact height, so the card doesn't resize
          // when the data lands.
          <div className="skeleton chart-box" />
        ) : !hasData ? (
          <div className="chart-box flex items-center justify-center">
            <p className="text-xs text-center px-4" style={{ color: 'var(--text-muted)' }}>
              Nothing to plot for this selection. Try a wider date range or clear a filter.
            </p>
          </div>
        ) : isHeatmap ? (
          <HeatmapGrid data={heatmapData} />
        ) : showTable ? (
          <div className="scroll-x" style={{ maxHeight: 'var(--chart-h)' }}>
            <ChartDataTable data={chartData} onSelect={onDrillDown} selectedLabel={selectedLabel} />
          </div>
        ) : (
          <ChartView type={chartType} data={chartData} onSelect={onDrillDown} />
        )}

        {/* Footer: totals + the concentration fact, in words. */}
        {!isHeatmap && chartData?.points?.length > 0 && (
          <p className="text-[12px] mt-2.5 pt-2.5" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
            {chartData.group_count} {chartData.dimension_label.toLowerCase()} group(s) · {chartData.measure_label}{' '}
            <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
              {formatByMeasure(chartData.total, chartData.measure_format)}
            </span>
            {chartData.pareto_group_count != null && <> · top {chartData.pareto_group_count} make 80%</>} · click to
            drill down
          </p>
        )}
      </div>
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
