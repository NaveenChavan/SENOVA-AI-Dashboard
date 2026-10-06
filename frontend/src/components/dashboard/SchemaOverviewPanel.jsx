import { useState } from 'react'

import Icon from '../common/Icon'

/**
 * What this particular file can be asked — answered once, up front, from the
 * server's own capability description.
 *
 * It exists to kill a specific dishonesty in the dashboard. A file with no Cost
 * Price column would otherwise show a profit card reading ₹0, which looks
 * identical to a genuinely unprofitable month. Here the card is present and
 * marked unavailable, with the one action that unlocks it — so "we can't
 * compute this from your file" and "this is zero" stop being the same picture.
 *
 * Two rules it never breaks: it contains no business figures at all (every
 * number still comes from the endpoints that computed it, so this panel cannot
 * disagree with the dashboard), and it hides nothing silently.
 */
export default function SchemaOverviewPanel({ schema, loading }) {
  const [open, setOpen] = useState(false)

  if (!schema) return null

  const kpi = schema.kpi_cards ?? []
  const charts = schema.charts ?? []
  const dimensions = schema.dimensions ?? []
  const measures = schema.measures ?? []
  const missing = schema.missing_required_columns ?? []

  const availableCount = kpi.filter((card) => card.available).length
  const blocked = kpi.filter((card) => !card.available && card.reason)

  return (
    <section aria-label="What this file can be asked" className="card card-pad">
      <header className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="panel-title flex items-center gap-1.5">
          <Icon name="chart" className="w-3.5 h-3.5" style={{ color: 'var(--accent-blue)' }} />
          What this file can answer
        </h2>
        <button
          type="button"
          className="text-[11.5px]"
          style={{ color: 'var(--text-muted)' }}
          aria-expanded={open}
          onClick={() => setOpen((previous) => !previous)}
        >
          {open ? 'Hide the detail' : `Show the detail (${charts.length + dimensions.length + measures.length})`}
        </button>
      </header>

      <p className="text-[12px] mt-1" style={{ color: 'var(--text-secondary)' }}>
        {availableCount} of {kpi.length} headline numbers are computable from this file
        {missing.length > 0 && (
          <>
            {' '}
            — <strong style={{ color: 'var(--accent-amber)' }}>still needs {missing.join(', ')}</strong>
          </>
        )}
        . Anything marked unavailable below says what would unlock it.
      </p>

      <ul className="flex flex-wrap gap-1.5 mt-2.5">
        {kpi.map((card) => (
          <li key={card.key}>
            <StatusPill label={card.label} available={card.available} reason={card.reason} />
          </li>
        ))}
      </ul>

      {/* The pill carries the unlock reason only as a tooltip, which is no help
          on a phone and no help to a screen reader. Anything it cannot show is
          written out here, so "not computable" is always actionable. */}
      {blocked.length > 0 && (
        <ul className="space-y-1 mt-2">
          {blocked.map((card) => (
            <li key={card.key} className="flex items-start gap-1.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
              <Icon name="info" className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: 'var(--accent-amber)' }} />
              <span>
                <strong style={{ color: 'var(--text-secondary)' }}>{card.label}</strong> — {card.reason}
              </span>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-[var(--gap)] mt-3">
          <CapabilityColumn title="Charts" empty="No charts described.">
            {charts.map((chart) => (
              <CapabilityRow
                key={chart.key}
                label={chart.label}
                available={chart.available}
                reason={chart.reason ?? shortHistoryReason(chart)}
              />
            ))}
          </CapabilityColumn>

          <CapabilityColumn title="Filters & chart axes" empty="No extra dimensions.">
            {dimensions.map((dimension) => (
              <CapabilityRow
                key={dimension.key}
                label={dimension.label}
                available={dimension.available}
                reason={dimension.reason}
              />
            ))}
          </CapabilityColumn>

          <CapabilityColumn title="Measures" empty="No measures described.">
            {measures.map((measure) => (
              <CapabilityRow
                key={measure.key}
                label={measure.label}
                available={measure.available}
                reason={measure.reason}
                suffix={measure.available && !measure.additive ? 'average, not sum' : null}
              />
            ))}
          </CapabilityColumn>
        </div>
      )}
    </section>
  )
}

/**
 * A chart can be available in principle and still say nothing useful, because
 * one distinct category draws a single lonely bar. The server reports both
 * numbers rather than collapsing them, so we explain the shortfall instead of
 * rendering a near-empty chart.
 */
function shortHistoryReason(chart) {
  if (chart.available) return null
  if (typeof chart.distinct_values === 'number' && chart.min_categories > 0) {
    return `Only ${chart.distinct_values} distinct value${chart.distinct_values === 1 ? '' : 's'} here — needs ${chart.min_categories} to be worth drawing.`
  }
  return null
}

function StatusPill({ label, available, reason }) {
  return (
    <span
      className="inline-block text-[11.5px] font-semibold px-1.5 py-0.5 rounded-full"
      title={available ? label : (reason ?? label)}
      style={{
        color: available ? 'var(--accent-green)' : 'var(--text-muted)',
        border: `1px solid ${available ? 'var(--accent-green)' : 'var(--border-subtle)'}`,
      }}
    >
      {available ? label : `${label} — no`}
    </span>
  )
}

function CapabilityColumn({ title, empty, children }) {
  const rows = (Array.isArray(children) ? children.flat() : [children]).filter(Boolean)

  return (
    <div>
      <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-[12px] mt-1" style={{ color: 'var(--text-muted)' }}>
          {empty}
        </p>
      ) : (
        <ul className="space-y-1.5 mt-1.5">
          {rows}
        </ul>
      )}
    </div>
  )
}

function CapabilityRow({ label, available, reason, suffix }) {
  return (
    <li className="flex items-start gap-1.5">
      <Icon
        name={available ? 'check' : 'close'}
        className="w-3.5 h-3.5 shrink-0 mt-0.5"
        style={{ color: available ? 'var(--accent-green)' : 'var(--text-muted)' }}
      />
      <span className="min-w-0">
        <span
          className="text-[12.5px]"
          style={{
            color: available ? 'var(--text-primary)' : 'var(--text-muted)',
            textDecoration: available ? 'none' : 'line-through',
            textDecorationColor: 'var(--border-subtle)',
          }}
        >
          {label}
        </span>
        {suffix && (
          <span className="block text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {suffix}
          </span>
        )}
        {!available && reason && (
          <span className="block text-[11.5px] leading-snug" style={{ color: 'var(--text-muted)' }}>
            {reason}
          </span>
        )}
      </span>
    </li>
  )
}