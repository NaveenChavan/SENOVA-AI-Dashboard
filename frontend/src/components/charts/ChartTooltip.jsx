import { formatByMeasure, formatCurrency, formatNumber, formatPercent } from './chartFormat'

/**
 * Shared tooltip and legend for every chart in the studio.
 *
 * Two reasons they live in one place: hover tooltips are the primary way a
 * data-dense dashboard stays readable (the design guidance calls them out
 * explicitly), and a legend must accompany every multi-series chart so colour
 * is never the only thing carrying meaning.
 */

/**
 * Tooltip that shows the hovered group's headline measure plus the supporting
 * figures (units, margin, share), because the whole point of the studio is
 * that one hover answers more than one question.
 */
export function StudioTooltip({ active, payload, measureFormat = 'currency' }) {
  if (!active || !payload?.length) return null

  // Every studio chart carries the full ChartPoint on its datum, so the
  // tooltip can read the supporting measures without extra props.
  const point = payload[0]?.payload ?? {}

  return (
    <div
      className="card px-3 py-2 rounded-lg text-xs"
      style={{ borderColor: 'var(--border-active)', minWidth: 170 }}
      role="tooltip"
    >
      <p className="font-semibold mb-1.5" style={{ color: 'var(--text-primary)' }}>
        {point.label ?? '—'}
      </p>

      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex justify-between gap-4 mb-0.5">
          <span style={{ color: 'var(--text-secondary)' }}>{entry.name}</span>
          <span className="font-semibold font-mono" style={{ color: entry.color }}>
            {formatByMeasure(entry.value, entry.dataKey === 'margin_pct' ? 'percent' : measureFormat)}
          </span>
        </p>
      ))}

      <div className="mt-1.5 pt-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <p className="flex justify-between gap-4" style={{ color: 'var(--text-muted)' }}>
          <span>Units</span>
          <span className="font-mono">{formatNumber(point.units)}</span>
        </p>
        <p className="flex justify-between gap-4" style={{ color: 'var(--text-muted)' }}>
          <span>Margin</span>
          <span className="font-mono">{formatPercent(point.margin_pct)}</span>
        </p>
        {point.share_pct != null && (
          <p className="flex justify-between gap-4" style={{ color: 'var(--text-muted)' }}>
            <span>Share</span>
            <span className="font-mono">{formatPercent(point.share_pct)}</span>
          </p>
        )}
      </div>
    </div>
  )
}

/** Tooltip for the trend/forecast chart, which is keyed by date, not group. */
export function TrendTooltip({ active, payload, label, anomalyDates = [] }) {
  if (!active || !payload?.length) return null
  const isAnomaly = anomalyDates.includes(label)

  return (
    <div className="card px-3 py-2 rounded-lg text-xs" style={{ borderColor: 'var(--border-active)' }} role="tooltip">
      <p className="font-semibold mb-1.5" style={{ color: 'var(--text-primary)' }}>
        {label}
      </p>
      {payload
        .filter((entry) => entry.value !== null && entry.value !== undefined)
        .map((entry) => (
          <p key={entry.dataKey} className="flex justify-between gap-4 mb-0.5">
            <span style={{ color: 'var(--text-secondary)' }}>{entry.name}</span>
            <span className="font-semibold font-mono" style={{ color: entry.color }}>
              {formatCurrency(entry.value)}
            </span>
          </p>
        ))}
      {isAnomaly && (
        <p className="mt-1.5 font-medium" style={{ color: 'var(--accent-red)' }}>
          Unusual day — flagged by anomaly detection
        </p>
      )}
    </div>
  )
}

/**
 * Minimal tooltip for charts whose data is a plain `{ name, value }` list
 * rather than a full ChartPoint (e.g. the "Top items" bar panel). Shares the
 * same surface styling and number formatting as the studio tooltip so the two
 * never drift apart visually.
 */
export function SimpleTooltip({ active, payload, label, measureFormat = 'number' }) {
  if (!active || !payload?.length) return null

  return (
    <div className="card px-3 py-2 rounded-lg text-xs" style={{ borderColor: 'var(--border-active)' }} role="tooltip">
      <p className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
        {label}
      </p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex justify-between gap-4">
          <span style={{ color: 'var(--text-secondary)' }}>{entry.name}</span>
          <span className="font-semibold font-mono" style={{ color: entry.color }}>
            {formatByMeasure(entry.value, measureFormat)}
          </span>
        </p>
      ))}
    </div>
  )
}

/**
 * Legend rendered as text + swatch. Charts that encode a series by dash
 * pattern (the forecast line) pass ``dashed`` so the legend shows the same
 * pattern — colour alone is not an accessible signal.
 */
export function ChartLegend({ payload, dashedKeys = [] }) {
  if (!payload?.length) return null

  return (
    <ul className="flex flex-wrap justify-center gap-x-5 gap-y-1.5 mt-3 px-2 list-none">
      {payload.map((entry) => {
        const dashed = dashedKeys.includes(entry.dataKey ?? entry.value)
        return (
          <li key={entry.value} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block"
              style={{
                width: 14,
                height: dashed ? 0 : 10,
                borderRadius: dashed ? 0 : 3,
                borderTop: dashed ? `2px dashed ${entry.color}` : undefined,
                backgroundColor: dashed ? undefined : entry.color,
              }}
            />
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              {entry.value}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
