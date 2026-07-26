import { Bar, BarChart as ReBar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { SimpleTooltip } from './ChartTooltip'
import { formatNumber, truncateLabel } from './chartFormat'
import useChartTheme from './useChartTheme'

/**
 * Small single-series bar chart used by the "Top items" panel.
 *
 * Distinct from the chart studio's BarView: this one plots a plain
 * `[{ name, quantity, revenue }]` list (the summary payload's `top_items`)
 * rather than the studio's fully-measured ChartPoint objects, so it stays a
 * separate, tiny component instead of adding branches to the studio.
 *
 * Tooltip and number formatting come from the shared modules so a change to
 * currency/label formatting lands here too.
 */
export default function BarChart({ data, dataKey = 'revenue', color, valueFormat = 'number' }) {
  const theme = useChartTheme()
  const barColor = color || theme.accentGreen

  return (
    <div className="h-56 sm:h-64 md:h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ReBar data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.3} />
          <XAxis
            dataKey="name"
            tickFormatter={(value) => truncateLabel(value, 10)}
            tick={{ fontSize: 12, fill: theme.textSecondary }}
            axisLine={{ stroke: theme.borderStrong }}
          />
          <YAxis
            tickFormatter={(value) => formatNumber(value)}
            tick={{ fontSize: 12, fill: theme.textSecondary }}
            axisLine={{ stroke: theme.borderStrong }}
          />
          <Tooltip
            content={<SimpleTooltip measureFormat={valueFormat} />}
            cursor={{ fill: theme.borderSubtle }}
          />
          {/* Animation off to match the rest of the dashboard: the chart
              re-renders on every filter change, where a sweep is noise. */}
          <Bar
            dataKey={dataKey}
            fill={barColor}
            radius={[4, 4, 0, 0]}
            maxBarSize={48}
            isAnimationActive={false}
          />
        </ReBar>
      </ResponsiveContainer>
    </div>
  )
}
