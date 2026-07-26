import { useState } from 'react'

import Icon from '../common/Icon'
import { formatCurrency, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * Feature 3 — inventory & reorder intelligence.
 *
 * Two modes, never blurred together:
 * - **Demand mode** (a plain sales register): velocity, trend, ABC class,
 *   ageing and a reorder-priority score.
 * - **Stock-aware mode** (a stock column was mapped): the same plus real
 *   days-of-cover, reorder alerts and capital locked per item.
 *
 * When stock is unknown the stock columns are simply absent and a note explains
 * how to unlock them — showing a guessed "days of cover" would be worse than
 * showing none.
 */

const ABC_HELP = 'A = the items making your first 80% of revenue, B = the next 15%, C = the long tail.'

/** Sort options, phrased as the question the shop owner is asking. */
const SORTS = [
  { value: 'reorder_priority', label: 'Reorder priority' },
  { value: 'velocity_per_day', label: 'Fastest moving' },
  { value: 'revenue', label: 'Highest revenue' },
  { value: 'days_since_last_sale', label: 'Longest idle' },
  { value: 'margin_pct', label: 'Thinnest margin', ascending: true },
]

export default function InventoryPanel({ inventory, loading, forecast }) {
  const [sortKey, setSortKey] = useState('reorder_priority')
  const [showAll, setShowAll] = useState(false)

  if (loading && !inventory) {
    return (
      <div className="card p-4 sm:p-6 animate-pulse">
        <div className="h-4 w-40 rounded mb-6" style={{ background: 'var(--bg-skeleton)' }} />
        <div className="h-64 rounded" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
      </div>
    )
  }

  if (!inventory?.items?.length) {
    return (
      <div className="card p-8 text-center">
        <Icon name="box" className="w-8 h-8 mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          No stock movement in this period
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          {inventory?.note ?? 'Widen the date range or clear a filter to see item-level demand.'}
        </p>
      </div>
    )
  }

  const sort = SORTS.find((option) => option.value === sortKey) ?? SORTS[0]
  const sorted = [...inventory.items].sort((a, b) => {
    const left = a[sort.value] ?? 0
    const right = b[sort.value] ?? 0
    return sort.ascending ? left - right : right - left
  })
  const visible = showAll ? sorted : sorted.slice(0, 12)

  // Per-item demand projections come from the forecast endpoint; joining them
  // here turns "what sells fast" into "how many to buy".
  const expectedUnits = new Map(
    (forecast?.item_forecasts ?? []).map((entry) => [entry.item, entry.expected_units]),
  )

  return (
    <section className="space-y-4 sm:space-y-6" aria-label="Inventory intelligence">
      {/* ── ABC + capital tiles ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        {inventory.abc_buckets.map((bucket) => (
          <div key={bucket.label} className="stat-tile">
            <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>
              {bucket.label}
            </p>
            <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
              {formatNumber(bucket.item_count)} <span className="text-xs font-normal">items</span>
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {formatCurrency(bucket.revenue)} · {formatPercent(bucket.revenue_share_pct, 0)} of revenue
            </p>
          </div>
        ))}

        <div className="stat-tile">
          <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>
            {inventory.stock_aware ? 'Capital locked in stock' : 'Reorder candidates'}
          </p>
          <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
            {inventory.stock_aware
              ? formatCurrency(inventory.total_capital_locked)
              : formatNumber(inventory.items.filter((item) => item.reorder_priority >= 50).length)}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            {inventory.stock_aware
              ? `${formatNumber(inventory.reorder_count)} item(s) below ${formatNumber(7)} days of cover`
              : `Priority 50+ over ${inventory.window_days} day(s)`}
          </p>
        </div>
      </div>

      {/* ── Ageing buckets ──────────────────────────────────────────── */}
      {inventory.ageing_buckets.length > 0 && (
        <div className="card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-secondary)' }}>
            Stock ageing — how long since each item last sold
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {inventory.ageing_buckets.map((bucket) => (
              <div key={bucket.label}>
                <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
                  {bucket.label}
                </p>
                <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                  {formatNumber(bucket.item_count)}
                </p>
                <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {formatCurrency(bucket.revenue)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Reorder table ───────────────────────────────────────────── */}
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Reorder priority
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }} title={ABC_HELP}>
              Blend of sales speed, trend and recency over {inventory.window_days} day(s)
            </p>
          </div>

          <label className="text-xs">
            <span className="sr-only">Sort items by</span>
            <select
              className="filter-select cursor-pointer"
              value={sortKey}
              onChange={(event) => setSortKey(event.target.value)}
              aria-label="Sort items by"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {!inventory.stock_aware && inventory.note && (
          <p
            className="text-xs mb-3 px-3 py-2 rounded-lg flex items-start gap-2"
            style={{ background: 'var(--bg-input)', color: 'var(--text-secondary)' }}
            role="note"
          >
            <Icon name="info" className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} />
            <span>{inventory.note}</span>
          </p>
        )}

        <div className="overflow-x-auto -mx-1 px-1">
          <table className="w-full text-sm border-collapse">
            <caption className="sr-only">
              Items ranked by {sort.label.toLowerCase()}, with velocity, class, ageing and reorder priority
            </caption>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-strong)' }}>
                <Th align="left">Item</Th>
                <Th title={ABC_HELP}>Class</Th>
                <Th>Units</Th>
                <Th title="Units sold per calendar day in this period">Per day</Th>
                <Th title="Late-period speed vs early-period speed">Trend</Th>
                <Th>Idle days</Th>
                {inventory.stock_aware && <Th>Stock</Th>}
                {inventory.stock_aware && <Th title="Stock ÷ daily sales speed">Cover</Th>}
                <Th title="Expected units over the forecast horizon">Next period</Th>
                <Th>Priority</Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr
                  key={item.item}
                  className="transition-colors"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                  onMouseEnter={(event) => {
                    event.currentTarget.style.background = 'var(--bg-card-hover)'
                  }}
                  onMouseLeave={(event) => {
                    event.currentTarget.style.background = 'transparent'
                  }}
                >
                  <th scope="row" className="text-left py-2 pr-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                    {item.item}
                    <span className="block text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>
                      {item.category} · {formatCurrency(item.revenue)} · {formatPercent(item.margin_pct)} margin
                    </span>
                  </th>
                  <Td>
                    <ClassBadge value={item.abc_class} />
                  </Td>
                  <Td mono>{formatNumber(item.units_sold)}</Td>
                  <Td mono>{item.velocity_per_day.toFixed(2)}</Td>
                  <Td>
                    <TrendBadge factor={item.trend_factor} />
                  </Td>
                  <Td mono>{formatNumber(item.days_since_last_sale)}</Td>
                  {inventory.stock_aware && <Td mono>{formatNumber(item.stock_on_hand)}</Td>}
                  {inventory.stock_aware && (
                    <Td mono>
                      <span style={{ color: item.reorder_flag ? 'var(--accent-red)' : 'var(--text-secondary)' }}>
                        {item.days_of_cover == null ? '—' : `${item.days_of_cover.toFixed(1)}d`}
                      </span>
                    </Td>
                  )}
                  <Td mono>
                    {expectedUnits.has(item.item) ? formatNumber(expectedUnits.get(item.item), 0) : '—'}
                  </Td>
                  <Td>
                    <PriorityBar value={item.reorder_priority} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {sorted.length > 12 && (
          <button
            type="button"
            onClick={() => setShowAll((previous) => !previous)}
            className="text-xs font-medium mt-3 cursor-pointer underline underline-offset-2"
            style={{ color: 'var(--accent-blue)' }}
          >
            {showAll ? 'Show top 12 only' : `Show all ${sorted.length} items`}
          </button>
        )}
      </div>
    </section>
  )
}

function Th({ children, align = 'right', title }) {
  return (
    <th
      scope="col"
      title={title}
      className={`py-2 px-2 font-semibold whitespace-nowrap text-${align}`}
      style={{ color: 'var(--text-secondary)' }}
    >
      {children}
    </th>
  )
}

function Td({ children, mono = false }) {
  return (
    <td
      className={`text-right py-2 px-2 whitespace-nowrap ${mono ? 'font-mono' : ''}`}
      style={{ color: 'var(--text-secondary)' }}
    >
      {children}
    </td>
  )
}

/** A/B/C class as a labelled badge — the letter plus colour, never colour alone. */
function ClassBadge({ value }) {
  const colours = {
    A: 'var(--accent-green)',
    B: 'var(--accent-blue)',
    C: 'var(--text-muted)',
  }
  return (
    <span
      className="inline-block text-[11px] font-bold rounded px-1.5 py-0.5"
      style={{ color: colours[value], border: `1px solid ${colours[value]}` }}
    >
      {value}
    </span>
  )
}

/** Trend factor as an arrow + word, so the direction reads without colour. */
function TrendBadge({ factor }) {
  const rising = factor > 1.15
  const falling = factor < 0.85
  const colour = rising ? 'var(--accent-green)' : falling ? 'var(--accent-red)' : 'var(--text-muted)'

  return (
    <span className="inline-flex items-center gap-1 text-[11px]" style={{ color: colour }}>
      <Icon name={falling ? 'trendDown' : 'trendUp'} className="w-3.5 h-3.5" />
      {factor.toFixed(2)}×
    </span>
  )
}

/** Priority as a bar plus its number — the bar alone would be unreadable. */
function PriorityBar({ value }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden="true"
        className="inline-block rounded-full"
        style={{ width: 44, height: 5, background: 'var(--bg-skeleton)' }}
      >
        <span
          className="block h-full rounded-full"
          style={{ width: `${Math.min(value, 100)}%`, background: 'var(--accent-blue)' }}
        />
      </span>
      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
        {value.toFixed(0)}
      </span>
    </span>
  )
}
