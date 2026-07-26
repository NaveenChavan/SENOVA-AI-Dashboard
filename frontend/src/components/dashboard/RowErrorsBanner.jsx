import { useMemo, useState } from 'react'

import Icon from '../common/Icon'

/**
 * Collapsed banner for row-level validation errors.
 *
 * Collapsed by default and only one line tall, because "partial success" is
 * information, not a blocker — the dashboard below it is still valid. Expanding
 * groups the failures by column so a repeated mistake (a whole date column in
 * the wrong format) reads as one problem rather than fifty.
 */

const MAX_VISIBLE = 10

export default function RowErrorsBanner({ errors }) {
  const [expanded, setExpanded] = useState(false)

  const total = errors?.length ?? 0
  const visible = useMemo(() => (errors ?? []).slice(0, MAX_VISIBLE), [errors])
  const grouped = useMemo(() => {
    const map = {}
    for (const error of visible) {
      if (!map[error.column]) map[error.column] = []
      map[error.column].push(error)
    }
    return map
  }, [visible])

  if (!total) return null
  const remainder = total - MAX_VISIBLE

  return (
    <div className="card" style={{ borderColor: 'color-mix(in srgb, var(--accent-amber) 40%, transparent)' }}>
      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-[var(--card-pad)] text-left cursor-pointer"
        style={{ minHeight: 42 }}
      >
        <Icon name="info" className="w-4 h-4 shrink-0" style={{ color: 'var(--accent-amber)' }} />
        <span className="text-xs font-semibold" style={{ color: 'var(--accent-amber)' }}>
          {total} row{total > 1 ? 's' : ''} skipped
        </span>
        <span className="text-[12px] truncate" style={{ color: 'var(--text-muted)' }}>
          — analytics below are computed from the valid rows only
        </span>
        <Icon
          name="close"
          className="w-3.5 h-3.5 ml-auto shrink-0"
          style={{
            color: 'var(--text-muted)',
            transform: expanded ? 'rotate(0deg)' : 'rotate(45deg)',
          }}
        />
      </button>

      {expanded && (
        <div className="px-[var(--card-pad)] pb-3 space-y-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {Object.entries(grouped).map(([column, columnErrors]) => (
            <div key={column} className="pt-2">
              <p className="panel-title mb-1">{column}</p>
              <ul className="space-y-0.5">
                {columnErrors.map((error, index) => (
                  <li key={index} className="flex items-start gap-2 text-[12px]">
                    <span className="font-mono shrink-0" style={{ color: 'var(--text-muted)', width: 34 }}>
                      R{error.row}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{error.error}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {remainder > 0 && (
            <p className="text-[12px] italic pt-1" style={{ color: 'var(--text-muted)' }}>
              …and {remainder} more.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
