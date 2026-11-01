import { useState } from 'react'
import Button from '../common/Button'
import Icon from '../common/Icon'

/**
 * Phase 4.2 — one short note per still-unmapped column, plus the AI
 * suggestion it produces and the explicit confirmation gate before anything
 * is applied.
 *
 * Nothing here ever writes to ``mapping`` on its own. A suggestion is only a
 * proposal: the user must press "Use this" (and, for a money-sensitive role,
 * tick the extra box) before ``onApply`` is called. Declining, or AI being
 * off/unavailable, always leaves the note itself as a plain label the user
 * can still act on through the ordinary dropdown — this component never
 * blocks that path.
 */

const MAX_NOTE_LENGTH = 200

export default function ColumnNoteInput({ column, existingNote, suggestion, onNoteChange, onApply, disabled }) {
  const [draft, setDraft] = useState(existingNote || '')
  const [moneyConfirmed, setMoneyConfirmed] = useState(false)

  const commit = (value) => {
    const trimmed = value.slice(0, MAX_NOTE_LENGTH)
    if (trimmed !== draft) setDraft(trimmed)
    onNoteChange?.(column, trimmed)
  }

  const handleBlur = () => commit(draft)

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter') return
    // Commit the current draft immediately so a note-resolution action
    // triggered right after this keypress (e.g. a sibling "Ask AI" button
    // activated via keyboard) sees the just-typed text, not a stale value
    // from before the last blur. This is a plain <input>, not a <form>, so
    // there is no submit behaviour to suppress — preventDefault only stops
    // this keypress from doing anything else (like a parent form, if this
    // input is ever nested inside one in the future).
    event.preventDefault()
    commit(event.target.value)
  }

  const canApply = suggestion && (!suggestion.money_sensitive || moneyConfirmed)

  return (
    <div className="flex flex-col gap-1 mt-1" style={{ maxWidth: 220 }}>
      <label className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
        Add a note (optional)
        <input
          type="text"
          value={draft}
          maxLength={MAX_NOTE_LENGTH}
          placeholder="e.g. this is the delivery charge"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          className="filter-select mt-0.5 w-full text-[12px]"
          data-testid={`column-note-input-${column}`}
          aria-label={`Note for column ${column}`}
        />
      </label>

      {suggestion && (
        <div
          className="text-[11.5px] p-1.5 rounded flex flex-col gap-1"
          style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)' }}
          data-testid={`note-suggestion-${column}`}
        >
          <span style={{ color: 'var(--text-primary)' }}>
            AI suggests: <strong>{suggestion.role}</strong>
          </span>
          {suggestion.reason && (
            <span style={{ color: 'var(--text-muted)' }}>{suggestion.reason}</span>
          )}

          {suggestion.money_sensitive && (
            <label className="flex items-start gap-1.5 cursor-pointer select-none" style={{ color: 'var(--accent-amber)' }}>
              <input
                type="checkbox"
                checked={moneyConfirmed}
                onChange={(e) => setMoneyConfirmed(e.target.checked)}
                className="mt-0.5"
                data-testid={`money-confirm-${column}`}
              />
              <span>
                This affects money calculations ({suggestion.role}). I confirm this is correct.
              </span>
            </label>
          )}

          <div className="flex gap-1.5 mt-0.5">
            <Button
              type="button"
              variant="primary"
              className="text-[11px] py-0.5 px-2"
              disabled={!canApply}
              onClick={() => onApply?.(column, suggestion.role)}
              data-testid={`apply-suggestion-${column}`}
            >
              <Icon name="check" className="w-3 h-3" />
              Use this
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
