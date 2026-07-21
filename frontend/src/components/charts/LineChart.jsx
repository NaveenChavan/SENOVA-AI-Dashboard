import { LineChart as ReLine, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import useChartTheme from './useChartTheme'

const fmtY = (v) => {
  if (v >= 1e7) return `₹${(v/1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `₹${(v/1e5).toFixed(1)}L`
  return `₹${v.toLocaleString('en-IN')}`
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-4 py-3 rounded-lg border" style={{borderColor:'var(--border-subtle)'}}>
      <p className="text-xs font-medium mb-1" style={{color:'var(--text-secondary)'}}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-semibold" style={{ color: entry.color }}>
          {entry.name}: ₹{typeof entry.value === 'number' ? entry.value.toLocaleString('en-IN') : entry.value}
        </p>
      ))}
    </div>
  )
}

function CustomLegend({ payload }) {
  if (!payload) return null
  return (
    <div className="flex justify-center gap-6 mt-2">
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-3 h-0.5 rounded-full" style={{ backgroundColor: entry.color }} />
          <span className="text-xs" style={{color:'var(--text-secondary)'}}>{entry.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function LineChart({ data }) {
  const theme = useChartTheme()

  return (
    <div className="h-56 sm:h-64 md:h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ReLine data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.5} />
          <XAxis dataKey="date" tick={{ fontSize: 12, fill: theme.textSecondary }} axisLine={{ stroke: theme.borderStrong }} />
          <YAxis tickFormatter={fmtY} tick={{ fontSize: 12, fill: theme.textSecondary }} axisLine={{ stroke: theme.borderStrong }} />
          <Tooltip content={<CustomTooltip />} />
          <Legend content={<CustomLegend />} />
          <Line type="monotone" dataKey="revenue" stroke={theme.accentBlue} strokeWidth={2.5} dot={{ r: 3, fill: theme.accentBlue, strokeWidth: 0 }} activeDot={{ r: 5, fill: theme.accentBlue, strokeWidth: 2, stroke: theme.bgPrimary }} name="Revenue" />
          <Line type="monotone" dataKey="profit" stroke={theme.accentGreen} strokeWidth={2.5} dot={{ r: 3, fill: theme.accentGreen, strokeWidth: 0 }} activeDot={{ r: 5, fill: theme.accentGreen, strokeWidth: 2, stroke: theme.bgPrimary }} name="Profit" />
        </ReLine>
      </ResponsiveContainer>
    </div>
  )
}
