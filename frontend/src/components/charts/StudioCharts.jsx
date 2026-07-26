import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'

import { ChartLegend, StudioTooltip } from './ChartTooltip'
import { formatCurrency, formatCurrencyCompact, formatNumber, formatPercent, tickFormatterFor, truncateLabel } from './chartFormat'
import useChartTheme from './useChartTheme'

/**
 * The six Recharts-based views of the chart studio. (The seventh, the heatmap,
 * is a CSS grid — see HeatmapGrid.jsx.)
 *
 * Every view consumes the *same* ChartDataResponse: the API pre-computes each
 * measure per group, so switching view never triggers a new request and the
 * views can't disagree with each other.
 *
 * Each view answers a different question, which is why the studio offers them
 * rather than picking one:
 *   BarView      how do groups compare?
 *   DonutView    what is the whole made of?
 *   ComboView    where is revenue high but margin thin?
 *   ParetoView   how concentrated is the business? (80/20)
 *   ScatterView  how do price and volume relate?
 *   TreemapView  which tiles dominate, at a glance?
 */

// Height comes from the --chart-h token (see index.css) via .chart-box, so
// 'make the charts smaller' is one edit for every view at once.
const CHART_HEIGHT = 'chart-box'

// Cap on bar thickness. Without it a full-width panel showing three groups
// renders three enormous blocks instead of a chart.
const BAR_MAX = 56

/** Shared axis/grid props so all views line up visually. */
function useAxisProps() {
  const theme = useChartTheme()
  return {
    theme,
    grid: <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.4} />,
    tick: { fontSize: 12, fill: theme.textSecondary },
    axisLine: { stroke: theme.borderStrong },
  }
}

