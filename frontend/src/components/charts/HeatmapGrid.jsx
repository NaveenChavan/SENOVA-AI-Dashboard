import { formatByMeasure } from './chartFormat'

/**
 * Weekday × week heatmap, built as a CSS grid rather than with a charting
 * library (Recharts has no heatmap, and this needs no extra dependency).
 *
 * Accessibility decisions, straight from the visualisation guidance:
 * - a *numeric* legend accompanies the colour ramp, so intensity is never
 *   conveyed by colour alone;
 * - every cell is a real table cell with a text title, readable by a screen
 *   reader and on hover;
 * - the ramp is single-hue (light → strong brand blue), which stays
 *   distinguishable for the common forms of colour-blindness, instead of a
 *   red/green scale.
 */
export default function HeatmapGrid({ data }) {
  if (!data?.cells?.length) {
    return (
      <p className="text-sm py-12 text-center" style={{ color: 'var(--text-muted)' }}>
        Not enough dated rows to build a weekday pattern yet.
      </p>
    )
  }

  const { rows, columns, column_dates: columnDates, cells, min_value: min, max_value: max } = data

  // Fast lookup by "row|column" so rendering stays O(rows × columns).
  const byKey = new Map(cells.map((cell) => [`${cell.row}|${cell.column}`, cell]))
  const span = max - min || 1

  /** 0 → barely tinted, 1 → full brand blue. */
  const intensityOf = (value) => 0.08 + 0.92 * Math.min(Math.max((value - min) / span, 0), 1)

  return (
    <div className="space-y-3">
      {/* overflow-x-auto: a 12-week grid must scroll, not break the layout. */}
      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: 3 }}>
          <caption className="sr-only">
            {data.measure_label} by weekday and week. Darker cells are higher values.
          </caption>
          <thead>
            <tr>
              <th className="sr-only" scope="col">
                Weekday
              </th>
              {columns.map((column, index) => (
                <th
                  key={column}
                  scope="col"
                  className="text-[10px] font-medium pb-1"
                  style={{ color: 'var(--text-muted)', minWidth: 34 }}
                  title={columnDates?.[index] ? `Week beginning ${columnDates[index]}` : column}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <th
                  scope="row"
                  className="text-[11px] font-medium pr-2 text-right"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {row}
                </th>
                {columns.map((column, index) => {
                  const cell = byKey.get(`${row}|${column}`)
                  const value = cell?.value ?? 0
                  const label = `${row}, ${column}${
                    columnDates?.[index] ? ` (week of ${columnDates[index]})` : ''
                  }: ${formatByMeasure(value, data.measure_format)}${
                    cell ? ` from ${cell.transactions} transaction(s)` : ' — no sales'
                  }`

                  return (
                    <td
                      key={column}
                      title={label}
                      aria-label={label}
                      className="rounded transition-colors"
                      style={{
                        width: 34,
                        height: 26,
                        // No cell → a visibly empty slot, not a "zero" that
                        // looks like a recorded sale of nothing.
                        background: cell
                          ? `color-mix(in srgb, var(--accent-blue) ${Math.round(intensityOf(value) * 100)}%, transparent)`
                          : 'var(--bg-input)',
                        border: '1px solid var(--border-subtle)',
                      }}
                    />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Numeric legend: the ramp plus the actual range it maps to. */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {formatByMeasure(min, data.measure_format, { compact: true })}
        </span>
        <div
          className="h-2.5 rounded-full flex-1"
          style={{
            minWidth: 120,
            maxWidth: 220,
            background:
              'linear-gradient(90deg, color-mix(in srgb, var(--accent-blue) 8%, transparent), var(--accent-blue))',
          }}
          aria-hidden="true"
        />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {formatByMeasure(max, data.measure_format, { compact: true })}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          · {data.measure_label} per day
        </span>
      </div>
    </div>
  )
}
