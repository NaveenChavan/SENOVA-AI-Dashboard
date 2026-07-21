import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import useChartTheme from './useChartTheme'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div className="card-gradient px-4 py-3 rounded-lg" style={{ border: '1px solid var(--border-strong)', boxShadow: 'var(--shadow-elevation-medium)' }}>
      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{d.name}</p>
      <p className="text-sm font-semibold mt-1" style={{ color: 'var(--accent-green)' }}>
        ₹{typeof d.value === 'number' ? d.value.toLocaleString('en-IN') : d.value}
      </p>
      <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
        {((d.payload.percent || 0) * 100).toFixed(1)}% of total
      </p>
    </div>
  )
}

function CustomLegend({ payload }) {
  if (!payload) return null
  return (
    <div className="space-y-2">
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-3">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <div className="min-w-0">
            <p className="text-xs truncate max-w-[100px]" style={{ color: 'var(--text-secondary)' }}>{entry.value}</p>
            <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              ₹{typeof entry.payload?.value === 'number' ? entry.payload.value.toLocaleString('en-IN') : entry.payload?.value}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function CategoryPieChart({ data }) {
  const theme = useChartTheme()
  if (!data || data.length === 0) return null

  const total = data.reduce((s, d) => s + d.revenue, 0)
  const enriched = data.map((d) => ({ ...d, percent: total > 0 ? d.revenue / total : 0 }))

  return (
    <div className="h-56 sm:h-64 md:h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <Pie
            data={enriched}
            dataKey="revenue"
            nameKey="category"
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={85}
            paddingAngle={3}
            cornerRadius={4}
          >
            {enriched.map((_, i) => (
              <Cell key={i} fill={theme.categorical[i % theme.categorical.length]} stroke="transparent" />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            content={<CustomLegend />}
            layout="vertical"
            align="right"
            verticalAlign="middle"
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
