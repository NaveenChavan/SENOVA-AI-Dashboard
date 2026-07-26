import Icon from '../common/Icon'
import { formatCurrency } from '../charts/chartFormat'

/**
 * Feature 2 — the forecast summary strip that sits above the trend chart.
 *
 * Deliberate choices:
 * - the **range** is given as much prominence as the point estimate, because a
 *   single number implies a certainty the model doesn't have;
 * - the backtested accuracy (100 − MAPE over a 7-day holdout) is shown as a
 *   badge, so the user can judge how much to trust the line;
 * - when history is too short the component renders the server's refusal
 *   verbatim instead of an empty chart or a fabricated projection.
 */

/** Horizon options the backend supports (capped at 90 days server-side). */
export const HORIZONS = [7, 14, 30]

export default function ForecastSummary({ forecast, loading, horizon, onHorizonChange }) {
  if (loading && !forecast) {
    return (
      <div className="card p-4 animate-pulse" style={{ minHeight: 88 }}>
        <div className="h-3 w-32 rounded mb-3" style={{ background: 'var(--bg-skeleton)' }} />
        <div className="h-5 w-48 rounded" style={{ background: 'var(--bg-skeleton)' }} />
      </div>
    )
  }

  if (!forecast) return null

  // Honest refusal path: not enough history to project.
  if (!forecast.available) {
    return (
      <div className="card p-4 flex items-start gap-3">
        <Icon name="clock" className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--text-muted)' }} />
        <div>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            Forecast not available yet
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            {forecast.reason}
          </p>
        </div>
      </div>
    )
  }

  const direction =
    forecast.trend_direction === 'rising'
      ? { icon: 'trendUp', colour: 'var(--accent-green)', word: 'Rising' }
      : forecast.trend_direction === 'falling'
        ? { icon: 'trendDown', colour: 'var(--accent-red)', word: 'Falling' }
        : { icon: 'refresh', colour: 'var(--text-muted)', word: 'Flat' }

  return (
    <div className="card p-4 flex flex-col lg:flex-row lg:items-center gap-4 justify-between">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            Expected revenue · next {forecast.horizon_days} days
          </p>
          <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
            {formatCurrency(forecast.expected_revenue)}
          </p>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Likely between {formatCurrency(forecast.expected_revenue_lower)} and{' '}
            {formatCurrency(forecast.expected_revenue_upper)}
          </p>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            Trend
          </p>
          <p className="text-sm font-semibold flex items-center gap-1.5" style={{ color: direction.colour }}>
            <Icon name={direction.icon} className="w-4 h-4" />
            {direction.word}
          </p>
          <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
            {formatCurrency(forecast.trend_per_day)} / day
          </p>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            Model check
          </p>
          {forecast.accuracy_pct != null ? (
            <p className="text-sm font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
              {forecast.accuracy_pct}% accurate
            </p>
          ) : (
            <p className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
              Not tested
            </p>
          )}
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {forecast.accuracy_pct != null
              ? 'measured on the last 7 days'
              : 'needs 3+ weeks of history'}
          </p>
        </div>
      </div>

      <div className="flex flex-col items-start lg:items-end gap-2">
        <div
          role="group"
          aria-label="Forecast horizon"
          className="flex items-center gap-1 p-1 rounded-xl"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}
        >
          {HORIZONS.map((option) => {
            const active = horizon === option
            return (
              <button
                key={option}
                type="button"
                onClick={() => onHorizonChange?.(option)}
                aria-pressed={active}
                className="text-xs font-medium rounded-lg cursor-pointer transition-colors"
                style={{
                  padding: '8px 12px',
                  minHeight: 36,
                  background: active
                    ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                    : 'transparent',
                  color: active ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                }}
              >
                {option}d
              </button>
            )
          })}
        </div>
        {!forecast.seasonality_applied && forecast.reason && (
          <p className="text-[11px] max-w-xs lg:text-right" style={{ color: 'var(--text-muted)' }}>
            {forecast.reason}
          </p>
        )}
      </div>
    </div>
  )
}
