import Card from '../common/Card'

const fmtMoney = (n) => `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`

/**
 * Profit & Loss statement, presented the way a Chartered Accountant would
 * print it: labelled line items with a ruled-off subtotal — not a chart.
 */
function PnLStatement({ pnl }) {
  if (!pnl || pnl.length === 0) return null

  return (
    <Card title="Profit &amp; Loss Statement">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            <th className="text-left py-2 font-medium uppercase tracking-wider text-xs" style={{ color: 'var(--text-muted)' }}>
              Particulars
            </th>
            <th className="text-right py-2 font-medium uppercase tracking-wider text-xs" style={{ color: 'var(--text-muted)' }}>
              Amount (₹)
            </th>
            <th className="text-right py-2 font-medium uppercase tracking-wider text-xs" style={{ color: 'var(--text-muted)' }}>
              % of Revenue
            </th>
          </tr>
        </thead>
        <tbody>
          {pnl.map((line) => (
            <tr
              key={line.label}
              className={line.is_subtotal ? 'border-t-2' : 'border-b'}
              style={{
                borderColor: line.is_subtotal ? 'var(--border-active)' : 'var(--border-subtle)',
              }}
            >
              <td
                className={`py-2.5 ${line.is_subtotal ? 'font-bold' : ''}`}
                style={{ color: line.is_subtotal ? 'var(--accent-blue)' : 'var(--text-primary)' }}
              >
                {line.label}
              </td>
              <td
                className={`py-2.5 text-right font-mono ${line.is_subtotal ? 'font-bold' : ''}`}
                style={{ color: line.is_subtotal ? 'var(--accent-blue)' : 'var(--text-secondary)' }}
              >
                {fmtMoney(line.amount)}
              </td>
              <td className="py-2.5 text-right font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                {line.percentage_of_revenue != null ? `${line.percentage_of_revenue}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

/**
 * Category-wise sales ledger — the "schedule" a CA attaches behind the
 * P&L to show revenue/cost/profit split by product segment.
 */
function CategoryLedger({ rows }) {
  if (!rows || rows.length === 0) return null

  return (
    <Card title="Category-wise Ledger">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              {['Category', 'Units Sold', 'Revenue (₹)', 'Cost (₹)', 'Profit (₹)', 'Margin %'].map((h, i) => (
                <th
                  key={h}
                  className={`py-2 font-medium uppercase tracking-wider text-xs whitespace-nowrap ${i === 0 ? 'text-left' : 'text-right'}`}
                  style={{ color: 'var(--text-muted)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.category} className="border-b last:border-0" style={{ borderColor: 'var(--border-subtle)' }}>
                <td className="py-2.5 font-medium" style={{ color: 'var(--text-primary)' }}>{row.category}</td>
                <td className="py-2.5 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {row.units_sold.toLocaleString('en-IN')}
                </td>
                <td className="py-2.5 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{fmtMoney(row.revenue)}</td>
                <td className="py-2.5 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{fmtMoney(row.cost)}</td>
                <td className="py-2.5 text-right font-mono" style={{ color: '#10b981' }}>{fmtMoney(row.profit)}</td>
                <td className="py-2.5 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{row.margin_percentage}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/**
 * Full CA-style financial report: period header, P&L statement, and the
 * category-wise ledger beneath it.
 */
export default function PnLReportTable({ report }) {
  if (!report) return null

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h2 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
          Financial Report — {report.period_label}
        </h2>
        {report.period_start && (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {report.period_start} to {report.period_end} &middot; {report.total_transactions.toLocaleString('en-IN')} transactions
          </p>
        )}
      </div>

      {report.pnl.length === 0 ? (
        <div className="card-gradient rounded-xl p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          No transactions in this period.
        </div>
      ) : (
        <>
          <PnLStatement pnl={report.pnl} />
          <CategoryLedger rows={report.category_ledger} />
        </>
      )}
    </div>
  )
}
