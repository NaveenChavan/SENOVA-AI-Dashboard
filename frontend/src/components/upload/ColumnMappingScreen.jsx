import { useMemo, useState, useEffect } from 'react'
import useSalesStore from '../../store/useSalesStore'

import Button from '../common/Button'
import Icon from '../common/Icon'
import { formatNumber } from '../charts/chartFormat'
import GroupedClarificationDialog from './GroupedClarificationDialog'
import ColumnNoteInput from './ColumnNoteInput'

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
const FALLBACK_REQUIRED = ['Date']
const FALLBACK_OPTIONAL = []

/** Optional fields that are numbers rather than dimensions, for grouping. */
const MEASURE_FIELDS = new Set(['Line Total', 'Discount', 'Tax', 'Stock On Hand', 'MRP'])


export function shouldStartTier2(preview, aiConsent) {
  return Boolean(
    preview?.ai_enabled &&
    aiConsent &&
    preview?.detected_columns?.some((column) => column?.route === 'gemini'),
  )
}

export default function ColumnMappingScreen({ preview, onConfirm, onCancel, submitting, initialOpenClarification = false }) {
  const requiredFields = preview.required_fields?.length ? preview.required_fields : FALLBACK_REQUIRED
  const optionalFields = preview.optional_fields?.length ? preview.optional_fields : FALLBACK_OPTIONAL
  const fieldHelp = preview.field_help ?? {}
  const allFields = useMemo(
    () => Array.from(new Set([...requiredFields, ...optionalFields])),
    [requiredFields, optionalFields],
  )

  const [mapping, setMapping] = useState(() => {
    const initial = {}
    for (const column of preview.detected_columns) {
      initial[column.raw_column] = column.suggested_field || ''
    }
    return initial
  })

  // Columns for which the user made an explicit personal choice (table dropdown or dialog)
  const [userSelected, setUserSelected] = useState(() => new Set())

  // Ambiguous columns that justify clarification
  const ambiguousColumns = useMemo(() => {
    return (preview.detected_columns || []).filter((col) => {
      if (col.recognised_unused) return false
      return (col.evidence_candidates && col.evidence_candidates.length > 0) || Boolean(col.needs_review)
    })
  }, [preview.detected_columns])

  const [clarificationOpen, setClarificationOpen] = useState(
    () => Boolean(initialOpenClarification && ambiguousColumns.length > 0),
  )
  const [rememberMapping, setRememberMapping] = useState(false)

  const aiConsent = useSalesStore((state) => state.aiConsent)
  const runTier2Async = useSalesStore((state) => state.runTier2Async)

  // Track if we're actively waiting for the background AI to finish
  const [checkingAi, setCheckingAi] = useState(() => {
    return shouldStartTier2(preview, aiConsent)
  })

  useEffect(() => {
    if (!checkingAi) return
    runTier2Async(preview.file_id).finally(() => {
      setCheckingAi(false)
    })
  }, [checkingAi, preview.file_id, runTier2Async])

  // ── Phase 4.1: "Check again with AI" ──────────────────────────────────────
  const forceRecheckTier2Async = useSalesStore((state) => state.forceRecheckTier2Async)
  const aiRecheckInFlight = useSalesStore((state) => state.aiRecheckInFlight)
  const [recheckMessage, setRecheckMessage] = useState(null)
  const [recheckCooldownUntil, setRecheckCooldownUntil] = useState(0)
  const [recheckClockTick, setRecheckClockTick] = useState(0)

  useEffect(() => {
    if (!recheckCooldownUntil) return
    const interval = setInterval(() => setRecheckClockTick((t) => t + 1), 1000)
    return () => clearInterval(interval)
  }, [recheckCooldownUntil])

  const recheckSecondsRemaining = Math.max(0, Math.ceil((recheckCooldownUntil - Date.now()) / 1000))

  const handleCheckAgain = async () => {
    const result = await forceRecheckTier2Async(preview.file_id)
    if (result?.cooldown) {
      setRecheckCooldownUntil(Date.now() + (result.retryAfterSeconds || 10) * 1000)
      setRecheckMessage(result.message)
      return
    }
    if (result?.error) {
      setRecheckMessage(result.error)
      return
    }
    setRecheckCooldownUntil(Date.now() + 10 * 1000)
    const evaluated = result?.columnsEvaluated ?? 0
    const resolved = result?.columnsResolved ?? 0
    // Only ever a real, measured count — never shown when nothing ran.
    setRecheckMessage(
      evaluated > 0 ? `AI looked at ${evaluated} column${evaluated === 1 ? '' : 's'}, resolved ${resolved}.` : null,
    )
  }

  // ── Phase 4.2: custom note per column ─────────────────────────────────────
  const submitColumnNotes = useSalesStore((state) => state.submitColumnNotes)
  const [columnNotes, setColumnNotes] = useState({})
  const [noteSuggestions, setNoteSuggestions] = useState({})
  const [notesSubmitting, setNotesSubmitting] = useState(false)

  const handleNoteChange = (rawColumn, note) => {
    setColumnNotes((previous) => ({ ...previous, [rawColumn]: note }))
  }

  const handleAskAiAboutNotes = async () => {
    const entries = Object.entries(columnNotes)
      .filter(([, note]) => note && note.trim().length > 0)
      .slice(0, 20)
      .map(([column, note]) => ({ column, note }))
    if (entries.length === 0) return

    setNotesSubmitting(true)
    try {
      const response = await submitColumnNotes(preview.file_id, entries)
      const byColumn = {}
      for (const suggestion of response?.suggestions || []) {
        byColumn[suggestion.column] = suggestion
      }
      setNoteSuggestions(byColumn)
    } finally {
      setNotesSubmitting(false)
    }
  }

  /**
   * Phase 4.2 fix: the three note-driven outcomes that are NOT a canonical
   * field. ``ignore`` has an existing, already-valid representation (the
   * empty-string "Ignore this column" option). ``extra_dimension`` /
   * ``extra_measure`` do not — the extra-column registry
   * (``extra_columns.classify_extra_columns``) decides those automatically,
   * deterministically, from the column's own data shape, *after*
   * confirm-mapping, for any column left unmapped here. There is no existing
   * API that lets this screen force a specific extra-column role onto the
   * registry, so the safe action is: leave the column unmapped (which lets
   * the real classifier decide) and say so plainly, rather than forcing the
   * literal AI role string into canonical mapping state where no dropdown
   * option matches it.
   */
  const NOTE_NON_CANONICAL_ROLES = new Set(['extra_dimension', 'extra_measure', 'ignore'])

  // Per-column note on what actually happened when a non-canonical
  // suggestion was applied, so "Use this" never looks like a no-op.
  const [noteOutcomeMessages, setNoteOutcomeMessages] = useState({})

  const handleApplyNoteSuggestion = (rawColumn, role) => {
    // Explicit confirmation already happened in ColumnNoteInput (the "Use
    // this" button, gated on the money-sensitive checkbox when applicable).
    // Only now does the suggestion become a real mapping change.
    if (NOTE_NON_CANONICAL_ROLES.has(role)) {
      // Always a safe, valid, already-supported state: unmapped. Never the
      // literal role string, which has no matching <option> and would leave
      // the select showing an unmatched value.
      handleChange(rawColumn, '')
      setNoteOutcomeMessages((previous) => ({
        ...previous,
        [rawColumn]:
          role === 'ignore'
            ? 'Set to "Ignore this column".'
            : `Left unmapped so it can be classified automatically as an ${role === 'extra_dimension' ? 'extra dimension' : 'extra measure'} based on its data, once you confirm.`,
      }))
    } else if (allFields.includes(role)) {
      handleChange(rawColumn, role)
      setNoteOutcomeMessages((previous) => {
        const next = { ...previous }
        delete next[rawColumn]
        return next
      })
    } else {
      // Defensive: a role that is neither a known canonical field nor one of
      // the three special outcomes should never reach this far (the backend
      // whitelist already rejects it), but if it ever did, refuse safely
      // rather than writing an unmatched value into mapping state.
      setNoteOutcomeMessages((previous) => ({
        ...previous,
        [rawColumn]: `"${role}" is not a supported mapping target. The current mapping was left unchanged.`,
      }))
      setNoteSuggestions((previous) => {
        const next = { ...previous }
        delete next[rawColumn]
        return next
      })
      return
    }
    setNoteSuggestions((previous) => {
      const next = { ...previous }
      delete next[rawColumn]
      return next
    })
  }

  // Update mapping state when preview.detected_columns updates (from Tier 2 response)
  useEffect(() => {
    setMapping((previous) => {
      const next = { ...previous }
      let changed = false
      for (const column of preview.detected_columns) {
        if (column.suggested_field && !previous[column.raw_column]) {
          next[column.raw_column] = column.suggested_field
          changed = true
        }
      }
      return changed ? next : previous
    })
  }, [preview.detected_columns])

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
   * Section 1.2 Two-field upload rule:
   * Require only Date + Line Total (Path A) OR Date + Quantity + Selling Price (Path B).
   * Category, Item, Cost Price, MRP, Discount, Tax, etc., are strictly optional for upload confirmation.
   */
  const hasDate = assignedFields.includes('Date')
  const hasLineTotal = assignedFields.includes('Line Total')
  const hasQuantity = assignedFields.includes('Quantity')
  const hasSellingPrice = assignedFields.includes('Selling Price')

  const meetsTwoFieldRule = hasDate && (hasLineTotal || (hasQuantity && hasSellingPrice))
  const canSubmit = duplicates.length === 0 && meetsTwoFieldRule && !submitting

  const missingRequirements = []
  if (!hasDate) {
    missingRequirements.push('Date')
  }
  if (!hasLineTotal && !(hasQuantity && hasSellingPrice)) {
    if (!hasQuantity && !hasSellingPrice) {
      missingRequirements.push('Line Total (or Quantity + Selling Price)')
    } else if (!hasQuantity) {
      missingRequirements.push('Quantity (or Line Total)')
    } else {
      missingRequirements.push('Selling Price (or Line Total)')
    }
  }

  const unmappedCoreOptional = ['Category', 'Item', 'Cost Price'].filter(
    (field) => !assignedFields.includes(field),
  )

  const mappedOptional = optionalFields.filter((field) => assignedFields.includes(field))

  const handleChange = (rawColumn, value) => {
    setMapping((previous) => ({ ...previous, [rawColumn]: value }))
    setReviewed((previous) => (previous.has(rawColumn) ? previous : new Set(previous).add(rawColumn)))
    setUserSelected((previous) => (previous.has(rawColumn) ? previous : new Set(previous).add(rawColumn)))
  }

  const handleApplyClarification = (selectedChanges, clarificationNotes, explicitlyTouched) => {
    const touched = explicitlyTouched || new Set(Object.keys(selectedChanges))

    setMapping((previous) => {
      const next = { ...previous }
      for (const [col, val] of Object.entries(selectedChanges)) {
        if (val !== undefined) {
          next[col] = val
        }
      }
      return next
    })
    setReviewed((previous) => {
      const next = new Set(previous)
      for (const col of touched) {
        next.add(col)
      }
      return next
    })
    setUserSelected((previous) => {
      const next = new Set(previous)
      for (const col of touched) {
        next.add(col)
      }
      return next
    })
    setClarificationOpen(false)
  }

  const unreviewedAmbiguousCount = ambiguousColumns.filter((c) => !reviewed.has(c.raw_column)).length

  return (
    <div className="card">
      <header className="px-[var(--card-pad)] py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <h2>Confirm your columns</h2>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          Every shop's spreadsheet is a little different. Check the guesses below and fix anything that's wrong.
        </p>
        <p className="text-[12px] mt-1 flex items-center justify-between" style={{ color: 'var(--text-muted)' }}>
          <span>
            {formatNumber(preview.row_count)} row{preview.row_count === 1 ? '' : 's'} detected in{' '}
            <span className="font-medium">{preview.filename}</span>
          </span>
          {checkingAi && (
            <span className="text-xs font-medium" style={{ color: 'var(--accent-blue)' }}>
              AI is checking {preview.detected_columns.filter(c => c.route === 'gemini').length} column(s)...
            </span>
          )}
        </p>
      </header>

      {/* Module 2.2 Clarification Banner */}
      {ambiguousColumns.length > 0 && (
        <div
          className="mx-[var(--card-pad)] my-2 p-2.5 rounded-lg flex flex-wrap items-center justify-between gap-2"
          style={{
            background: 'rgba(59,130,246,0.08)',
            border: '1px solid rgba(59,130,246,0.25)',
          }}
          data-testid="clarification-banner"
        >
          <div className="flex items-center gap-2">
            <span
              className="w-5 h-5 rounded-full flex items-center justify-center shrink-0"
              style={{ background: 'rgba(59,130,246,0.18)', color: 'var(--accent-blue)' }}
            >
              <Icon name="spark" className="w-3 h-3" />
            </span>
            <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
              {unreviewedAmbiguousCount > 0
                ? `${unreviewedAmbiguousCount} column(s) need clarification based on data evidence.`
                : 'All ambiguous columns have been reviewed.'}
            </span>
          </div>

          <Button
            type="button"
            variant="secondary"
            className="text-xs py-1 px-2.5"
            onClick={() => setClarificationOpen(true)}
          >
            Clarify columns ({ambiguousColumns.length})
          </Button>
        </div>
      )}

      {/* Phase 4.1: Check again with AI — only offered when something is
          still unresolved after the automatic pass. */}
      {(() => {
        const stillUnresolved = preview.detected_columns.filter(
          (c) => c.needs_review && !c.recognised_unused,
        ).length
        if (stillUnresolved === 0) return null

        let disabledReason = null
        if (!preview.ai_enabled) disabledReason = 'AI is switched off on this server.'
        else if (!aiConsent) disabledReason = 'AI was not approved for this upload.'
        else if (recheckSecondsRemaining > 0) disabledReason = `Wait ${recheckSecondsRemaining}s before checking again.`
        else if (aiRecheckInFlight) disabledReason = 'Checking…'

        return (
          <div
            className="mx-[var(--card-pad)] my-2 p-2.5 rounded-lg flex flex-wrap items-center justify-between gap-2"
            style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}
            data-testid="check-again-banner"
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                {stillUnresolved} column{stillUnresolved === 1 ? '' : 's'} still unresolved.
              </span>
              {recheckMessage && (
                <span className="text-[11.5px]" style={{ color: 'var(--text-muted)' }} data-testid="check-again-message">
                  {recheckMessage}
                </span>
              )}
            </div>
            <Button
              type="button"
              variant="secondary"
              className="text-xs py-1 px-2.5"
              onClick={handleCheckAgain}
              disabled={Boolean(disabledReason)}
              loading={aiRecheckInFlight}
              title={disabledReason || 'Ask AI to look again at the unresolved columns'}
              data-testid="check-again-button"
            >
              <Icon name="refresh" className="w-3.5 h-3.5" />
              Check again with AI
            </Button>
            {disabledReason && (
              <span className="text-[11px] w-full" style={{ color: 'var(--text-muted)' }} data-testid="check-again-disabled-reason">
                {disabledReason}
              </span>
            )}
          </div>
        )
      })()}

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

                    {/* Phase 4.2: a note is only offered for a column that
                        still needs review — a confidently-matched column has
                        no ambiguity for a note to resolve. */}
                    {needsReview && (
                      <ColumnNoteInput
                        column={column.raw_column}
                        existingNote={columnNotes[column.raw_column]}
                        suggestion={noteSuggestions[column.raw_column]}
                        onNoteChange={handleNoteChange}
                        onApply={handleApplyNoteSuggestion}
                        disabled={notesSubmitting}
                      />
                    )}
                    {noteOutcomeMessages[column.raw_column] && (
                      <span
                        className="block text-[11px] mt-1 whitespace-normal"
                        style={{ color: 'var(--text-muted)', maxWidth: 220 }}
                        data-testid={`note-outcome-${column.raw_column}`}
                      >
                        {noteOutcomeMessages[column.raw_column]}
                      </span>
                    )}
                  </td>

                  <td style={{ textAlign: 'left' }}>
                    <ConfidenceBadge column={guess} isUserChoice={userSelected.has(column.raw_column)} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <footer className="px-[var(--card-pad)] py-3 space-y-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {missingRequirements.length > 0 && (
          <p className="text-xs" style={{ color: 'var(--accent-amber)' }}>
            Still need a column for: <strong>{missingRequirements.join(' and ')}</strong>
          </p>
        )}

        {missingRequirements.length === 0 && unmappedCoreOptional.length > 0 && (
          <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Optional columns not mapped: <strong>{unmappedCoreOptional.join(', ')}</strong> — views requiring these will show &quot;Not available&quot; rather than fabricating numbers.
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

        {Object.values(columnNotes).some((note) => note && note.trim().length > 0) && preview.ai_enabled && aiConsent && (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              className="text-xs py-1 px-2.5"
              onClick={handleAskAiAboutNotes}
              loading={notesSubmitting}
              data-testid="ask-ai-about-notes-button"
            >
              <Icon name="spark" className="w-3.5 h-3.5" />
              Ask AI about my notes
            </Button>
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Up to 20 columns, one request.
            </span>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-2 sm:justify-between sm:items-center pt-2">
          <label className="flex items-center gap-2 text-xs cursor-pointer select-none" style={{ color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={rememberMapping}
              onChange={(e) => setRememberMapping(e.target.checked)}
              className="rounded"
              data-testid="remember-mapping-checkbox"
            />
            <span>Remember approved mappings for this template next time (opt-in)</span>
          </label>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={!canSubmit}
              loading={submitting}
              onClick={() => onConfirm(mapping, Array.from(userSelected), rememberMapping)}
            >
              Confirm &amp; analyse
            </Button>
          </div>
        </div>
      </footer>

      <GroupedClarificationDialog
        open={clarificationOpen}
        columns={ambiguousColumns}
        sampleRows={preview.sample_rows || []}
        fieldHelp={fieldHelp}
        allFields={allFields}
        currentMapping={mapping}
        onApply={handleApplyClarification}
        onSkip={() => setClarificationOpen(false)}
      />
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
  dictionary: 'From dictionary',
  fallback: 'needs a human',
  evidence: 'deterministic',
  memory: 'saved memory',
}

function ConfidenceBadge({ column, isUserChoice }) {
  const legacy = LEGACY_TONE[column?.confidence] ?? LEGACY_TONE.none
  let tone = BAND_TONE[column?.confidence_band] ?? legacy

  if (isUserChoice) {
    tone = { colour: 'var(--accent-blue)', label: 'User choice' }
  } else if (column?.source === 'memory') {
    tone = { colour: 'var(--accent-purple, #8b5cf6)', label: 'Memory' }
  } else if (column?.recognised_unused) {
    tone = { colour: 'var(--text-muted)', label: 'Recognised, not analysed' }
  }

  const score = Number(column?.confidence_score)
  const hasScore = Number.isFinite(score) && score > 0
  const source = isUserChoice
    ? 'from your selection'
    : (SOURCE_LABEL[column?.source] || column?.source)

  const reason = isUserChoice
    ? 'You selected this mapping.'
    : (column?.recognised_unused
        ? 'We know what this is. It is not used in the numbers. You can still map it by hand.'
        : column?.reason)

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
      {hasScore && !column?.recognised_unused && !isUserChoice && (
        <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {Math.round(score * 100)}%
        </span>
      )}

      {source && !column?.recognised_unused && (
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }} title={`Decided by: ${source}`}>
          {source}
        </span>
      )}

      {reason && (
        <span className="block w-full text-[11.5px] leading-snug mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {reason}
        </span>
      )}
    </span>
  )
}
