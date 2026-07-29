import { useState } from 'react'
import { motion } from 'motion/react'

import Card from '../common/Card'
import Icon from '../common/Icon'
import { formatCurrency, formatCurrencyCompact, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * Feature 3 — inventory & reorder intelligence.
 *
 * Two modes, never blurred together:
 * - **Demand mode** (a plain sales register): velocity, trend, ABC class,
 *   ageing and a reorder-priority score.
 * - **Stock-aware mode** (a stock column was mapped): the same plus real
 *   days-of-cover, reorder alerts and capital locked per item.
 *
 * When stock is unknown those columns are simply absent and a one-line note
 * explains how to unlock them — a guessed days-of-cover would be worse than
 * none, because it would drive a purchase from a number nobody measured.
 *
 * Layout: four summary tiles on one row, ageing counts on the next, then the
 * table scrolling inside a capped height so the page length stays predictable.
 */

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
      <div className="space-y-3">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-[var(--gap)]">
          {[...Array(4)].map((_, index) => (
            <div key={index} className="stat-tile" style={{ height: 76 }}>
              <div className="skeleton h-2 w-20 mb-2.5" />
              <div className="skeleton h-4 w-16" />
            </div>
          ))}
        </div>
        <div className="card card-pad">
          <div className="skeleton h-40 w-full" />
        </div>
      </div>
    )
  }

  if (!inventory?.items?.length) {
    return (
      <div className="card card-pad text-center py-10">
        <Icon name="box" className="w-7 h-7 mx-auto mb-2.5" style={{ color: 'var(--text-muted)' }} />
        <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          No stock movement in this period
        </p>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
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
  const expectedUnits = new Map((forecast?.item_forecasts ?? []).map((entry) => [entry.item, entry.expected_units]))

  return (
    <section className="space-y-3 sm:space-y-4" aria-label="Inventory intelligence">
      {/* ── ABC + capital tiles ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-[var(--gap)]">
        {inventory.abc_buckets.map((bucket, i) => (
          <motion.div
            key={bucket.label}
            className="stat-tile"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.04, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-[11px] uppercase tracking-wider font-semibold mb-1 truncate" style={{ color: 'var(--text-muted)' }}>
              {bucket.label}
            </p>
            <p className="text-base font-bold font-mono leading-none" style={{ color: 'var(--text-primary)' }}>
              {formatNumber(bucket.item_count)}
              <span className="text-[12px] font-normal"> items</span>
            </p>
            <p className="text-[12px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
              {formatCurrencyCompact(bucket.revenue)} · {formatPercent(bucket.revenue_share_pct, 0)} of revenue
            </p>
          </motion.div>
        ))}

        <motion.div
          className="stat-tile"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: inventory.abc_buckets.length * 0.04, ease: [0.16, 1, 0.3, 1] }}
        >
          <p className="text-[11px] uppercase tracking-wider font-semibold mb-1 truncate" style={{ color: 'var(--text-muted)' }}>
            {inventory.stock_aware ? 'Capital in stock' : 'Reorder candidates'}
          </p>
          <p className="text-base font-bold font-mono leading-none" style={{ color: 'var(--text-primary)' }}>
            {inventory.stock_aware
              ? formatCurrencyCompact(inventory.total_capital_locked)
              : formatNumber(inventory.items.filter((item) => item.reorder_priority >= 50).length)}
          </p>
          <p className="text-[12px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
            {inventory.stock_aware
              ? `${formatNumber(inventory.reorder_count)} below 7 days cover`
              : `Priority 50+ over ${inventory.window_days} day(s)`}
          </p>
        </motion.div>
      </div>

      {/* ── Ageing buckets ─────────────────────────────────────────────── */}
      {inventory.ageing_buckets.length > 0 && (
        <Card title="Stock ageing" hint="Days since each item last sold">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {inventory.ageing_buckets.map((bucket) => (
              <div key={bucket.label} className="min-w-0">
                <p className="text-[12px] truncate" style={{ color: 'var(--text-muted)' }}>
                  {bucket.label}
                </p>
                <p className="text-base font-bold font-mono leading-tight" style={{ color: 'var(--text-primary)' }}>
                  {formatNumber(bucket.item_count)}
                </p>
                <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>
                  {formatCurrencyCompact(bucket.revenue)}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── Reorder table ──────────────────────────────────────────────── */}
      <Card
        title="Reorder priority"
        hint={`Sales speed, trend and recency over ${inventory.window_days} day(s)`}
        action={
          <select
            className="filter-select"
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
        }
      >
        {!inventory.stock_aware && inventory.note && (
          <p className="note mb-2.5" data-tone="info" role="note">
            <Icon name="info" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--accent-blue)' }} />
            <span>{inventory.note}</span>
          </p>
        )}

        <div className="scroll-x" style={{ maxHeight: 440, overflowY: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col" title="A = first 80% of revenue, B = next 15%, C = the tail">Class</th>
                <th scope="col">Units</th>
                <th scope="col" title="Units sold per calendar day">Per day</th>
                <th scope="col" title="Late-period speed vs early-period speed">Trend</th>
                <th scope="col">Idle</th>
                {inventory.stock_aware && <th scope="col">Stock</th>}
                {inventory.stock_aware && <th scope="col" title="Stock ÷ daily sales speed">Cover</th>}
                <th scope="col" title="Expected units over the forecast horizon">Next</th>
                <th scope="col">Priority</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.item}>
                  <th scope="row">
                    <span className="block truncate" style={{ maxWidth: 200 }} title={item.item}>
                      {item.item}
                    </span>
                    <span className="block text-[11px] font-normal truncate" style={{ color: 'var(--text-muted)', maxWidth: 200 }}>
                      {item.category} · {formatCurrency(item.revenue)} · {formatPercent(item.margin_pct)}
                    </span>
                  </th>
                  <td>
                    <ClassBadge value={item.abc_class} />
                  </td>
                  <td className="font-mono">{formatNumber(item.units_sold)}</td>
                  <td className="font-mono">{item.velocity_per_day.toFixed(2)}</td>
                  <td>
                    <TrendBadge factor={item.trend_factor} />
                  </td>
                  <td className="font-mono">{formatNumber(item.days_since_last_sale)}d</td>
                  {inventory.stock_aware && <td className="font-mono">{formatNumber(item.stock_on_hand)}</td>}
                  {inventory.stock_aware && (
                    <td className="font-mono" style={{ color: item.reorder_flag ? 'var(--accent-red)' : undefined }}>
                      {item.days_of_cover == null ? '—' : `${item.days_of_cover.toFixed(1)}d`}
                    </td>
                  )}
                  <td className="font-mono">
                    {expectedUnits.has(item.item) ? formatNumber(expectedUnits.get(item.item), 0) : '—'}
                  </td>
                  <td>
                    <PriorityBar value={item.reorder_priority} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {sorted.length > 12 && (
          <button
            type="button"
            onClick={() => setShowAll((previous) => !previous)}
            className="text-[12px] font-medium mt-2 cursor-pointer underline underline-offset-2"
            style={{ color: 'var(--accent-blue)' }}
          >
            {showAll ? 'Show top 12 only' : `Show all ${sorted.length} items`}
          </button>
        )}
      </Card>
    </section>
  )
}

/** A/B/C class as a filled pill — the letter carries the meaning, the colour reinforces it. */
function ClassBadge({ value }) {
  const colours = { A: 'var(--accent-green)', B: 'var(--accent-blue)', C: 'var(--text-muted)' }
  const colour = colours[value]
  return (
    <span
      className="inline-flex items-center justify-center text-[11px] font-bold rounded-md"
      style={{ width: 20, height: 20, color: colour, background: `${colour}1a`, border: `1px solid ${colour}40` }}
    >
      {value}
    </span>
  )
}

/** Trend factor as an arrow + number, so direction reads without colour. */
function TrendBadge({ factor }) {
  const rising = factor > 1.15
  const falling = factor < 0.85
  const colour = rising ? 'var(--accent-green)' : falling ? 'var(--accent-red)' : 'var(--text-muted)'

  return (
    <span className="inline-flex items-center gap-0.5 text-[12px] font-mono" style={{ color: colour }}>
      <Icon name={falling ? 'trendDown' : 'trendUp'} className="w-3 h-3" strokeWidth={2.2} />
      {factor.toFixed(2)}×
    </span>
  )
}

/** Priority as a gradient bar plus its number — the bar alone would be unreadable. */
function PriorityBar({ value }) {
  const high = value >= 70
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="inline-block rounded-full"
        style={{ width: 36, height: 4, background: 'var(--bg-skeleton)' }}
      >
        <span
          className="block h-full rounded-full"
          style={{
            width: `${Math.min(value, 100)}%`,
            background: high ? 'var(--gradient-accent)' : 'var(--accent-blue)',
          }}
        />
      </span>
      <span className="font-mono text-[12px]" style={{ color: 'var(--text-primary)' }}>
        {value.toFixed(0)}
      </span>
    </span>
  )
}
