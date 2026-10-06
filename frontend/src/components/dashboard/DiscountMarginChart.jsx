import { Bar, BarChart as ReBar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from 'recharts'
import Card from '../common/Card'
import ErrorBoundary from '../common/ErrorBoundary'
import { SimpleTooltip } from '../charts/ChartTooltip'
import { formatPercent, truncateLabel } from '../charts/chartFormat'
import useChartTheme from '../charts/useChartTheme'

/**
 * Compares discount percentage against margin percentage.
 */
export default function DiscountMarginChart({ data, metrics }) {
  const theme = useChartTheme()

  if (!data || data.length === 0) return null

  // The excluded rows note 
  const excluded = metrics ? metrics.missing_mrp_rows + metrics.price_above_mrp_rows : 0
  const hint = excluded > 0 
    ? `Excluded ${excluded} rows (missing or invalid MRP)` 
    : 'Discount % vs Profit Margin %'

  return (
    <Card title="Discount vs Margin" hint={hint}>
      <ErrorBoundary>
        <div className="chart-box">
          <ResponsiveContainer width="100%" height="100%">
            <ReBar data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.3} />
              <XAxis
                dataKey="item"
                tickFormatter={(value) => truncateLabel(value, 10)}
                tick={{ fontSize: 12, fill: theme.textSecondary }}
                axisLine={{ stroke: theme.borderStrong }}
              />
              <YAxis
                tickFormatter={(value) => formatPercent(value)}
                tick={{ fontSize: 12, fill: theme.textSecondary }}
                axisLine={{ stroke: theme.borderStrong }}
              />
              <Tooltip
                content={<SimpleTooltip measureFormat="percent" />}
                cursor={{ fill: theme.borderSubtle }}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
              <Bar
                name="Discount %"
                dataKey="discount_pct"
                fill={theme.accentRed}
                radius={[4, 4, 0, 0]}
                maxBarSize={32}
                isAnimationActive={false}
              />
              <Bar
                name="Margin %"
                dataKey="margin_pct"
                fill={theme.accentBlue}
                radius={[4, 4, 0, 0]}
                maxBarSize={32}
                isAnimationActive={false}
              />
            </ReBar>
          </ResponsiveContainer>
        </div>
      </ErrorBoundary>
    </Card>
  )
}
