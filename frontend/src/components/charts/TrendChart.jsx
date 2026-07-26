import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ChartLegend, TrendTooltip } from './ChartTooltip'
import { formatCurrencyCompact, formatShortDate } from './chartFormat'
import useChartTheme from './useChartTheme'

/**
 * Daily revenue/profit trend, with the forecast drawn as a continuation of the
 * same line and anomalous days marked.
 *
 * The visual language follows the forecasting guidance exactly:
 * - **actual** revenue is a solid line;
 * - **forecast** is a dashed line in a different hue, so it can never be
 *   mistaken for recorded history;
 * - the 80% confidence band is a shaded ribbon behind it, because the range is
 *   the honest answer — the single line is not;
 * - a vertical rule marks "today" (the last real data point);
 * - anomalous days get a red ring plus a text alert in the tooltip, since a
 *   colour on its own is not an accessible signal.
 */
export default function TrendChart({ trend = [], forecast = null, anomalyDates = [] }) {
  const theme = useChartTheme()

  // One row per date: actuals from the trend payload, projection from the
  // forecast payload. Merging here (instead of on the server) keeps the two
  // endpoints independent — the chart still renders if the forecast is absent.
  const series = useMemo(() => {
    const byDate = new Map()

    for (const point of trend) {
      byDate.set(point.date, {
        date: point.date,
        revenue: point.revenue,
        profit: point.profit,
      })
    }

    if (forecast?.available) {
      for (const point of forecast.points) {
        const existing = byDate.get(point.date) ?? { date: point.date }
        byDate.set(point.date, {
          ...existing,
          forecast: point.forecast,
          // Recharts draws a ribbon when a dataKey resolves to [min, max].
          band: point.is_future && point.lower != null ? [point.lower, point.upper] : undefined,
        })
      }
    }

    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
  }, [trend, forecast])

  const lastActualDate = trend.length ? trend[trend.length - 1].date : null
  const anomalySet = useMemo(() => new Set(anomalyDates), [anomalyDates])

  if (!series.length) {
    return (
      <p className="text-sm py-16 text-center" style={{ color: 'var(--text-muted)' }}>
        No dated transactions in this period.
      </p>
    )
  }

  return (
    <div className="h-64 sm:h-72 md:h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.4} />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            tick={{ fontSize: 11, fill: theme.textSecondary }}
            axisLine={{ stroke: theme.borderStrong }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            tickFormatter={formatCurrencyCompact}
            tick={{ fontSize: 11, fill: theme.textSecondary }}
            axisLine={{ stroke: theme.borderStrong }}
          />
          <Tooltip content={<TrendTooltip anomalyDates={anomalyDates} />} />
          <Legend content={<ChartLegend dashedKeys={['Forecast']} />} />

          {/* Confidence band first so it sits behind every line. */}
          {forecast?.available && (
            <Area
              type="monotone"
              dataKey="band"
              name="Likely range (80%)"
              stroke="none"
              fill={theme.forecast}
              fillOpacity={0.16}
              connectNulls
              isAnimationActive={false}
            />
          )}

          <Line
            type="monotone"
            dataKey="revenue"
            name="Revenue"
            stroke={theme.actual}
            strokeWidth={2.5}
            dot={<AnomalyDot anomalies={anomalySet} colour={theme.anomaly} />}
            activeDot={{ r: 5, fill: theme.actual, stroke: theme.bgPrimary, strokeWidth: 2 }}
            connectNulls={false}
            // Animation off: on a dashboard the line redraws on every filter
            // change, where a 1.5s sweep is decoration rather than meaning —
            // and it would delay the anomaly markers from appearing.
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="profit"
            name="Profit"
            stroke={theme.accentGreen}
            strokeWidth={2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />

          {forecast?.available && (
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast"
              stroke={theme.forecast}
              strokeWidth={2.5}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          )}

          {/* Where recorded history ends and projection begins. */}
          {forecast?.available && lastActualDate && (
            <ReferenceLine
              x={lastActualDate}
              stroke={theme.textMuted}
              strokeDasharray="3 3"
              label={{ value: 'today', position: 'insideTopRight', fill: theme.textMuted, fontSize: 10 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Dot renderer for the revenue line: invisible on ordinary days, a hollow red
 * ring on days the anomaly detector flagged. Marking the outlier on the chart
 * is what turns the insight card into something the user can actually locate.
 */
function AnomalyDot({ cx, cy, payload, anomalies, colour }) {
  if (cx == null || cy == null || !anomalies.has(payload?.date)) return null
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill="none"
      stroke={colour}
      strokeWidth={2.5}
      role="img"
      aria-label={`Unusual revenue on ${payload.date}`}
    />
  )
}
