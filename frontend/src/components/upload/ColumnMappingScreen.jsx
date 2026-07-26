import { useMemo, useState } from 'react'
import Button from '../common/Button'

/**
 * Column-mapping confirmation screen.
 *
 * Every shop's export is different — different headers, different order, extra
 * columns — so nothing is analysed until the user confirms what maps where. This
 * screen shows our guess, flags how confident it was, and lets the user fix it.
 *
 * The field list comes from the server (``required_fields`` + ``optional_fields``
 * + ``field_help``) rather than being hardcoded here, so adding a new supported
 * field on the backend surfaces automatically.
 *
 * Optional fields are what unlock the Pro features: Discount refines revenue,
 * Stock On Hand turns the inventory tab into real reorder alerts, and Branch /
 * Payment Mode / Salesperson become extra chart axes and filters.
 */

/** Fallbacks used only if an older backend response omits the field lists. */
const FALLBACK_REQUIRED = ['Date', 'Category', 'Item', 'Quantity', 'Selling Price', 'Cost Price']
const FALLBACK_OPTIONAL = []

/** Optional fields that are numbers rather than dimensions, for grouping. */
const MEASURE_FIELDS = new Set(['Line Total', 'Discount', 'Tax', 'Stock On Hand'])

function ConfidenceBadge({ confidence }) {
  const styles = {
    exact: { bg: 'rgba(16,185,129,0.12)', color: '#10b981', label: 'Matched' },
    fuzzy: { bg: 'rgba(234,179,8,0.12)', color: '#facc15', label: 'Guessed — please check' },
    none: { bg: 'rgba(148,163,184,0.12)', color: '#94a3b8', label: 'Not recognised' },
  }
  const style = styles[confidence] || styles.none
  return (
    <span
      className="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: style.bg, color: style.color }}
    >
      {style.label}
    </span>
  )
}

