import { useMemo, useState } from 'react'

import Button from '../common/Button'
import { formatNumber } from '../charts/chartFormat'

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
const MEASURE_FIELDS = new Set(['Line Total', 'Discount', 'Tax', 'Stock On Hand', 'MRP'])

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

  /**
   * Columns the user has personally picked a field for.
   *
   * Needed because a pre-filled guess and a deliberate choice look identical
   * from `mapping` alone — a low-confidence row arrives with a field already
   * selected, and that row is precisely the one worth highlighting. Once the
   * user touches it themselves, the question is answered and the highlight goes.
   */
  const [reviewed, setReviewed] = useState(() => new Set())

  const confidenceByColumn = useMemo(() => {
    const map = {}
    for (const column of preview.detected_columns) map[column.raw_column] = column
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
    setReviewed((previous) => (previous.has(rawColumn) ? previous : new Set(previous).add(rawColumn)))
  }

  return (
    <div className="card">
      <header className="px-[var(--card-pad)] py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <h2>Confirm your columns</h2>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          Every shop's spreadsheet is a little different. Check the guesses below and fix anything that's wrong.
        </p>
        <p className="text-[12px] mt-1" style={{ color: 'var(--text-muted)' }}>
          {formatNumber(preview.row_count)} row{preview.row_count === 1 ? '' : 's'} detected in{' '}
          <span className="font-medium">{preview.filename}</span>
        </p>
      </header>

      {/* Scrolls inside the card: a 40-column file must not make the page
          endless, and the action row below must stay reachable. */}
      <div className="scroll-x" style={{ maxHeight: '46vh', overflowY: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Your column</th>
              <th scope="col">Sample value</th>
              <th scope="col">Maps to</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {preview.detected_columns.map((column) => {
              const value = mapping[column.raw_column]
              const isDuplicate = value && duplicates.includes(value)
              const sample = preview.sample_rows?.[0]?.[column.raw_column]
              const guess = confidenceByColumn[column.raw_column]
              // A flagged row stays flagged until the user answers it themselves,
              // even though a server guess has already pre-filled the select —
              // an unexamined low-confidence pick is the whole risk here.
              const needsReview = guess?.needs_review && !reviewed.has(column.raw_column)

              return (
                <tr
                  key={column.raw_column}
                  style={needsReview ? { background: 'rgba(245,158,11,0.06)' } : undefined}
                >
                  <th scope="row">
                    <span className="block truncate" style={{ maxWidth: 180 }} title={column.raw_column}>
                      {column.raw_column}
                    </span>
                  </th>

                  <td className="font-mono text-[12px]" style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                    <span className="block truncate" style={{ maxWidth: 130 }} title={sample ?? ''}>
                      {sample ?? '—'}
                    </span>
                  </td>

                  <td style={{ textAlign: 'left' }}>
                    <select
                      value={value}
                      onChange={(event) => handleChange(column.raw_column, event.target.value)}
                      className="filter-select"
                      style={{ maxWidth: 190, borderColor: isDuplicate ? 'var(--accent-red)' : undefined }}
                      aria-label={`Map column ${column.raw_column} to a field`}
                    >
                      <option value="">Ignore this column</option>

                      <optgroup label="Required">
                        {requiredFields.map((field) => (
                          <option key={field} value={field} title={fieldHelp[field]}>
                            {field === 'MRP' ? 'List price (MRP)' : field}
                          </option>
                        ))}
                      </optgroup>

                      {optionalFields.some((field) => MEASURE_FIELDS.has(field)) && (
                        <optgroup label="Optional — extra amounts">
                          {optionalFields
                            .filter((field) => MEASURE_FIELDS.has(field))
                            .map((field) => (
                              <option key={field} value={field} title={fieldHelp[field]}>
                                {field === 'MRP' ? 'List price (MRP)' : field}
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
                                {field === 'MRP' ? 'List price (MRP)' : field}
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </select>

                    {/* Helper text for the chosen field: this screen is where a
                        wrong pick quietly corrupts every later number. */}
                    {value && fieldHelp[value] && !isDuplicate && (
                      <span
                        className="block text-[11.5px] mt-0.5 whitespace-normal"
                        style={{ color: 'var(--text-muted)', maxWidth: 190 }}
                      >
                        {fieldHelp[value]}
                      </span>
                    )}
                    {isDuplicate && (
                      <span className="block text-[11.5px] mt-0.5" style={{ color: 'var(--accent-red)' }}>
                        Already used by another column
                      </span>
                    )}
                  </td>

                  <td style={{ textAlign: 'left' }}>
                    <ConfidenceBadge column={guess} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <footer className="px-[var(--card-pad)] py-3 space-y-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {missingRequired.length > 0 && (
          <p className="text-xs" style={{ color: 'var(--accent-amber)' }}>
            Still need a column for: <strong>{missingRequired.join(', ')}</strong>
          </p>
        )}

        {hasLineTotal && !assignedFields.includes('Selling Price') && (
          <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No unit price mapped — we'll calculate it as Line Total ÷ Quantity, which keeps revenue correct instead of
            multiplying by quantity twice.
          </p>
        )}

        {mappedOptional.length > 0 && (
          <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            Extra features unlocked: <strong>{mappedOptional.join(', ')}</strong>
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
            Cancel
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
      </footer>
    </div>
  )
}

/**
 * What to trust this row by.
 *
 * `confidence` is the original contract and the floor: an older backend sends
 * only the `exact|fuzzy|none` string, and the new fields simply do not exist.
 * So the score, the band and the source are *additive detail* — present when
 * the 2-tier pipeline ran, absent otherwise, and never required to render
 * anything sensible.
 *
 * The band, not the score, drives the colour. A 0.42 is a different kind of
 * unsure from a 0.62, and a gradient of shades of amber would communicate that
 * distinction less clearly than three words would.
 */
const BAND_TONE = {
  high: { colour: 'var(--accent-green)', label: 'Confident' },
  medium: { colour: 'var(--accent-amber)', label: 'Likely' },
  low: { colour: 'var(--accent-red)', label: 'Check this' },
}

/** The wording an older backend's `exact|fuzzy|none` string has always had. */
const LEGACY_TONE = {
  exact: { colour: 'var(--accent-green)', label: 'Matched' },
  fuzzy: { colour: 'var(--accent-amber)', label: 'Check this' },
  none: { colour: 'var(--text-muted)', label: 'Not recognised' },
}

const SOURCE_LABEL = {
  gemini: 'AI',
  local: 'on-device',
  fallback: 'needs a human',
}

function ConfidenceBadge({ column }) {
  const legacy = LEGACY_TONE[column?.confidence] ?? LEGACY_TONE.none
  const tone = BAND_TONE[column?.confidence_band] ?? legacy

  const score = Number(column?.confidence_score)
  const hasScore = Number.isFinite(score) && score > 0
  const source = SOURCE_LABEL[column?.source]

  return (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <span
        className="inline-block text-[11.5px] font-semibold px-1.5 rounded-full whitespace-nowrap"
        style={{ color: tone.colour, border: `1px solid ${tone.colour}` }}
      >
        {tone.label}
      </span>

      {/* The score is a refinement of the word beside it, never a replacement:
          0.95 and the next one below it both read as "Confident" here. */}
      {hasScore && (
        <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {Math.round(score * 100)}%
        </span>
      )}

      {source && (
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }} title={`Decided by: ${column.source}`}>
          {source}
        </span>
      )}

      {column?.reason && (
        <span className="block w-full text-[11.5px] leading-snug mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {column.reason}
        </span>
      )}
    </span>
  )
}
