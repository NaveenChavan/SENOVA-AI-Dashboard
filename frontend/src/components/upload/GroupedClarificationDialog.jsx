import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'motion/react'

import Button from '../common/Button'
import Icon from '../common/Icon'

/**
 * Sanitize user-typed clarification notes.
 * Strips non-printable control characters, trims, and enforces max length.
 */
function sanitizeNote(text) {
  if (!text) return ''
  return String(text)
    .replace(/[\x00-\x1F\x7F]/g, '')
    .trim()
    .slice(0, 150)
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function getFocusableElements(container) {
  if (!container) return []
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter((el) => {
    if (el.disabled || el.getAttribute('aria-hidden') === 'true') return false
    return true
  })
}

/**
 * Grouped Clarification Dialog (Module 2.2).
 *
 * Sits as a single modal dialog for all open ambiguous column questions
 * rather than displaying separate per-column popups.
 *
 * Guarantees:
 * - Uses one grouped dialog for all ambiguous headers.
 * - Prioritizes evidence-based candidates from `column.evidence_candidates`.
 * - Renders only pre-masked values from `sampleRows` (never requests or exposes raw PII).
 * - Provides "Something else (type a note)" with sanitized clarification notes and explicit role selection.
 * - Provides per-column and dialog-level "Skip for now" without resetting or blocking valid Phase 1 uploads.
 * - Keeps keyboard focus trapped inside the dialog with Tab / Shift+Tab wrapping.
 * - Restores focus to the opener element when dismissed.
 */
export default function GroupedClarificationDialog({
  open,
  columns = [],
  sampleRows = [],
  fieldHelp = {},
  allFields = [],
  currentMapping = {},
  onApply,
  onSkip,
}) {
  const dialogRef = useRef(null)
  const onSkipRef = useRef(onSkip)
  onSkipRef.current = onSkip
  const previouslyFocusedRef = useRef(null)

  const [prevOpen, setPrevOpen] = useState(open)
  const [touchedColumns, setTouchedColumns] = useState(() => new Set())

  // Staged mapping selections inside the dialog: { [raw_column]: canonicalField }
  const [stagedMapping, setStagedMapping] = useState(() => {
    const initial = {}
    for (const col of columns) {
      initial[col.raw_column] = currentMapping[col.raw_column] || ''
    }
    return initial
  })

  // Clarification notes: { [raw_column]: noteString }
  const [notes, setNotes] = useState({})

  // Toggle for "Something else" section per column: { [raw_column]: boolean }
  const [expandedNotes, setExpandedNotes] = useState({})

  // Synchronize staged selections with currentMapping whenever dialog opens or reopens,
  // without resetting deliberate in-dialog edits while the dialog remains open.
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      const initial = {}
      for (const col of columns) {
        initial[col.raw_column] = currentMapping[col.raw_column] || ''
      }
      setStagedMapping(initial)
      setTouchedColumns(new Set())
      setNotes({})
      setExpandedNotes({})
    }
  }

  // Focus trap, focus containment, and focus restoration
  useEffect(() => {
    if (!open) return

    // Remember the element that had focus before the dialog opened
    previouslyFocusedRef.current = document.activeElement

    // Move initial focus inside the dialog to the first focusable element
    const dialogEl = dialogRef.current
    if (dialogEl) {
      const focusables = getFocusableElements(dialogEl)
      if (focusables.length > 0) {
        focusables[0].focus()
      } else {
        dialogEl.focus()
      }
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onSkipRef.current?.()
        return
      }

      if (e.key === 'Tab') {
        const dialogEl = dialogRef.current
        if (!dialogEl) return

        const focusables = getFocusableElements(dialogEl)
        if (focusables.length === 0) {
          e.preventDefault()
          dialogEl.focus()
          return
        }

        const firstElement = focusables[0]
        const lastElement = focusables[focusables.length - 1]
        const isInsideFocusables = focusables.includes(document.activeElement)

        if (!isInsideFocusables) {
          e.preventDefault()
          if (e.shiftKey) {
            lastElement.focus()
          } else {
            firstElement.focus()
          }
          return
        }

        if (e.shiftKey) {
          // Shift + Tab on first focusable element wraps to last focusable element
          if (document.activeElement === firstElement) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          // Tab on last focusable element wraps to first focusable element
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    }

    // Keep focus contained inside the dialog if user attempts to focus outside
    const handleFocusIn = (e) => {
      const dialogEl = dialogRef.current
      if (dialogEl && !dialogEl.contains(e.target)) {
        const focusables = getFocusableElements(dialogEl)
        if (focusables.length > 0) {
          focusables[0].focus()
        } else {
          dialogEl.focus()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    document.addEventListener('focusin', handleFocusIn)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('focusin', handleFocusIn)

      // When the dialog closes (via Escape, close button, backdrop, or Skip),
      // restore focus to the opener element if it still exists in the DOM.
      const opener = previouslyFocusedRef.current
      if (
        opener &&
        opener !== document.body &&
        typeof opener.focus === 'function' &&
        document.body.contains(opener)
      ) {
        opener.focus()
      }
      previouslyFocusedRef.current = null
    }
  }, [open])


  const handleSelectRole = (rawColumn, role) => {
    setStagedMapping((prev) => ({
      ...prev,
      [rawColumn]: role,
    }))
    setTouchedColumns((prev) => {
      const next = new Set(prev)
      next.add(rawColumn)
      return next
    })
  }

  const handleNoteChange = (rawColumn, rawText) => {
    const clean = sanitizeNote(rawText)
    setNotes((prev) => ({
      ...prev,
      [rawColumn]: clean,
    }))
  }

  const toggleSomethingElse = (rawColumn) => {
    setExpandedNotes((prev) => ({
      ...prev,
      [rawColumn]: !prev[rawColumn],
    }))
  }

  const handleApply = () => {
    // Only apply mappings for columns the user explicitly changed or ignored in the dialog
    const changes = {}
    for (const col of touchedColumns) {
      changes[col] = stagedMapping[col] ?? ''
    }
    const cleanedNotes = {}
    for (const [col, noteText] of Object.entries(notes)) {
      const sanitized = sanitizeNote(noteText)
      if (sanitized) cleanedNotes[col] = sanitized
    }
    onApply(changes, cleanedNotes)
  }

  // Pre-filter non-empty masked samples for a given column (max 3)
  const getMaskedSamples = (rawColumn) => {
    const samples = []
    for (const row of sampleRows) {
      const val = row?.[rawColumn]
      if (val !== null && val !== undefined && val !== '') {
        samples.push(String(val))
        if (samples.length >= 3) break
      }
    }
    return samples
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6"
      data-testid="grouped-clarification-dialog"
    >
      {/* Backdrop: clicking outside calls onSkip (does not wipe mappings) */}
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.55)' }}
        onClick={onSkip}
        aria-hidden="true"
      />

          <motion.div
            ref={dialogRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby="clarification-dialog-title"
            className="relative w-full rounded-xl flex flex-col focus:outline-none"
            style={{
              maxWidth: 680,
              maxHeight: '90vh',
              background: 'var(--bg-card-solid)',
              border: '1px solid var(--border-subtle)',
              boxShadow: 'var(--shadow-high)',
            }}
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 14, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* Header */}
            <header
              className="px-5 py-4 border-b flex items-start justify-between gap-3 shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className="w-6 h-6 rounded-full flex items-center justify-center shrink-0"
                    style={{ background: 'rgba(59,130,246,0.15)', color: 'var(--accent-blue)' }}
                  >
                    <Icon name="spark" className="w-3.5 h-3.5" />
                  </span>
                  <h2 id="clarification-dialog-title" className="text-base font-semibold">
                    Clarify ambiguous columns
                  </h2>
                </div>
                <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                  We found {columns.length} column{columns.length === 1 ? '' : 's'} where data evidence points to multiple possible meanings. Review our recommendations or skip to proceed.
                </p>
              </div>

              <button
                type="button"
                onClick={onSkip}
                className="text-xs px-2 py-1 rounded transition-colors"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Close dialog without saving"
              >
                ✕
              </button>
            </header>

            {/* Scrollable list of ambiguous columns */}
            <div className="p-5 space-y-4 overflow-y-auto scroll-x flex-1">
              {columns.map((column) => {
                const raw = column.raw_column
                const samples = getMaskedSamples(raw)
                const currentSelection = stagedMapping[raw] || ''
                const evidenceCandidates = column.evidence_candidates || []
                const reasonText = column.evidence_reason || column.reason
                const evidenceFacts = column.evidence_facts || []

                // Extra non-evidence alternatives if present (strictly distinguished)
                const extraAlternatives = (column.alternatives || [])
                  .map((alt) => (typeof alt === 'object' ? alt.field || alt.label : alt))
                  .filter((alt) => alt && !evidenceCandidates.includes(alt))

                const isSomethingElseExpanded = Boolean(expandedNotes[raw])

                return (
                  <div
                    key={raw}
                    className="p-4 rounded-lg space-y-3"
                    style={{
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border-subtle)',
                    }}
                    data-testid={`clarification-card-${raw}`}
                  >
                    {/* Column Name & Current Status */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                          {raw}
                        </span>
                        {currentSelection ? (
                          <span
                            className="text-[11px] font-medium px-2 py-0.5 rounded-full"
                            style={{
                              background: 'rgba(59,130,246,0.12)',
                              color: 'var(--accent-blue)',
                              border: '1px solid var(--accent-blue)',
                            }}
                          >
                            Selected: {currentSelection}
                          </span>
                        ) : (
                          <span
                            className="text-[11px] font-medium px-2 py-0.5 rounded-full"
                            style={{
                              background: 'rgba(156,163,175,0.12)',
                              color: 'var(--text-muted)',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            Unmapped
                          </span>
                        )}
                      </div>

                      {/* Button to quickly skip/ignore this column */}
                      <button
                        type="button"
                        onClick={() => handleSelectRole(raw, '')}
                        className="text-[11px] underline"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        Ignore this column
                      </button>
                    </div>

                    {/* Pre-masked sample values representation */}
                    <div className="text-xs flex items-baseline gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <span className="font-medium shrink-0">Sample values:</span>
                      {samples.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
                          {samples.map((val, idx) => (
                            <span
                              key={idx}
                              className="px-1.5 py-0.5 rounded"
                              style={{ background: 'var(--bg-card-solid)', border: '1px solid var(--border-subtle)' }}
                              title={val}
                            >
                              {val}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="italic">—</span>
                      )}
                    </div>

                    {/* Evidence reason & facts */}
                    {reasonText && (
                      <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                        {reasonText}
                      </p>
                    )}

                    {evidenceFacts.length > 0 && (
                      <ul className="text-[11.5px] list-disc list-inside space-y-0.5 pl-1" style={{ color: 'var(--text-muted)' }}>
                        {evidenceFacts.map((fact, idx) => (
                          <li key={idx}>{fact}</li>
                        ))}
                      </ul>
                    )}

                    {/* Candidate Roles Selection */}
                    <div className="space-y-1.5 pt-1">
                      <span className="text-[11px] font-medium block" style={{ color: 'var(--text-secondary)' }}>
                        {evidenceCandidates.length > 0
                          ? 'Recommended candidates (based on data evidence):'
                          : 'Suggested candidates:'}
                      </span>

                      <div className="flex flex-wrap gap-2">
                        {evidenceCandidates.map((candidate) => {
                          const isSelected = currentSelection === candidate
                          return (
                            <button
                              key={candidate}
                              type="button"
                              onClick={() => handleSelectRole(raw, candidate)}
                              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5"
                              style={{
                                background: isSelected ? 'var(--gradient-accent)' : 'var(--bg-card-solid)',
                                color: isSelected ? '#ffffff' : 'var(--text-primary)',
                                border: isSelected ? '1px solid transparent' : '1px solid var(--border-subtle)',
                                boxShadow: isSelected ? 'var(--shadow-glow)' : 'none',
                              }}
                              title={fieldHelp[candidate] || candidate}
                            >
                              <Icon name="check" className={`w-3 h-3 ${isSelected ? 'opacity-100' : 'opacity-0'}`} />
                              <span>{candidate}</span>
                            </button>
                          )
                        })}

                        {/* Clearly distinguished other alternatives (not auto-selected) */}
                        {extraAlternatives.map((alt) => {
                          const isSelected = currentSelection === alt
                          return (
                            <button
                              key={alt}
                              type="button"
                              onClick={() => handleSelectRole(raw, alt)}
                              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 opacity-80 hover:opacity-100"
                              style={{
                                background: isSelected ? 'var(--accent-blue)' : 'var(--bg-card-solid)',
                                color: isSelected ? '#ffffff' : 'var(--text-secondary)',
                                border: isSelected ? '1px solid transparent' : '1px dashed var(--border-subtle)',
                              }}
                              title={`Alternative option: ${alt}`}
                            >
                              <span className="text-[10px] text-muted italic">Alt:</span>
                              <span>{alt}</span>
                            </button>
                          )
                        })}
                      </div>
                    </div>

                    {/* "Something else (type a note)" section */}
                    <div className="pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                      <button
                        type="button"
                        onClick={() => toggleSomethingElse(raw)}
                        className="text-xs font-medium flex items-center gap-1 transition-colors"
                        style={{ color: 'var(--accent-blue)' }}
                      >
                        <span>{isSomethingElseExpanded ? '▾' : '▸'}</span>
                        <span>Something else (type a note or choose another role)</span>
                      </button>

                      {isSomethingElseExpanded && (
                        <div
                          className="mt-2.5 p-3 rounded-lg space-y-2.5"
                          style={{
                            background: 'var(--bg-card-solid)',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          <div>
                            <label
                              htmlFor={`note-${raw}`}
                              className="block text-[11px] font-medium mb-1"
                              style={{ color: 'var(--text-secondary)' }}
                            >
                              Clarification note (optional):
                            </label>
                            <input
                              id={`note-${raw}`}
                              type="text"
                              value={notes[raw] || ''}
                              onChange={(e) => handleNoteChange(raw, e.target.value)}
                              placeholder="e.g. Delivery surcharge or vendor code"
                              maxLength={150}
                              className="w-full text-xs px-2.5 py-1.5 rounded-md"
                              style={{
                                background: 'var(--bg-input)',
                                border: '1px solid var(--border-subtle)',
                                color: 'var(--text-primary)',
                              }}
                            />
                            <span className="text-[10px] block mt-0.5 text-right" style={{ color: 'var(--text-muted)' }}>
                              {(notes[raw] || '').length}/150
                            </span>
                          </div>

                          <div>
                            <label
                              htmlFor={`role-select-${raw}`}
                              className="block text-[11px] font-medium mb-1"
                              style={{ color: 'var(--text-secondary)' }}
                            >
                              Map to a specific canonical role:
                            </label>
                            <select
                              id={`role-select-${raw}`}
                              value={currentSelection}
                              onChange={(e) => handleSelectRole(raw, e.target.value)}
                              className="filter-select w-full text-xs"
                              aria-label={`Select canonical role for ${raw}`}
                            >
                              <option value="">Ignore this column</option>
                              {allFields.map((field) => (
                                <option key={field} value={field}>
                                  {field}
                                </option>
                              ))}
                            </select>
                            <p className="text-[10.5px] mt-1" style={{ color: 'var(--text-muted)' }}>
                              Note: Typing a free-text note does not map the column. An explicit role selection from the list is required.
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Footer with Skip for now & Apply mappings */}
            <footer
              className="px-5 py-3 border-t flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <p className="text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                Skipping clarification will not block upload if required Date + Amount columns are already mapped.
              </p>

              <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                <Button type="button" variant="secondary" onClick={onSkip}>
                  Skip for now
                </Button>
                <Button type="button" variant="primary" onClick={handleApply}>
                  Apply mappings
                </Button>
              </div>
            </footer>
          </motion.div>
        </div>
  )
}
