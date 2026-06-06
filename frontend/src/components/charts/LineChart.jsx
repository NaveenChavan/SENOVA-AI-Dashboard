import { LineChart as ReLine, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'

const EMERALD = '#10b981'
const NEON_BLUE = '#38bdf8'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card-gradient px-4 py-3 rounded-lg border border-slate-600/60 shadow-xl">
      <p className="text-slate-300 text-xs font-medium mb-1">{label}</p>
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
          <span className="text-xs text-slate-400">{entry.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function LineChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ReLine data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" strokeOpacity={0.3} />
        <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={{ stroke: '#475569' }} />
        <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={{ stroke: '#475569' }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend content={<CustomLegend />} />
        <Line type="monotone" dataKey="revenue" stroke={EMERALD} strokeWidth={2.5} dot={{ r: 3, fill: EMERALD, strokeWidth: 0 }} activeDot={{ r: 5, fill: EMERALD, strokeWidth: 2, stroke: '#0f172a' }} name="Revenue" />
        <Line type="monotone" dataKey="profit" stroke={NEON_BLUE} strokeWidth={2.5} dot={{ r: 3, fill: NEON_BLUE, strokeWidth: 0 }} activeDot={{ r: 5, fill: NEON_BLUE, strokeWidth: 2, stroke: '#0f172a' }} name="Profit" />
      </ReLine>
    </ResponsiveContainer>
  )
}
