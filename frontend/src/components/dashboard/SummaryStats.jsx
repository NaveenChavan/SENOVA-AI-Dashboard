import { motion } from 'motion/react'

import Icon from '../common/Icon'
import { formatCurrency, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * The KPI row — five compact tiles on one line at desktop, two per row on a
 * phone.
 *
 * Sizing is deliberate: amounts use the compact ₹1.8L form so a tile never has
 * to grow to fit a nine-digit number, and the tile itself has no hover
 * translate, because shifting tiles make a dense row look unstable.
 *
 * Trend is shown as an arrow icon **and** the signed percentage, never colour
 * alone. The direction comes from the server-computed `trend_percentage`.
 */

function Trend({ metric }) {
  const pct = metric?.trend_percentage
  if (pct == null || pct === 0) return null

  const up = pct > 0
  return (
    <span
      className="inline-flex items-center gap-0.5 text-[12px] font-semibold shrink-0"
      style={{ color: up ? 'var(--accent-green)' : 'var(--accent-red)' }}
      title={`${up ? 'Up' : 'Down'} ${Math.abs(pct)}% vs the previous period`}
    >
      <Icon name={up ? 'trendUp' : 'trendDown'} className="w-3 h-3" strokeWidth={2.2} />
      {formatPercent(Math.abs(pct), 0)}
    </span>
  )
}

export default function SummaryStats({ summary }) {
  if (!summary) return null

  const revenue = summary.revenue?.value ?? 0
  const profit = summary.profit?.value ?? 0
  const cost = summary.cost?.value ?? 0
  const units = summary.units_sold?.value ?? 0
  const unique = summary.unique_items_sold?.value ?? 0
  const margin = revenue > 0 ? (profit / revenue) * 100 : null

  const tiles = [
    {
      label: 'Revenue',
      value: formatCurrency(revenue),
      colour: 'var(--text-primary)',
      sub: margin != null ? `${formatPercent(margin, 1)} margin` : null,
      metric: summary.revenue,
    },
    {
      label: 'Profit',
      value: formatCurrency(profit),
      colour: profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)',
      sub: margin != null ? `${formatPercent(margin, 1)} of revenue` : null,
      metric: summary.profit,
    },
    {
      label: 'Cost',
      value: formatCurrency(cost),
      colour: 'var(--text-primary)',
      sub: revenue > 0 ? `${formatPercent((cost / revenue) * 100, 1)} of revenue` : null,
      metric: summary.cost,
    },
    {
      label: 'Units Sold',
      value: formatNumber(units),
      colour: 'var(--text-primary)',
      sub: `${formatNumber(unique)} unique SKU${unique === 1 ? '' : 's'}`,
      metric: summary.units_sold,
    },
    {
      label: 'Unique Items',
      value: formatNumber(unique),
      colour: 'var(--text-primary)',
      sub: units > 0 ? `${(units / Math.max(unique, 1)).toFixed(1)} units per item` : null,
      metric: null,
    },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-[var(--gap)]">
      {tiles.map((tile, i) => (
        <motion.div
          key={tile.label}
          // With an odd number of tiles the last one is left alone in a
          // half-width cell at the 2-column mobile breakpoint, which reads as
          // a broken grid. Letting it span the full row closes that gap.
          // Only needed for the 2-column case: the 3- and 5-column layouts
          // above `sm` lay 5 tiles out without a stranded cell.
          className={`stat-tile${
            tiles.length % 2 === 1 && i === tiles.length - 1 ? ' col-span-2 sm:col-span-1' : ''
          }`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: i * 0.04, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-[12px] uppercase tracking-wide font-semibold truncate" style={{ color: 'var(--text-muted)' }}>
              {tile.label}
            </span>
            <Trend metric={tile.metric} />
          </div>

          {/*
            The full figure, not an abbreviation: "₹7,20,126" is what the shop
            owner needs to read off the screen. The font size steps down as the
            number gets longer (clamp on ch width) so a 9-digit amount still
            fits the tile instead of being clipped or wrapping.
          */}
          <p
            className="font-bold font-mono leading-tight"
            style={{
              color: tile.colour,
              fontSize: `clamp(0.9rem, ${Math.max(1.35 - tile.value.length * 0.045, 0.62)}rem, 1.35rem)`,
            }}
          >
            {tile.value}
          </p>

          {tile.sub && (
            <p className="text-[12.5px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
              {tile.sub}
            </p>
          )}
        </motion.div>
      ))}
    </div>
  )
}
