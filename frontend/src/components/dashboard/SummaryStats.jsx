import Card from '../common/Card'

export default function SummaryStats({ summary }) {
  if (!summary) return null

  const tiles = [
    { label: 'Total Revenue', value: `₹${summary.total_revenue.toLocaleString('en-IN')}`, accent: 'text-emerald-400' },
    { label: 'Total Profit', value: `₹${summary.total_profit.toLocaleString('en-IN')}`, accent: 'text-emerald-300' },
    { label: 'Total Cost', value: `₹${summary.total_cost.toLocaleString('en-IN')}`, accent: 'text-slate-300' },
    { label: 'Units Sold', value: summary.total_units_sold.toLocaleString('en-IN'), accent: 'text-sky-400' },
    { label: 'Unique Items', value: summary.unique_items_sold, accent: 'text-violet-400' },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {tiles.map((t) => (
        <Card key={t.label}>
          <p className="text-xs text-slate-500 uppercase tracking-wider font-medium">{t.label}</p>
          <p className={`text-2xl font-bold mt-1.5 glow-emerald-text ${t.accent}`}>{t.value}</p>
        </Card>
      ))}
    </div>
  )
}
