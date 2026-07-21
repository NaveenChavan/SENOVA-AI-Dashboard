import { BarChart as ReBar, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import useChartTheme from './useChartTheme'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card-gradient px-4 py-3 rounded-lg" style={{ border: '1px solid var(--border-strong)', boxShadow: 'var(--shadow-elevation-medium)' }}>
      <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-semibold" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  )
}

export default function BarChart({ data, dataKey = 'revenue', color }) {
  const theme = useChartTheme()
  const barColor = color || theme.accentGreen

  return (
    <div className="h-56 sm:h-64 md:h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ReBar data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.borderStrong} strokeOpacity={0.3} />
          <XAxis dataKey="name" tick={{ fontSize: 12, fill: theme.textSecondary }} axisLine={{ stroke: theme.borderStrong }} />
          <YAxis tick={{ fontSize: 12, fill: theme.textSecondary }} axisLine={{ stroke: theme.borderStrong }} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: theme.borderSubtle }} />
          <Bar dataKey={dataKey} fill={barColor} radius={[4, 4, 0, 0]} maxBarSize={48} />
        </ReBar>
      </ResponsiveContainer>
    </div>
  )
}
