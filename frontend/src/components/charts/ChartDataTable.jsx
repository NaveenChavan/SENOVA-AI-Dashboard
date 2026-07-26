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
 * table is a first-class view, not a fallback.
 */
export default function ChartDataTable({ data, onSelect, selectedLabel }) {
  if (!data?.points?.length) {
    return (
      <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
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
    // overflow-x-auto keeps a wide table usable on a 375px phone instead of
    // breaking the page layout.
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="w-full text-sm border-collapse">
        <caption className="sr-only">
          {data.measure_label} by {data.dimension_label}, with supporting measures
        </caption>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-strong)' }}>
            <th scope="col" className="text-left py-2 pr-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              {data.dimension_label}
            </th>
            {showMeasureColumn && (
              <th scope="col" className="text-right py-2 px-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                {data.measure_label}
              </th>
            )}
            <th scope="col" className="text-right py-2 px-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Revenue
            </th>
            <th scope="col" className="text-right py-2 px-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Profit
            </th>
            <th scope="col" className="text-right py-2 px-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Units
            </th>
            <th scope="col" className="text-right py-2 px-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Margin
            </th>
            <th scope="col" className="text-right py-2 pl-3 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Share
            </th>
          </tr>
        </thead>
        <tbody>
          {data.points.map((point) => {
            const isSelected = selectedLabel === point.label
            return (
              <tr
                key={point.label}
                onClick={interactive && !point.is_other ? () => onSelect(point) : undefined}
                onKeyDown={
                  interactive && !point.is_other
                    ? (event) => {
                        // Keyboard parity with the click target.
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onSelect(point)
                        }
                      }
                    : undefined
                }
                tabIndex={interactive && !point.is_other ? 0 : undefined}
                aria-selected={interactive ? isSelected : undefined}
                className="transition-colors"
                style={{
                  borderBottom: '1px solid var(--border-subtle)',
                  background: isSelected ? 'var(--accent-blue-glow)' : 'transparent',
                  cursor: interactive && !point.is_other ? 'pointer' : 'default',
                }}
                onMouseEnter={(event) => {
                  if (!isSelected) event.currentTarget.style.background = 'var(--bg-card-hover)'
                }}
                onMouseLeave={(event) => {
                  if (!isSelected) event.currentTarget.style.background = 'transparent'
                }}
              >
                <th
                  scope="row"
                  className="text-left py-2 pr-3 font-medium"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {point.label}
                </th>
                {showMeasureColumn && (
                  <td className="text-right py-2 px-3 font-mono font-semibold" style={{ color: 'var(--accent-blue)' }}>
                    {formatByMeasure(point.value, measureFormat)}
                  </td>
                )}
                <td className="text-right py-2 px-3 font-mono" style={{ color: 'var(--text-primary)' }}>
                  {formatCurrency(point.revenue)}
                </td>
                <td
                  className="text-right py-2 px-3 font-mono"
                  style={{ color: point.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                >
                  {formatCurrency(point.profit)}
                </td>
                <td className="text-right py-2 px-3 font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {formatNumber(point.units)}
                </td>
                <td className="text-right py-2 px-3 font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {formatPercent(point.margin_pct)}
                </td>
                <td className="text-right py-2 pl-3 font-mono" style={{ color: 'var(--text-muted)' }}>
                  {formatPercent(point.share_pct)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
