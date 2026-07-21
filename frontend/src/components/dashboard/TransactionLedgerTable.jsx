import Card from '../common/Card'
import Button from '../common/Button'

const fmtMoney = (n) => `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`

/**
 * Detailed, row-by-row transaction ledger — the day-book / sales register
 * behind the summary numbers. Paginated server-side because real files
 * run into tens of thousands of rows; we only ever hold one page in memory.
 */
export default function TransactionLedgerTable({ ledgerPage, loading, onPageChange }) {
  if (!ledgerPage && !loading) return null

  return (
    <Card title="Detailed Transaction Ledger">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              {['#', 'Date', 'Category', 'Item', 'Qty', 'Selling Price', 'Cost Price', 'Revenue', 'Profit'].map((h, i) => (
                <th
                  key={h}
                  className={`py-2 px-2 font-medium uppercase tracking-wider text-xs whitespace-nowrap ${i <= 3 ? 'text-left' : 'text-right'}`}
                  style={{ color: 'var(--text-muted)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={9} className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                  Loading transactions…
                </td>
              </tr>
            )}
            {!loading && ledgerPage?.entries?.length === 0 && (
              <tr>
                <td colSpan={9} className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                  No transactions in this period.
                </td>
              </tr>
            )}
            {!loading &&
              ledgerPage?.entries?.map((e) => (
                <tr key={e.row} className="border-b last:border-0" style={{ borderColor: 'var(--border-subtle)' }}>
                  <td className="py-2 px-2 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{e.row}</td>
                  <td className="py-2 px-2" style={{ color: 'var(--text-secondary)' }}>{e.date}</td>
                  <td className="py-2 px-2" style={{ color: 'var(--text-secondary)' }}>{e.category}</td>
                  <td className="py-2 px-2 font-medium" style={{ color: 'var(--text-primary)' }}>{e.item}</td>
                  <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{e.quantity}</td>
                  <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{fmtMoney(e.selling_price)}</td>
                  <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{fmtMoney(e.cost_price)}</td>
                  <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{fmtMoney(e.revenue)}</td>
                  <td className="py-2 px-2 text-right font-mono" style={{ color: e.profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {fmtMoney(e.profit)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {ledgerPage && ledgerPage.total_pages > 1 && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mt-4 pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Page {ledgerPage.page} of {ledgerPage.total_pages} &middot; {ledgerPage.total_rows.toLocaleString('en-IN')} total rows
          </p>
          <div className="flex gap-2 self-end sm:self-auto">
            <Button
              variant="secondary"
              disabled={ledgerPage.page <= 1 || loading}
              onClick={() => onPageChange(ledgerPage.page - 1)}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={ledgerPage.page >= ledgerPage.total_pages || loading}
              onClick={() => onPageChange(ledgerPage.page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
