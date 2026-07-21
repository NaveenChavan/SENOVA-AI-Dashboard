function TrendBadge({ direction }) {
  if (!direction) return null
  const isUp = direction === 'up'
  return (
    <span
      className="text-xs font-semibold px-1.5 py-0.5 rounded-full"
      style={
        isUp
          ? { background: 'rgba(16,185,129,0.12)', color: '#10b981' }
          : { background: 'rgba(239,68,68,0.12)', color: '#f87171' }
      }
      aria-label={isUp ? 'Trending up' : 'Trending down'}
    >
      {isUp ? '▲' : '▼'}
    </span>
  )
}

export default function SummaryStats({ summary }) {
  if (!summary) return null
  const fmt = (n) => (n != null ? Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—')

  const rev = summary.revenue?.value ?? 0
  const profit = summary.profit?.value ?? 0
  const cost = summary.cost?.value ?? 0
  const units = summary.units_sold?.value ?? 0
  const unique = summary.unique_items_sold?.value ?? 0
  const margin = rev > 0 ? ((profit / rev) * 100).toFixed(1) : null

  // Trend direction driven by the actual server-computed trend_percentage,
  // not a hardcoded assumption — a metric that's down should show ▼.
  const trendDirection = (metric) => {
    const pct = metric?.trend_percentage
    if (pct == null || pct === 0) return null
    return pct > 0 ? 'up' : 'down'
  }

  const tiles = [
    {
      label: 'Total Revenue',
      value: `₹${fmt(rev)}`,
      color: 'var(--accent-blue)',
      sub: margin ? `${margin}% margin` : null,
      trend: trendDirection(summary.revenue),
    },
    {
      label: 'Total Profit',
      value: `₹${fmt(profit)}`,
      color: 'var(--accent-green)',
      sub: rev > 0 ? `${margin}% of revenue` : null,
      trend: trendDirection(summary.profit),
    },
    {
      label: 'Total Cost',
      value: `₹${fmt(cost)}`,
      color: 'var(--text-secondary)',
      sub: null,
      trend: trendDirection(summary.cost),
    },
    {
      label: 'Units Sold',
      value: Number(units).toLocaleString('en-IN'),
      color: 'var(--accent-purple)',
      sub: `${unique} unique SKU${unique === 1 ? '' : 's'}`,
      trend: trendDirection(summary.units_sold),
    },
    {
      label: 'Unique Items',
      value: Number(unique),
      color: 'var(--accent-amber)',
      sub: null,
      trend: null,
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 3xl:grid-cols-5 gap-3 sm:gap-4">
      {tiles.map((t) => (
        <div key={t.label} className="stat-tile">
          <div className="flex items-start justify-between mb-2 sm:mb-3">
            <span
              className="text-[0.65rem] sm:text-xs uppercase tracking-widest font-medium"
              style={{ color: 'var(--text-muted)' }}
            >
              {t.label}
            </span>
            <TrendBadge direction={t.trend} />
          </div>
          <p className="text-lg sm:text-xl font-bold glow-blue-text" style={{ color: t.color, lineHeight: 1.2 }}>
            {t.value}
          </p>
          {t.sub && (
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              {t.sub}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
