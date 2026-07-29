import Card from '../common/Card'
import { formatCurrencyExact, formatNumber, formatPercent } from '../charts/chartFormat'

/**
 * CA-style financial report: a Profit & Loss statement plus the category-wise
 * ledger schedule beneath it — rows and columns, the way an accountant prints
 * them, not charts.
 *
 * Both tables use the shared compact `.table` styling, so the report reads at
 * the same density as every other panel and a long ledger scrolls inside its
 * own card instead of stretching the page.
 */

function PnLStatement({ pnl }) {
  if (!pnl?.length) return null

  return (
    <Card title="Profit &amp; loss statement" gradient>
      <div className="scroll-x">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Particulars</th>
              <th scope="col">Amount</th>
              <th scope="col">% of revenue</th>
            </tr>
          </thead>
          <tbody>
            {pnl.map((line) => (
              <tr key={line.label}>
                <th
                  scope="row"
                  style={{
                    color: line.is_subtotal ? 'var(--accent-blue)' : 'var(--text-primary)',
                    fontWeight: line.is_subtotal ? 700 : 550,
                    borderTop: line.is_subtotal ? '1px solid var(--border-strong)' : undefined,
                  }}
                >
                  {line.label}
                </th>
                <td
                  className="font-mono"
                  style={{
                    color: line.is_subtotal ? 'var(--accent-blue)' : 'var(--text-secondary)',
                    fontWeight: line.is_subtotal ? 700 : 400,
                    borderTop: line.is_subtotal ? '1px solid var(--border-strong)' : undefined,
                  }}
                >
                  {formatCurrencyExact(line.amount)}
                </td>
                <td
                  className="font-mono"
                  style={{ borderTop: line.is_subtotal ? '1px solid var(--border-strong)' : undefined }}
                >
                  {line.percentage_of_revenue != null ? formatPercent(line.percentage_of_revenue) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function CategoryLedger({ rows }) {
  if (!rows?.length) return null

  return (
    <Card title="Category-wise ledger" hint={`${rows.length} category group(s)`}>
      <div className="scroll-x" style={{ maxHeight: 320, overflowY: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Units</th>
              <th scope="col">Revenue</th>
              <th scope="col">Cost</th>
              <th scope="col">Profit</th>
              <th scope="col">Margin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.category}>
                <th scope="row">{row.category}</th>
                <td className="font-mono">{formatNumber(row.units_sold)}</td>
                <td className="font-mono">{formatCurrencyExact(row.revenue)}</td>
                <td className="font-mono">{formatCurrencyExact(row.cost)}</td>
                <td
                  className="font-mono"
                  style={{ color: row.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                >
                  {formatCurrencyExact(row.profit)}
                </td>
                <td className="font-mono">{formatPercent(row.margin_percentage)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function PnLReportTable({ report }) {
  if (!report) return null

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h2 className="truncate">Financial report — {report.period_label}</h2>
        {report.period_start && (
          <p className="panel-hint">
            {report.period_start} to {report.period_end} · {formatNumber(report.total_transactions)} transactions
          </p>
        )}
      </div>

      {report.pnl.length === 0 ? (
        <p className="card card-pad text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          No transactions in this period.
        </p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-[var(--gap)] items-start">
          <PnLStatement pnl={report.pnl} />
          <CategoryLedger rows={report.category_ledger} />
        </div>
      )}
    </div>
  )
}
