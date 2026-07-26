import { useEffect, useRef } from 'react'

import Icon from '../common/Icon'
import { formatCurrency, formatCurrencyCompact, formatNumber } from '../charts/chartFormat'

/**
 * Feature 5b — the drill-down panel.
 *
 * Clicking any bar, slice, tile or table row opens this slide-over with the
 * actual transactions behind that number, fetched with the *same* filters as the
 * page plus the clicked group. That closes the usual dashboard gap where a user
 * can see a total but not the rows that produced it.
 *
 * Accessibility: focus moves into the panel on open, Escape closes it, the
 * backdrop is click-to-close, and the sheet is full-width on a phone but a
 * 480px side sheet on a desktop so the dashboard stays visible behind it.
 */
export default function DrillDownPanel({ selection, ledger, loading, onClose, onPageChange }) {
  const closeButtonRef = useRef(null)

  useEffect(() => {
    if (selection) closeButtonRef.current?.focus()
  }, [selection])

  useEffect(() => {
    if (!selection) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selection, onClose])

  if (!selection) return null

  const entries = ledger?.entries ?? []

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(16, 24, 40, 0.45)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Transactions for ${selection.label}`}
        className="relative h-full w-full sm:w-[480px] flex flex-col"
        style={{
          background: 'var(--bg-card-solid)',
          borderLeft: '1px solid var(--border-strong)',
          boxShadow: 'var(--shadow-high)',
        }}
      >
        <header
          className="flex items-start justify-between gap-3 px-[var(--card-pad)] py-3 shrink-0"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>
              Drill-down
            </p>
            <h2 className="truncate">{selection.label}</h2>
            <p className="panel-hint">
              {formatCurrency(selection.revenue)} · {formatNumber(selection.units)} units ·{' '}
              {formatNumber(selection.transactions)} txn
            </p>
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close drill-down"
            className="btn-icon shrink-0"
          >
            <Icon name="close" className="w-3.5 h-3.5" />
          </button>
        </header>

        {/* Body scrolls; header and footer stay put. */}
        <div className="flex-1 overflow-y-auto px-[var(--card-pad)] py-2">
          {loading && !entries.length ? (
            <div className="space-y-1.5">
              {[...Array(8)].map((_, index) => (
                <div key={index} className="skeleton h-7" />
              ))}
            </div>
          ) : !entries.length ? (
            <p className="text-xs py-8 text-center" style={{ color: 'var(--text-muted)' }}>
              No individual transactions matched this selection.
            </p>
          ) : (
            <div className="scroll-x">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Item</th>
                    <th scope="col">Qty</th>
                    <th scope="col">Revenue</th>
                    <th scope="col">Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={`${entry.row}-${entry.date}`}>
                      <td className="font-mono" style={{ textAlign: 'left' }}>
                        {entry.date}
                      </td>
                      <th scope="row">
                        <span className="block truncate" style={{ maxWidth: 150 }} title={entry.item}>
                          {entry.item}
                        </span>
                        <span className="block text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>
                          {entry.category}
                        </span>
                      </th>
                      <td className="font-mono">{entry.quantity}</td>
                      <td className="font-mono">{formatCurrencyCompact(entry.revenue)}</td>
                      <td
                        className="font-mono"
                        style={{ color: entry.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                      >
                        {formatCurrencyCompact(entry.profit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination — a busy item can have thousands of lines. */}
        {ledger && ledger.total_pages > 1 && (
          <nav
            className="flex items-center justify-between gap-2 px-[var(--card-pad)] py-2.5 shrink-0"
            style={{ borderTop: '1px solid var(--border-subtle)' }}
            aria-label="Drill-down pages"
          >
            <button
              type="button"
              className="btn"
              disabled={ledger.page <= 1}
              onClick={() => onPageChange?.(ledger.page - 1)}
            >
              Prev
            </button>
            <span className="text-[12px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {ledger.page} / {ledger.total_pages} · {formatNumber(ledger.total_rows)} rows
            </span>
            <button
              type="button"
              className="btn"
              disabled={ledger.page >= ledger.total_pages}
              onClick={() => onPageChange?.(ledger.page + 1)}
            >
              Next
            </button>
          </nav>
        )}
      </aside>
    </div>
  )
}
