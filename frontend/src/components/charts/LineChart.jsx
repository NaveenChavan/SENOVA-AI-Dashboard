import { LineChart as ReLine, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'

const ACCENT_BLUE = '#38bdf8'
const ACCENT_GREEN = '#10b981'

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
  return (
    <div className="h-64 md:h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ReLine data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" strokeOpacity={0.5} />
          <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#7a9cc4' }} axisLine={{ stroke: '#1e2d4a' }} />
          <YAxis tickFormatter={fmtY} tick={{ fontSize: 12, fill: '#7a9cc4' }} axisLine={{ stroke: '#1e2d4a' }} />
          <Tooltip content={<CustomTooltip />} />
          <Legend content={<CustomLegend />} />
          <Line type="monotone" dataKey="revenue" stroke={ACCENT_BLUE} strokeWidth={2.5} dot={{ r: 3, fill: ACCENT_BLUE, strokeWidth: 0 }} activeDot={{ r: 5, fill: ACCENT_BLUE, strokeWidth: 2, stroke: '#050d1a' }} name="Revenue" />
          <Line type="monotone" dataKey="profit" stroke={ACCENT_GREEN} strokeWidth={2.5} dot={{ r: 3, fill: ACCENT_GREEN, strokeWidth: 0 }} activeDot={{ r: 5, fill: ACCENT_GREEN, strokeWidth: 2, stroke: '#050d1a' }} name="Profit" />
        </ReLine>
      </ResponsiveContainer>
    </div>
  )
}