export default function ColumnMappingScreen({ preview, onConfirm, onCancel, submitting }) {
  const requiredFields = preview.required_fields?.length ? preview.required_fields : FALLBACK_REQUIRED
  const optionalFields = preview.optional_fields?.length ? preview.optional_fields : FALLBACK_OPTIONAL
  const fieldHelp = preview.field_help ?? {}

  const [mapping, setMapping] = useState(() => {
    const initial = {}
    for (const column of preview.detected_columns) {
      initial[column.raw_column] = column.suggested_field || ''
    }
    return initial
  })

  const confidenceByColumn = useMemo(() => {
    const map = {}
    for (const column of preview.detected_columns) map[column.raw_column] = column.confidence
    return map
  }, [preview.detected_columns])

  const assignedFields = Object.values(mapping).filter(Boolean)
  const duplicates = assignedFields.filter((field, index) => assignedFields.indexOf(field) !== index)

  /**
   * Selling Price is the one required field that can be *derived*: if the file
   * only carries a line total (Amount / Net Amount), the server computes the
   * unit price as total ÷ quantity. So it stops being required once Line Total
   * is mapped.
   */
  const hasLineTotal = assignedFields.includes('Line Total')
  const effectiveRequired = requiredFields.filter(
    (field) => !(field === 'Selling Price' && hasLineTotal),
  )
  const missingRequired = effectiveRequired.filter((field) => !assignedFields.includes(field))

  const mappedOptional = optionalFields.filter((field) => assignedFields.includes(field))
  const canSubmit = duplicates.length === 0 && missingRequired.length === 0 && !submitting

  const handleChange = (rawColumn, value) => {
    setMapping((previous) => ({ ...previous, [rawColumn]: value }))
  }

  return (
    <div className="card-gradient rounded-2xl overflow-hidden" style={{ border: '1px solid var(--border-strong)' }}>
      <div className="px-4 sm:px-6 py-4 sm:py-5" style={{ borderBottom: '1px solid var(--border-strong)' }}>
        <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
          Confirm your columns
        </h2>
        <p className="text-xs sm:text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          Every shop's spreadsheet is a little different. We've matched what we could — please check the
          guesses below and fix anything that's wrong.
        </p>
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          {preview.row_count.toLocaleString('en-IN')} row{preview.row_count === 1 ? '' : 's'} detected in{' '}
          <span className="font-medium">{preview.filename}</span>
        </p>
      </div>

      {/* overflow-x-auto so a wide mapping table scrolls instead of breaking. */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{ borderBottom: '1px solid var(--border-strong)' }}>
              <Th>Your column</Th>
              <Th>Sample value</Th>
              <Th>Maps to</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {preview.detected_columns.map((column) => {
              const value = mapping[column.raw_column]
              const isDuplicate = value && duplicates.includes(value)
              const sample = preview.sample_rows?.[0]?.[column.raw_column]

              return (
                <tr
                  key={column.raw_column}
                  className="last:border-0"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <td className="px-4 sm:px-6 py-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                    {column.raw_column}
                  </td>
                  <td
                    className="px-4 py-3 font-mono text-xs truncate max-w-[160px]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {sample ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={value}
                      onChange={(event) => handleChange(column.raw_column, event.target.value)}
                      className="filter-select w-full max-w-[220px] cursor-pointer"
                      style={isDuplicate ? { borderColor: 'var(--accent-red)' } : undefined}
                      aria-label={`Map column ${column.raw_column} to a field`}
                    >
                      <option value="">Ignore this column</option>

                      <optgroup label="Required">
                        {requiredFields.map((field) => (
                          <option key={field} value={field} title={fieldHelp[field]}>
                            {field}
                          </option>
                        ))}
                      </optgroup>

                      {optionalFields.some((field) => MEASURE_FIELDS.has(field)) && (
                        <optgroup label="Optional — extra amounts">
                          {optionalFields
                            .filter((field) => MEASURE_FIELDS.has(field))
                            .map((field) => (
                              <option key={field} value={field} title={fieldHelp[field]}>
                                {field}
                              </option>
                            ))}
                        </optgroup>
                      )}

                      {optionalFields.some((field) => !MEASURE_FIELDS.has(field)) && (
                        <optgroup label="Optional — extra breakdowns">
                          {optionalFields
                            .filter((field) => !MEASURE_FIELDS.has(field))
                            .map((field) => (
                              <option key={field} value={field} title={fieldHelp[field]}>
                                {field}
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </select>

                    {/* Helper text for the chosen field: this screen is where a
                        wrong pick quietly corrupts every later number. */}
                    {value && fieldHelp[value] && !isDuplicate && (
                      <p className="text-[11px] mt-1 max-w-[220px]" style={{ color: 'var(--text-muted)' }}>
                        {fieldHelp[value]}
                      </p>
                    )}
                    {isDuplicate && (
                      <p className="text-xs mt-1" style={{ color: 'var(--accent-red)' }}>
                        Already used by another column
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <ConfidenceBadge confidence={confidenceByColumn[column.raw_column]} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="px-4 sm:px-6 py-4 sm:py-5 space-y-3" style={{ borderTop: '1px solid var(--border-strong)' }}>
        {missingRequired.length > 0 && (
          <p className="text-sm" style={{ color: 'var(--accent-amber)' }}>
            Still need a column for: <strong>{missingRequired.join(', ')}</strong>
          </p>
        )}

        {hasLineTotal && !assignedFields.includes('Selling Price') && (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            No unit price mapped — we'll calculate it as Line Total ÷ Quantity, which keeps revenue
            correct instead of multiplying by quantity twice.
          </p>
        )}

        {mappedOptional.length > 0 && (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Extra features unlocked by this mapping: <strong>{mappedOptional.join(', ')}</strong>
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

function Th({ children }) {
  return (
    <th
      className="px-4 sm:px-6 py-3 font-medium uppercase tracking-wider text-xs whitespace-nowrap"
      style={{ color: 'var(--text-muted)' }}
    >
      {children}
    </th>
  )
}
