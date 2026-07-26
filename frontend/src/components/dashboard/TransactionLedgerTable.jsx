import Card from '../common/Card'
import { formatCurrencyExact, formatNumber } from '../charts/chartFormat'

/**
 * The row-by-row transaction register (day-book) behind the summary numbers.
 *
 * Paginated server-side because real files run into tens of thousands of rows;
 * only one page is ever in memory. The body scrolls inside a capped height with
 * a sticky header, so the page length stays predictable regardless of page size.
 */
export default function TransactionLedgerTable({ ledgerPage, loading, onPageChange }) {
  if (!ledgerPage && !loading) return null

  const entries = ledgerPage?.entries ?? []
  // The discount column only appears when the file actually carries discounts —
  // and when it does, it's what explains why revenue ≠ qty × price.
  const showDiscount = entries.some((entry) => (entry.discount ?? 0) > 0)

  return (
    <Card
      title="Transaction ledger"
      hint={ledgerPage ? `${formatNumber(ledgerPage.total_rows)} rows in this period` : 'Loading…'}
      action={
        ledgerPage && ledgerPage.total_pages > 1 ? (
          <div className="flex items-center gap-1.5">
            <span className="text-[12px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {ledgerPage.page}/{ledgerPage.total_pages}
            </span>
            <button
              type="button"
              className="btn"
              disabled={ledgerPage.page <= 1 || loading}
              onClick={() => onPageChange(ledgerPage.page - 1)}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn"
              disabled={ledgerPage.page >= ledgerPage.total_pages || loading}
              onClick={() => onPageChange(ledgerPage.page + 1)}
            >
              Next
            </button>
          </div>
        ) : null
      }
    >
      <div className="scroll-x" style={{ maxHeight: 420, overflowY: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Date</th>
              <th scope="col">Category</th>
              <th scope="col">Item</th>
              <th scope="col">Qty</th>
              <th scope="col">Price</th>
              <th scope="col">Cost</th>
              {showDiscount && <th scope="col">Disc.</th>}
              <th scope="col">Revenue</th>
              <th scope="col">Profit</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={showDiscount ? 10 : 9} className="text-center py-6" style={{ color: 'var(--text-muted)' }}>
                  Loading transactions…
                </td>
              </tr>
            )}

            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={showDiscount ? 10 : 9} className="text-center py-6" style={{ color: 'var(--text-muted)' }}>
                  No transactions in this period.
                </td>
              </tr>
            )}

            {!loading &&
              entries.map((entry) => (
                <tr key={entry.row}>
                  <td className="font-mono" style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                    {entry.row}
                  </td>
                  <td className="font-mono" style={{ textAlign: 'left' }}>
                    {entry.date}
                  </td>
                  <td style={{ textAlign: 'left' }}>{entry.category}</td>
                  <th scope="row">{entry.item}</th>
                  <td className="font-mono">{entry.quantity}</td>
                  <td className="font-mono">{formatCurrencyExact(entry.selling_price)}</td>
                  <td className="font-mono">{formatCurrencyExact(entry.cost_price)}</td>
                  {showDiscount && (
                    <td className="font-mono" style={{ color: 'var(--text-muted)' }}>
                      {formatCurrencyExact(entry.discount ?? 0)}
                    </td>
                  )}
                  <td className="font-mono">{formatCurrencyExact(entry.revenue)}</td>
                  <td
                    className="font-mono"
                    style={{ color: entry.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                  >
                    {formatCurrencyExact(entry.profit)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
