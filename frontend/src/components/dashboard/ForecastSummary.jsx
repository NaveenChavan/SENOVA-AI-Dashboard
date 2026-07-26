import Icon from '../common/Icon'
import { formatCurrency, formatCurrencyCompact } from '../charts/chartFormat'

/**
 * Feature 2 — the forecast strip above the trend chart.
 *
 * One row, one card height, four facts: expected revenue, the likely range, the
 * trend, and how accurate the model was on a holdout. Deliberate choices:
 *
 * - the **range** gets equal billing with the point estimate, because a single
 *   number implies certainty the model doesn't have;
 * - the backtested accuracy (100 − MAPE over a 7-day holdout) is stated, so the
 *   user can judge how much to trust the line;
 * - when history is too short the component renders the server's refusal
 *   verbatim instead of an empty chart or a fabricated projection.
 */

export const HORIZONS = [7, 14, 30]

export default function ForecastSummary({ forecast, loading, horizon, onHorizonChange }) {
  if (loading && !forecast) {
    return (
      <div className="card card-pad" style={{ height: 64 }}>
        <div className="skeleton h-2.5 w-28 mb-2.5" />
        <div className="skeleton h-3.5 w-40" />
      </div>
    )
  }

  if (!forecast) return null

  // Honest refusal path: not enough history to project.
  if (!forecast.available) {
    return (
      <p className="note" role="note">
        <Icon name="clock" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--text-muted)' }} />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>Forecast not available yet. </strong>
          {forecast.reason}
        </span>
      </p>
    )
  }

  const direction =
    forecast.trend_direction === 'rising'
      ? { icon: 'trendUp', colour: 'var(--accent-green)', word: 'Rising' }
      : forecast.trend_direction === 'falling'
        ? { icon: 'trendDown', colour: 'var(--accent-red)', word: 'Falling' }
        : { icon: 'refresh', colour: 'var(--text-muted)', word: 'Flat' }

  return (
    <div className="card card-pad flex flex-wrap items-center gap-x-6 gap-y-3 justify-between">
      <Fact label={`Expected · next ${forecast.horizon_days}d`}>
        <span className="text-base font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
          {formatCurrencyCompact(forecast.expected_revenue)}
        </span>
        <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
          {formatCurrency(forecast.expected_revenue)}
        </span>
      </Fact>

      <Fact label="Likely range (80%)">
        <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text-secondary)' }}>
          {formatCurrencyCompact(forecast.expected_revenue_lower)} –{' '}
          {formatCurrencyCompact(forecast.expected_revenue_upper)}
        </span>
      </Fact>

      <Fact label="Trend">
        <span className="text-xs font-semibold inline-flex items-center gap-1" style={{ color: direction.colour }}>
          <Icon name={direction.icon} className="w-3.5 h-3.5" />
          {direction.word}
        </span>
        <span className="text-[12px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {formatCurrency(forecast.trend_per_day)}/day
        </span>
      </Fact>

      <Fact label="Model check">
        {forecast.accuracy_pct != null ? (
          <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
            {forecast.accuracy_pct}% accurate
          </span>
        ) : (
          <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
            Not tested
          </span>
        )}
        {/* What the figure scores matters as much as the figure: on a shop that
            trades some days, per-day error is dominated by which days were open,
            so the backtest scores the 7-day total instead. */}
        <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
          {forecast.accuracy_pct == null
            ? 'needs 3+ weeks'
            : forecast.accuracy_basis === 'total'
              ? 'on the last 7-day total'
              : 'per day, last 7 days'}
        </span>
      </Fact>

      {forecast.trading_days > 0 && forecast.trading_days < forecast.history_days && (
        <Fact label="Trading days">
          <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
            {forecast.trading_days} / {forecast.history_days}
          </span>
          <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
            days had sales
          </span>
        </Fact>
      )}

      <div className="flex flex-col items-start lg:items-end gap-1.5">
        <div className="seg" role="group" aria-label="Forecast horizon">
          {HORIZONS.map((option) => (
            <button
              key={option}
              type="button"
              className="seg__btn"
              onClick={() => onHorizonChange?.(option)}
              aria-pressed={horizon === option}
            >
              {option}d
            </button>
          ))}
        </div>

        {/* Any caveat the model itself reported — short history, or a shop that
            only trades some days. Shown, not hidden: it changes how the numbers
            above should be read. */}
        {forecast.reason && (
          <p className="text-[12px] max-w-sm lg:text-right" style={{ color: 'var(--text-muted)' }}>
            {forecast.reason}
          </p>
        )}
      </div>
    </div>
  )
}

/** One labelled fact in the strip — label above, value(s) below, tight. */
function Fact({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>
        {label}
      </p>
      <div className="flex flex-col leading-tight">{children}</div>
    </div>
  )
}
