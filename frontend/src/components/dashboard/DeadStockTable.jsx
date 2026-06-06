import Card from '../common/Card'

export default function DeadStockTable({ items }) {
  if (!items || items.length === 0) return null

  return (
    <Card title="Dead Stock / Slow Movers">
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b border-slate-700 text-slate-500 uppercase tracking-wider text-xs">
              <th className="py-3 pr-4 font-medium">Item</th>
              <th className="py-3 pr-4 font-medium">Total Units Sold</th>
              <th className="py-3 font-medium">Days Since Last Sale</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name} className="border-b border-slate-700/50 last:border-0 hover:bg-slate-700/20 transition-colors">
                <td className="py-3 pr-4 font-medium text-slate-200">{item.name}</td>
                <td className="py-3 pr-4 text-slate-300">{item.total_quantity}</td>
                <td className="py-3">
                  <span className={`font-semibold ${item.days_since_last_sale > 30 ? 'text-red-400' : 'text-amber-400'}`}>
                    {item.days_since_last_sale} days
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
