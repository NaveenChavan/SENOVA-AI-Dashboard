import { useEffect, useMemo, useRef, useState } from 'react'

import Icon from './Icon'

/**
 * Command palette (⌘K / Ctrl-K).
 *
 * On a dashboard with three tabs, five date presets, eight chart types, eight
 * measures and a filter panel, every action is two or three clicks away and
 * spread across the screen. A palette collapses all of them into one keystroke
 * and a few letters — the single biggest speed gain for someone who uses the
 * dashboard daily, and it doubles as a discoverability list for someone who
 * doesn't know a feature exists.
 *
 * The parent owns the actions; this component only handles opening, filtering,
 * keyboard navigation and focus. Actions are plain objects so they stay
 * testable without rendering the whole page.
 */
export default function CommandPalette({ actions = [] }) {
  const [open, setOpen] = useState(false)
  const [queryText, setQueryText] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  // ⌘K / Ctrl-K opens; Escape closes. Registered once, globally, so the
  // shortcut works no matter where focus currently is.
  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((previous) => !previous)
        return
      }
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (!open) return
    setQueryText('')
    setActiveIndex(0)
    // Focus after paint so the caret lands in the field, not on the backdrop.
    const timer = window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => window.clearTimeout(timer)
  }, [open])

  /**
   * Subsequence match, not substring: "cbr" finds "Chart: Bars", which is how
   * people actually type in a palette.
   */
  const results = useMemo(() => {
    const needle = queryText.trim().toLowerCase()
    if (!needle) return actions.slice(0, 40)

    return actions
      .filter((action) => {
        const haystack = `${action.group ?? ''} ${action.label} ${action.hint ?? ''}`.toLowerCase()
        let cursor = 0
        for (const character of needle) {
          if (character === ' ') continue
          cursor = haystack.indexOf(character, cursor)
          if (cursor === -1) return false
          cursor += 1
        }
        return true
      })
      .slice(0, 40)
  }, [actions, queryText])

  useEffect(() => {
    // Keep the highlight inside the (possibly shorter) filtered list.
    setActiveIndex((index) => Math.min(index, Math.max(results.length - 1, 0)))
  }, [results.length])

  const run = (action) => {
    setOpen(false)
    action?.run?.()
  }

  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => (index + 1) % Math.max(results.length, 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => (index - 1 + results.length) % Math.max(results.length, 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      run(results[activeIndex])
    }
  }

  if (!open) return null

  return (
    <div className="palette-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="palette__input"
          placeholder="Jump to a view, date range, chart or measure…"
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-label="Search commands"
          aria-controls="palette-list"
          autoComplete="off"
        />

        <div id="palette-list" ref={listRef} role="listbox" className="overflow-y-auto">
          {results.length === 0 ? (
            <p className="px-3.5 py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
              Nothing matches “{queryText}”.
            </p>
          ) : (
            results.map((action, index) => (
              <button
                key={action.id}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className="palette__item"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => run(action)}
              >
                {action.icon && <Icon name={action.icon} className="w-3.5 h-3.5 shrink-0" />}
                <span className="truncate">
                  {action.group && (
                    <span style={{ color: 'var(--text-muted)' }}>{action.group} · </span>
                  )}
                  {action.label}
                </span>
                {action.hint && (
                  <span className="ml-auto text-[11px] shrink-0" style={{ color: 'var(--text-muted)' }}>
                    {action.hint}
                  </span>
                )}
              </button>
            ))
          )}
        </div>

        <footer
          className="flex items-center gap-3 px-3.5 py-2 text-[11px]"
          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
        >
          <span>↑↓ to move</span>
          <span>↵ to run</span>
          <span>esc to close</span>
        </footer>
      </div>
    </div>
  )
}
