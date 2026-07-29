import { motion } from 'motion/react'

import Icon from '../common/Icon'
import { formatCurrency, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * Feature 1 — the AI insight cards.
 *
 * Each card is a finding the backend computed statistically (robust z-score
 * anomalies, period-over-period movers, margin leaks, Pareto concentration,
 * weekday patterns, dead stock) and wrote as a sentence from a template. No
 * language model is involved, so the numbers in the text are the numbers in the
 * data — and the raw figures ride along in `metrics` so this component formats
 * them for Indian currency conventions itself.
 *
 * Layout: compact three-across on a laptop, four on a very wide screen, one on
 * a phone. Each card is capped in height by its own content — title, two lines
 * of explanation, key figures, action — so the row never becomes a wall of text.
 *
 * Severity is carried by an icon *and* a word, not just a colour, so the
 * meaning survives greyscale printing and colour-blindness.
 */

const SEVERITY = {
  critical: { word: 'Urgent', icon: 'alert', colour: 'var(--accent-red)' },
  warning: { word: 'Watch', icon: 'info', colour: 'var(--accent-amber)' },
  positive: { word: 'Good', icon: 'trendUp', colour: 'var(--accent-green)' },
  neutral: { word: 'Note', icon: 'spark', colour: 'var(--accent-blue)' },
}

export default function InsightCards({ insights, loading }) {
  if (loading && !insights) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 3xl:grid-cols-4 gap-[var(--gap)]">
        {[...Array(3)].map((_, index) => (
          <div key={index} className="card card-pad" style={{ height: 104 }}>
            <div className="skeleton h-2.5 w-24 mb-2.5" />
            <div className="skeleton h-2.5 w-full mb-1.5" />
            <div className="skeleton h-2.5 w-4/5" />
          </div>
        ))}
      </div>
    )
  }

  if (!insights) return null

  // Nothing found is a legitimate answer for a small file — say so in one line
  // rather than showing an empty strip.
  if (!insights.insights?.length) {
    return (
      <p className="note" data-tone="info">
        <Icon name="spark" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--accent-blue)' }} />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>No findings for this period. </strong>
          {insights.note ??
            'Widen the date range or clear a filter — there is not enough data here to detect a pattern.'}
        </span>
      </p>
    )
  }

  return (
    <section aria-label="Automated insights" className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="flex items-center gap-1.5 text-sm">
          <Icon name="spark" className="w-3.5 h-3.5" style={{ color: 'var(--accent-blue)' }} />
          What changed
        </h2>
        <p className="panel-hint">{insights.analysed_days} day(s) analysed</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 3xl:grid-cols-4 gap-[var(--gap)] items-start">
        {insights.insights.map((insight, i) => (
          <InsightCard key={insight.id} insight={insight} index={i} />
        ))}
      </div>

      {insights.note && <p className="panel-hint">{insights.note}</p>}
    </section>
  )
}

function InsightCard({ insight, index = 0 }) {
  const severity = SEVERITY[insight.severity] ?? SEVERITY.neutral
  const glow = insight.severity === 'critical' || insight.severity === 'positive'

  return (
    <motion.article
      className="card card-pad flex flex-col gap-1.5"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
      style={{
        borderLeft: `3px solid ${severity.colour}`,
        boxShadow: glow ? `var(--shadow-low), inset 0 0 0 1px ${severity.colour}1a` : undefined,
      }}
    >
      <header className="flex items-start gap-1.5">
        <Icon name={severity.icon} className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color: severity.colour }} />
        <div className="min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: severity.colour }}>
            {severity.word}
          </span>
          <h3 className="text-[13px] leading-snug">{insight.title}</h3>
        </div>
      </header>

      <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {insight.message}
      </p>

      <KeyFigures insight={insight} />

      {insight.action && (
        <p
          className="text-[12px] mt-auto pt-1.5 flex items-start gap-1.5"
          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
        >
          <Icon name="check" className="w-3 h-3 shrink-0 mt-0.5" />
          <span>{insight.action}</span>
        </p>
      )}
    </motion.article>
  )
}

/**
 * The two or three figures worth showing as data rather than prose, chosen per
 * insight family. Formatted here so amounts follow Indian conventions
 * (₹1,24,500 / ₹2.35L) rather than whatever the server stringified.
 */
function KeyFigures({ insight }) {
  const metrics = insight.metrics ?? {}
  const figures = []

  if (insight.kind === 'anomaly') {
    figures.push(['That day', formatCurrency(metrics.value)])
    figures.push(['Normal', formatCurrency(metrics.normal_level)])
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
    figures.push(['Best day', formatCurrency(metrics.best_average)])
    figures.push(['Worst day', formatCurrency(metrics.worst_average)])
  } else if (insight.kind === 'deadstock') {
    figures.push(['Items idle', formatNumber(metrics.item_count)])
    figures.push(['Longest', `${formatNumber(metrics.max_days_idle)}d`])
  }

  if (!figures.length) return null

  return (
    <dl className="flex flex-wrap gap-x-3.5 gap-y-1">
      {figures.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            {label}
          </dt>
          <dd className="text-[12.5px] font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  )
}
