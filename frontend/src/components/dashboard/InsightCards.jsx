import Icon from '../common/Icon'
import { formatCurrency, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * Feature 1 — the AI insight cards.
 *
 * Each card is a finding the backend computed statistically (robust z-score
 * anomalies, period-over-period movers, margin leaks, Pareto concentration,
 * weekday patterns, dead stock) and wrote as a sentence from a template. No
 * language model is involved, so the numbers in the text are the numbers in the
 * data — and the raw figures ride along in ``metrics`` so this component
 * formats them itself for Indian currency conventions.
 *
 * Severity is carried by an icon *and* a word, not just a colour, so the
 * meaning survives greyscale printing and colour-blindness.
 */

const SEVERITY = {
  critical: { word: 'Urgent', icon: 'alert', colour: 'var(--accent-red)' },
  warning: { word: 'Watch', icon: 'info', colour: 'var(--accent-amber)' },
  positive: { word: 'Good news', icon: 'trendUp', colour: 'var(--accent-green)' },
  neutral: { word: 'Note', icon: 'spark', colour: 'var(--accent-blue)' },
}

export default function InsightCards({ insights, loading }) {
  if (loading && !insights) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
        {[...Array(3)].map((_, index) => (
          <div key={index} className="card p-4 animate-pulse" style={{ minHeight: 132 }}>
            <div className="h-3 w-24 rounded mb-3" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-3 w-full rounded mb-2" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-3 w-4/5 rounded" style={{ background: 'var(--bg-skeleton)' }} />
          </div>
        ))}
      </div>
    )
  }

  if (!insights) return null

  // Nothing found is a legitimate answer for a small file — say so plainly
  // instead of showing an empty strip.
  if (!insights.insights?.length) {
    return (
      <div className="card p-4 flex items-start gap-3">
        <Icon name="spark" className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} />
        <div>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            No findings for this period
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            {insights.note ??
              'Widen the date range or clear a filter — there is not enough data here to detect a pattern.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <section aria-label="Automated insights" className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Icon name="spark" className="w-4 h-4" style={{ color: 'var(--accent-blue)' }} />
          What changed
        </h2>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {insights.analysed_days} day(s) analysed
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
        {insights.insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} />
        ))}
      </div>

      {insights.note && (
        <p className="text-xs pt-1" style={{ color: 'var(--text-muted)' }}>
          {insights.note}
        </p>
      )}
    </section>
  )
}

function InsightCard({ insight }) {
  const severity = SEVERITY[insight.severity] ?? SEVERITY.neutral

  return (
    <article
      className="card p-4 flex flex-col gap-2"
      style={{ borderLeft: `3px solid ${severity.colour}` }}
    >
      <header className="flex items-start gap-2">
        <Icon name={severity.icon} className="w-4 h-4 shrink-0 mt-0.5" style={{ color: severity.colour }} />
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: severity.colour }}>
            {severity.word}
          </p>
          <h3 className="text-sm font-semibold leading-snug" style={{ color: 'var(--text-primary)' }}>
            {insight.title}
          </h3>
        </div>
      </header>

      <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {insight.message}
      </p>

      <KeyFigures insight={insight} />

      {insight.action && (
        <p className="text-xs mt-auto pt-2 flex items-start gap-1.5" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
          <Icon name="check" className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{insight.action}</span>
        </p>
      )}
    </article>
  )
}

/**
 * The two or three figures worth showing as data rather than prose, chosen per
 * insight family. Formatting happens here so amounts follow Indian conventions
 * (₹1,24,500 / ₹2.35L) rather than whatever the server stringified.
 */
function KeyFigures({ insight }) {
  const metrics = insight.metrics ?? {}
  const figures = []

  if (insight.kind === 'anomaly') {
    figures.push(['That day', formatCurrency(metrics.value)])
    figures.push(['Normal day', formatCurrency(metrics.normal_level)])
  } else if (insight.kind === 'mover') {
    figures.push(['Now', formatCurrency(metrics.current)])
    figures.push(['Before', formatCurrency(metrics.previous)])
    figures.push(['Change', formatPercent(metrics.change_pct, 0)])
  } else if (insight.kind === 'margin') {
    figures.push(['Revenue', formatCurrency(metrics.revenue)])
    figures.push(['Profit', formatCurrency(metrics.profit)])
    figures.push(['Margin', formatPercent(metrics.margin_pct)])
  } else if (insight.kind === 'concentration') {
    figures.push(['Key items', formatNumber(metrics.top_items)])
    figures.push(['Of total', formatNumber(metrics.total_items)])
  } else if (insight.kind === 'timing') {
    figures.push(['Best day avg', formatCurrency(metrics.best_average)])
    figures.push(['Worst day avg', formatCurrency(metrics.worst_average)])
  } else if (insight.kind === 'deadstock') {
    figures.push(['Items idle', formatNumber(metrics.item_count)])
    figures.push(['Longest idle', `${formatNumber(metrics.max_days_idle)} days`])
  }

  if (!figures.length) return null

  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1">
      {figures.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            {label}
          </dt>
          <dd className="text-xs font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  )
}
