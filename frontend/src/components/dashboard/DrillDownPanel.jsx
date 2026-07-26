import { useEffect, useRef } from 'react'

import Icon from '../common/Icon'
import { formatCurrency, formatNumber } from '../charts/chartFormat'

/**
 * Feature 5b — the drill-down panel.
 *
 * Clicking any bar, slice, tile or table row opens this slide-over with the
 * actual transactions behind that number, fetched with the *same* filters as the
 * page plus the clicked group. That closes the usual dashboard gap where a user
 * can see a total but not the rows that produced it.
 *
 * Accessibility handling: focus moves into the panel on open, Escape closes it,
 * and the backdrop is click-to-close — the standard dialog contract, since a
 * keyboard user must never get trapped behind an overlay.
 */
export default function DrillDownPanel({ selection, ledger, loading, onClose, onPageChange }) {
  const closeButtonRef = useRef(null)

  // Move focus into the dialog when it opens.
  useEffect(() => {
    if (selection) closeButtonRef.current?.focus()
  }, [selection])

  // Escape closes, as with any modal surface.
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
      {/* Backdrop */}
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(2, 6, 23, 0.55)', backdropFilter: 'blur(2px)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Transactions for ${selection.label}`}
        className="relative h-full w-full sm:w-[560px] overflow-y-auto p-4 sm:p-6"
        style={{
          background: 'var(--bg-card-solid)',
          borderLeft: '1px solid var(--border-strong)',
          boxShadow: 'var(--shadow-elevation-high)',
        }}
      >
        <header className="flex items-start justify-between gap-4 mb-4">
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Drill-down
            </p>
            <h2 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
              {selection.label}
            </h2>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {formatCurrency(selection.revenue)} revenue · {formatNumber(selection.units)} units ·{' '}
              {formatNumber(selection.transactions)} transaction(s)
            </p>
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close drill-down"
            className="rounded-lg p-2 cursor-pointer transition-colors"
            style={{ border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
          >
            <Icon name="close" className="w-4 h-4" />
          </button>
        </header>

        {loading && !entries.length ? (
          <div className="space-y-2 animate-pulse">
            {[...Array(6)].map((_, index) => (
              <div key={index} className="h-9 rounded" style={{ background: 'var(--bg-skeleton)' }} />
            ))}
          </div>
        ) : !entries.length ? (
          <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
            No individual transactions matched this selection.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <caption className="sr-only">Transactions making up {selection.label}</caption>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-strong)' }}>
                    <th scope="col" className="text-left py-2 pr-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      Date
                    </th>
                    <th scope="col" className="text-left py-2 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      Item
                    </th>
                    <th scope="col" className="text-right py-2 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      Qty
                    </th>
                    <th scope="col" className="text-right py-2 px-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      Revenue
                    </th>
                    <th scope="col" className="text-right py-2 pl-2 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      Profit
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={`${entry.row}-${entry.date}`} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td className="py-2 pr-2 font-mono" style={{ color: 'var(--text-secondary)' }}>
                        {entry.date}
                      </td>
                      <td className="py-2 px-2" style={{ color: 'var(--text-primary)' }}>
                        {entry.item}
                        <span className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {entry.category}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-secondary)' }}>
                        {entry.quantity}
                      </td>
                      <td className="py-2 px-2 text-right font-mono" style={{ color: 'var(--text-primary)' }}>
                        {formatCurrency(entry.revenue)}
                      </td>
                      <td
                        className="py-2 pl-2 text-right font-mono"
                        style={{ color: entry.profit < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}
                      >
                        {formatCurrency(entry.profit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination — a busy item can have thousands of lines. */}
            {ledger.total_pages > 1 && (
              <nav className="flex items-center justify-between gap-3 mt-4" aria-label="Drill-down pages">
                <button
                  type="button"
                  disabled={ledger.page <= 1}
                  onClick={() => onPageChange?.(ledger.page - 1)}
                  className="text-xs rounded-lg px-3 cursor-pointer disabled:cursor-not-allowed"
                  style={{
                    minHeight: 36,
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    opacity: ledger.page <= 1 ? 0.4 : 1,
                  }}
                >
                  Previous
                </button>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Page {ledger.page} of {ledger.total_pages} · {formatNumber(ledger.total_rows)} rows
                </span>
                <button
                  type="button"
                  disabled={ledger.page >= ledger.total_pages}
                  onClick={() => onPageChange?.(ledger.page + 1)}
                  className="text-xs rounded-lg px-3 cursor-pointer disabled:cursor-not-allowed"
                  style={{
                    minHeight: 36,
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    opacity: ledger.page >= ledger.total_pages ? 0.4 : 1,
                  }}
                >
                  Next
                </button>
              </nav>
            )}
          </>
        )}
      </aside>
    </div>
  )
}
