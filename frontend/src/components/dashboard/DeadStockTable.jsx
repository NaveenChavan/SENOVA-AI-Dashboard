import Card from '../common/Card'

function SeverityBadge({ days }) {
  if (days > 30) {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
        style={{background: 'rgba(239,68,68,0.12)', color: '#f87171'}}>
        🔴 Critical
      </span>
    )
  }
  if (days > 14) {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
        style={{background: 'rgba(234,179,8,0.12)', color: '#facc15'}}>
        🟡 Warning
      </span>
    )
  }
  return (
    <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
      style={{background: 'rgba(16,185,129,0.12)', color: '#10b981'}}>
      🟢 Recent
    </span>
  )
}

export default function DeadStockTable({ items }) {
  if (!items || items.length === 0) return null

  return (
    <Card title="Dead Stock / Slow Movers">
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b" style={{borderColor:'var(--border-subtle)'}}>
              <th className="py-3 pr-4 font-medium uppercase tracking-wider text-xs"
                style={{color:'var(--text-muted)'}}>Item</th>
              <th className="py-3 pr-4 font-medium uppercase tracking-wider text-xs"
                style={{color:'var(--text-muted)'}}>Total Units Sold</th>
              <th className="py-3 pr-4 font-medium uppercase tracking-wider text-xs"
                style={{color:'var(--text-muted)'}}>Days Since Last Sale</th>
              <th className="py-3 font-medium uppercase tracking-wider text-xs"
                style={{color:'var(--text-muted)'}}>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name} className="border-b last:border-0 transition-colors"
                style={{borderColor:'var(--border-subtle)'}}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(56,189,248,0.04)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                <td className="py-3 pr-4 font-medium" style={{color:'var(--text-primary)'}}>{item.name}</td>
                <td className="py-3 pr-4" style={{color:'var(--text-secondary)'}}>{item.total_quantity}</td>
                <td className="py-3 pr-4" style={{color:'var(--text-secondary)'}}>
                  {item.days_since_last_sale} days
                </td>
                <td className="py-3">
                  <SeverityBadge days={item.days_since_last_sale} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}