/** Bars, optionally horizontal — the default "compare groups" view. */
export function BarView({ data, horizontal = false, onSelect }) {
  const { theme, grid, tick, axisLine } = useAxisProps()
  const formatTick = tickFormatterFor(data.measure_format)

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data.points}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 12, bottom: 4, left: horizontal ? 8 : 0 }}
          onClick={(state) => {
            // Recharts reports the clicked category on the chart itself; this
            // is what makes every bar a drill-down entry point.
            const point = state?.activePayload?.[0]?.payload
            if (point && !point.is_other) onSelect?.(point)
          }}
        >
          {grid}
          {horizontal ? (
            <>
              <XAxis type="number" tickFormatter={formatTick} tick={tick} axisLine={axisLine} />
              <YAxis
                type="category"
                dataKey="label"
                width={96}
                tickFormatter={(value) => truncateLabel(value, 12)}
                tick={tick}
                axisLine={axisLine}
              />
            </>
          ) : (
            <>
              <XAxis
                dataKey="label"
                tickFormatter={(value) => truncateLabel(value, 10)}
                tick={tick}
                axisLine={axisLine}
                interval="preserveStartEnd"
              />
              <YAxis tickFormatter={formatTick} tick={tick} axisLine={axisLine} />
            </>
          )}
          <Tooltip
            content={<StudioTooltip measureFormat={data.measure_format} />}
            cursor={{ fill: theme.borderSubtle }}
          />
          <Bar dataKey="value" name={data.measure_label} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} isAnimationActive={false} maxBarSize={BAR_MAX}>
            {data.points.map((point) => (
              // The folded "Other" bucket is muted so it never reads as a
              // real, actionable group.
              <Cell
                key={point.label}
                fill={point.is_other ? theme.textMuted : theme.accentBlue}
                cursor={point.is_other ? 'default' : 'pointer'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Donut. The guidance caps a pie at 5–6 slices, which is enforced upstream by
 * requesting top_n=6 — anything beyond that is already folded into "Other".
 *
 * Percentages are drawn *inside* the ring and the names live in the legend.
 * Outside labels were being clipped by the card at compact heights, and a
 * clipped label is worse than no label.
 */
export function DonutView({ data, onSelect }) {
  const { theme } = useAxisProps()

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <Pie
            data={data.points}
            dataKey="value"
            nameKey="label"
            innerRadius="46%"
            outerRadius="76%"
            paddingAngle={2}
            isAnimationActive={false}
            labelLine={false}
            label={<SliceLabel />}
            onClick={(slice) => {
              const point = slice?.payload?.payload ?? slice?.payload
              if (point && !point.is_other) onSelect?.(point)
            }}
          >
            {data.points.map((point, index) => (
              <Cell
                key={point.label}
                fill={point.is_other ? theme.textMuted : theme.categorical[index % theme.categorical.length]}
                stroke={theme.bgCard}
                strokeWidth={2}
                cursor={point.is_other ? 'default' : 'pointer'}
              />
            ))}
          </Pie>
          <Tooltip content={<StudioTooltip measureFormat={data.measure_format} />} />
          <Legend content={<ChartLegend />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Percentage printed in the middle of its own slice, in white, and only when
 * the slice is wide enough to hold it. Nothing can overflow the chart area,
 * which is what made the previous outside labels get cut off.
 */
function SliceLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.06) return null

  const radian = Math.PI / 180
  const radius = innerRadius + (outerRadius - innerRadius) * 0.55
  const x = cx + radius * Math.cos(-midAngle * radian)
  const y = cy + radius * Math.sin(-midAngle * radian)

  return (
    <text x={x} y={y} fill="#ffffff" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

/**
 * Combo: revenue bars against a margin-% line on a second axis. This is the
 * view that exposes "sells a lot, earns little" without any maths by the user.
 */
export function ComboView({ data, onSelect }) {
  const { theme, grid, tick, axisLine } = useAxisProps()

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data.points}
          margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
          onClick={(state) => {
            const point = state?.activePayload?.[0]?.payload
            if (point && !point.is_other) onSelect?.(point)
          }}
        >
          {grid}
          <XAxis
            dataKey="label"
            tickFormatter={(value) => truncateLabel(value, 10)}
            tick={tick}
            axisLine={axisLine}
          />
          <YAxis yAxisId="left" tickFormatter={formatCurrencyCompact} tick={tick} axisLine={axisLine} />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(value) => `${Math.round(value)}%`}
            tick={tick}
            axisLine={axisLine}
          />
          <Tooltip content={<StudioTooltip measureFormat="currency" />} cursor={{ fill: theme.borderSubtle }} />
          <Legend content={<ChartLegend />} />
          <Bar yAxisId="left" dataKey="revenue" name="Revenue" fill={theme.accentBlue} radius={[6, 6, 0, 0]} isAnimationActive={false} maxBarSize={BAR_MAX} />
          <Bar yAxisId="left" dataKey="cost" name="Cost" fill={theme.accentPurple} radius={[6, 6, 0, 0]} isAnimationActive={false} maxBarSize={BAR_MAX} />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="margin_pct"
            name="Margin %"
            stroke={theme.accentAmber}
            strokeWidth={2.5}
            dot={{ r: 3, fill: theme.accentAmber }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Pareto: bars sorted descending with the cumulative-share curve. Where the
 * curve crosses 80% is the concentration answer ("N items make most money").
 */
export function ParetoView({ data, onSelect }) {
  const { theme, grid, tick, axisLine } = useAxisProps()

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data.points}
          margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
          onClick={(state) => {
            const point = state?.activePayload?.[0]?.payload
            if (point && !point.is_other) onSelect?.(point)
          }}
        >
          {grid}
          <XAxis
            dataKey="label"
            tickFormatter={(value) => truncateLabel(value, 10)}
            tick={tick}
            axisLine={axisLine}
          />
          <YAxis
            yAxisId="left"
            tickFormatter={tickFormatterFor(data.measure_format)}
            tick={tick}
            axisLine={axisLine}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            tickFormatter={(value) => `${value}%`}
            tick={tick}
            axisLine={axisLine}
          />
          <Tooltip content={<StudioTooltip measureFormat={data.measure_format} />} cursor={{ fill: theme.borderSubtle }} />
          <Legend content={<ChartLegend />} />
          <Bar yAxisId="left" dataKey="value" name={data.measure_label} fill={theme.accentBlue} radius={[6, 6, 0, 0]} isAnimationActive={false} maxBarSize={BAR_MAX} />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="cumulative_pct"
            name="Cumulative %"
            stroke={theme.accentAmber}
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Bubble scatter: average selling price against units sold, bubble area =
 * revenue. Reveals pricing sweet spots — cheap high-volume vs dear low-volume.
 * Opacity is kept at 0.7 per the visualisation guidance so overlapping bubbles
 * still show density.
 */
export function ScatterView({ data, onSelect }) {
  const { theme, grid, tick, axisLine } = useAxisProps()
  const points = data.points.filter((point) => !point.is_other && point.avg_price != null)

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 16, bottom: 12, left: 0 }}>
          {grid}
          <XAxis
            type="number"
            dataKey="avg_price"
            name="Avg price"
            tickFormatter={formatCurrencyCompact}
            tick={tick}
            axisLine={axisLine}
            label={{ value: 'Avg selling price', position: 'insideBottom', offset: -6, fill: theme.textMuted, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="units"
            name="Units"
            tickFormatter={(value) => formatNumber(value)}
            tick={tick}
            axisLine={axisLine}
            label={{ value: 'Units sold', angle: -90, position: 'insideLeft', fill: theme.textMuted, fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="revenue" range={[60, 520]} name="Revenue" />
          <Tooltip content={<StudioTooltip measureFormat="currency" />} />
          <Scatter
            data={points}
            name="Items"
            fill={theme.accentBlue}
            fillOpacity={0.7}
            stroke={theme.accentBlueStrong}
            isAnimationActive={false}
            onClick={(node) => {
              const point = node?.payload
              if (point) onSelect?.(point)
            }}
            cursor="pointer"
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Treemap: area = share of the measure. White 2–3px borders between tiles
 * (per the guidance) keep the boundaries legible, and the value is printed
 * inside any tile large enough to hold it.
 */
export function TreemapView({ data, onSelect }) {
  const { theme } = useAxisProps()
  const tiles = data.points
    .filter((point) => point.value > 0)
    .map((point, index) => ({
      ...point,
      name: point.label,
      size: point.value,
      fill: point.is_other ? theme.textMuted : theme.categorical[index % theme.categorical.length],
    }))

  if (!tiles.length) {
    return (
      <p className="chart-box flex items-center justify-center text-xs text-center" style={{ color: 'var(--text-muted)' }}>
        A treemap needs positive values — try Revenue or Units.
      </p>
    )
  }

  return (
    <div className={`${CHART_HEIGHT}`}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={tiles}
          dataKey="size"
          nameKey="name"
          stroke={theme.bgCard}
          isAnimationActive={false}
          content={<TreemapTile onSelect={onSelect} measureFormat={data.measure_format} />}
        />
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Custom treemap tile: border, label, and value when the tile is big enough.
 *
 * Recharts spreads the *node itself* onto this component's props (not a
 * ``payload`` object as cartesian charts do), so our ChartPoint fields —
 * ``label``, ``value``, ``fill``, ``is_other`` — arrive as top-level props.
 */
function TreemapTile({ x, y, width, height, label, value, fill, is_other: isOther, onSelect, measureFormat, ...rest }) {
  const canLabel = width > 62 && height > 34
  const name = label ?? rest.name

  return (
    <g
      onClick={() => (isOther ? null : onSelect?.({ ...rest, label: name, value, is_other: isOther }))}
      style={{ cursor: isOther ? 'default' : 'pointer' }}
    >
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={fill}
        stroke="#ffffff"
        strokeWidth={2.5}
        rx={3}
      />
      {canLabel && (
        <>
          <text x={x + 8} y={y + 18} fill="#ffffff" fontSize={12} fontWeight={600}>
            {truncateLabel(name, Math.max(4, Math.floor(width / 8)))}
          </text>
          <text x={x + 8} y={y + 32} fill="#ffffff" fontSize={11} opacity={0.85}>
            {measureFormat === 'percent'
              ? formatPercent(value)
              : measureFormat === 'number'
                ? formatNumber(value)
                : formatCurrency(value)}
          </text>
        </>
      )}
    </g>
  )
}
