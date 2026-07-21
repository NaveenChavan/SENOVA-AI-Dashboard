import { useMemo, useState } from 'react'
import Button from '../common/Button'

// The 6 fields every uploaded file must eventually map to. "" (empty) means
// "ignore this column" — not every raw column needs a home (e.g. a shop's
// internal "Notes" or "Discount %" column).
const CANONICAL_FIELDS = [
  { value: '', label: 'Ignore this column' },
  { value: 'Date', label: 'Date' },
  { value: 'Category', label: 'Category' },
  { value: 'Item', label: 'Item' },
  { value: 'Quantity', label: 'Quantity' },
  { value: 'Selling Price', label: 'Selling Price' },
  { value: 'Cost Price', label: 'Cost Price' },
]

const REQUIRED_FIELDS = ['Date', 'Category', 'Item', 'Quantity', 'Selling Price', 'Cost Price']

function ConfidenceBadge({ confidence }) {
  const styles = {
    exact: { bg: 'rgba(16,185,129,0.12)', color: '#10b981', label: 'Matched' },
    fuzzy: { bg: 'rgba(234,179,8,0.12)', color: '#facc15', label: 'Guessed — please check' },
    none: { bg: 'rgba(148,163,184,0.12)', color: '#94a3b8', label: 'Not recognised' },
  }
  const s = styles[confidence] || styles.none
  return (
    <span
      className="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  )
}

/**
 * Column-mapping confirmation screen. Every shop's export format is
 * different (different column names, order, extra columns) — this screen
 * shows our best guess and lets the user fix anything before we run any
 * analysis on their data, instead of silently assuming our guess is right.
 */
export default function ColumnMappingScreen({ preview, onConfirm, onCancel, submitting }) {
  const [mapping, setMapping] = useState(() => {
    const initial = {}
    for (const col of preview.detected_columns) {
      initial[col.raw_column] = col.suggested_field || ''
    }
    return initial
  })

  const confidenceByColumn = useMemo(() => {
    const map = {}
    for (const col of preview.detected_columns) map[col.raw_column] = col.confidence
    return map
  }, [preview.detected_columns])

  // Which canonical fields are currently mapped to some column — used to
  // detect duplicates (two raw columns both mapped to "Quantity") and to
  // show which required fields are still missing.
  const assignedFields = Object.values(mapping).filter(Boolean)
  const duplicates = assignedFields.filter((f, i) => assignedFields.indexOf(f) !== i)
  const missingRequired = REQUIRED_FIELDS.filter((f) => !assignedFields.includes(f))

  const canSubmit = duplicates.length === 0 && missingRequired.length === 0 && !submitting

  const handleChange = (rawColumn, value) => {
    setMapping((prev) => ({ ...prev, [rawColumn]: value }))
  }

  return (
    <div className="card-gradient rounded-2xl overflow-hidden" style={{ border: '1px solid var(--border-strong)' }}>
      <div className="px-4 sm:px-6 py-4 sm:py-5" style={{ borderBottom: '1px solid var(--border-strong)' }}>
        <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
          Confirm your columns
        </h2>
        <p className="text-xs sm:text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          Every shop's spreadsheet is a little different. We've matched what we could —
          please check the guesses below and fix anything that's wrong.
        </p>
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          {preview.row_count.toLocaleString('en-IN')} row{preview.row_count === 1 ? '' : 's'} detected in{' '}
          <span className="font-medium">{preview.filename}</span>
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{ borderBottom: '1px solid var(--border-strong)' }}>
              <th className="px-4 sm:px-6 py-3 font-medium uppercase tracking-wider text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                Your column
              </th>
              <th className="px-4 py-3 font-medium uppercase tracking-wider text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                Sample value
              </th>
              <th className="px-4 py-3 font-medium uppercase tracking-wider text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                Maps to
              </th>
              <th className="px-4 py-3 font-medium uppercase tracking-wider text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {preview.detected_columns.map((col) => {
              const value = mapping[col.raw_column]
              const isDuplicate = value && duplicates.includes(value)
              const sample = preview.sample_rows?.[0]?.[col.raw_column]
              return (
                <tr key={col.raw_column} className="last:border-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td className="px-4 sm:px-6 py-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                    {col.raw_column}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs truncate max-w-[160px]" style={{ color: 'var(--text-muted)' }}>
                    {sample ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={value}
                      onChange={(e) => handleChange(col.raw_column, e.target.value)}
                      className="filter-select w-full max-w-[200px]"
                      style={isDuplicate ? { borderColor: 'var(--accent-red)' } : undefined}
                      aria-label={`Map column ${col.raw_column} to a field`}
                    >
                      {CANONICAL_FIELDS.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                    {isDuplicate && (
                      <p className="text-xs mt-1" style={{ color: 'var(--accent-red)' }}>
                        Already used by another column
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <ConfidenceBadge confidence={confidenceByColumn[col.raw_column]} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="px-4 sm:px-6 py-4 sm:py-5" style={{ borderTop: '1px solid var(--border-strong)' }}>
        {missingRequired.length > 0 && (
          <p className="text-sm mb-4" style={{ color: 'var(--accent-amber)' }}>
            Still need a column for: <strong>{missingRequired.join(', ')}</strong>
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-3 sm:justify-end">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
            Cancel &amp; choose another file
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={!canSubmit}
            loading={submitting}
            onClick={() => onConfirm(mapping)}
          >
            Confirm &amp; analyse
          </Button>
        </div>
      </div>
    </div>
  )
}
