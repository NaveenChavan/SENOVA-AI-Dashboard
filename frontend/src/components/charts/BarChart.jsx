import { BarChart as ReBar, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

const EMERALD = '#10b981'
const MUTED = '#38bdf8'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card-gradient px-4 py-3 rounded-lg border border-slate-600/60 shadow-xl">
      <p className="text-slate-300 text-xs font-medium mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-semibold" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  )
}

export default function BarChart({ data, dataKey = 'revenue', color = EMERALD }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ReBar data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" strokeOpacity={0.3} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={{ stroke: '#475569' }} />
        <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={{ stroke: '#475569' }} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#1e293b' }} />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} maxBarSize={48} />
      </ReBar>
    </ResponsiveContainer>
  )
}
