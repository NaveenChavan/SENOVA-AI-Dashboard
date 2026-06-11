import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'

const COLORS = ['#10b981', '#3b82f6', '#8b5cf6', '#eab308']

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div className="card-gradient px-4 py-3 rounded-lg border border-slate-600/60 shadow-xl">
      <p className="text-slate-200 text-sm font-medium">{d.name}</p>
      <p className="text-emerald-400 text-sm font-semibold mt-1">
        ₹{typeof d.value === 'number' ? d.value.toLocaleString('en-IN') : d.value}
      </p>
      <p className="text-slate-500 text-xs mt-0.5">
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
            <p className="text-xs text-slate-300 truncate max-w-[100px]">{entry.value}</p>
            <p className="text-xs text-slate-500 font-mono">
              ₹{typeof entry.payload?.value === 'number' ? entry.payload.value.toLocaleString('en-IN') : entry.payload?.value}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function CategoryPieChart({ data }) {
  if (!data || data.length === 0) return null

  const total = data.reduce((s, d) => s + d.revenue, 0)
  const enriched = data.map((d) => ({ ...d, percent: total > 0 ? d.revenue / total : 0 }))

  return (
    <div className="h-64 md:h-[280px] w-full">
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
              <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
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
