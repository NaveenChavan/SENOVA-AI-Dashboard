import { formatByMeasure, formatCurrency, formatNumber, formatPercent } from './chartFormat'

/**
 * The chart data as a real table.
 *
 * This is not a nicety: scatter plots, treemaps and heatmaps are rated poor for
 * accessibility, and the guidance for all three is "provide a data table
 * alternative". The studio therefore always offers this view, and screen-reader
 * users get the same numbers as everyone else.
 *
 * Clicking a row drills into that group, exactly like clicking a bar — so the
 * table is a first-class view, not a fallback. Styling comes from the shared
 * compact `.table` class so it matches every other table in the product.
 */
export default function ChartDataTable({ data, onSelect, selectedLabel }) {
  if (!data?.points?.length) {
    return (
      <p className="text-xs py-6 text-center" style={{ color: 'var(--text-muted)' }}>
        No data for this selection.
      </p>
    )
  }

  const measureFormat = data.measure_format ?? 'currency'
  const interactive = typeof onSelect === 'function'

  // Revenue, profit and units already have their own columns below, so showing
  // the selected measure again would duplicate a column (and its header).
  const showMeasureColumn = !['revenue', 'profit', 'units'].includes(data.measure)

  return (
    <table className={`table ${interactive ? 'table--clickable' : ''}`}>
      <caption className="sr-only">
        {data.measure_label} by {data.dimension_label}, with supporting measures
      </caption>
      <thead>
        <tr>
          <th scope="col">{data.dimension_label}</th>
          {showMeasureColumn && <th scope="col">{data.measure_label}</th>}
          <th scope="col">Revenue</th>
          <th scope="col">Profit</th>
          <th scope="col">Units</th>
          <th scope="col">Margin</th>
          <th scope="col">Share</th>
        </tr>
      </thead>
      <tbody>
        {data.points.map((point) => {
          const selected = selectedLabel === point.label
          const clickable = interactive && !point.is_other

          return (
            <tr
              key={point.label}
              onClick={clickable ? () => onSelect(point) : undefined}
              onKeyDown={
                clickable
                  ? (event) => {
                      // Keyboard parity with the click target.
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onSelect(point)
                      }
                    }
                  : undefined
              }
              tabIndex={clickable ? 0 : undefined}
              aria-selected={interactive ? selected : undefined}
              style={{
                background: selected ? 'var(--accent-blue-glow)' : undefined,
                cursor: clickable ? 'pointer' : 'default',
              }}
            >
              <th scope="row">
                <span className="block truncate" style={{ maxWidth: 170 }} title={point.label}>
                  {point.label}
                </span>
              </th>
              {showMeasureColumn && (
                <td className="font-mono font-semibold" style={{ color: 'var(--accent-blue)' }}>
                  {formatByMeasure(point.value, measureFormat)}
                </td>
              )}
              <td className="font-mono" style={{ color: 'var(--text-primary)' }}>
                {formatCurrency(point.revenue)}
              </td>
              <td className="font-mono" style={{ color: point.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                {formatCurrency(point.profit)}
              </td>
              <td className="font-mono">{formatNumber(point.units)}</td>
              <td className="font-mono">{formatPercent(point.margin_pct)}</td>
              <td className="font-mono" style={{ color: 'var(--text-muted)' }}>
                {formatPercent(point.share_pct)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
