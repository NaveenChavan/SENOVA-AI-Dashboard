import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'

import Icon from '../common/Icon'

/**
 * Compact filter row restored to the original dashboard visual language.
 * The row itself remains visible while scrolling Inventory, but the opened
 * filter controls float above the page instead of expanding the document.
 */
export default function FilterPanel({
  dimensions = [],
  filters = {},
  onChange,
  dateRange,
  customRange,
  onCustomRangeChange,
  onClear,
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  const hasCustomRange = Boolean(customRange?.start && customRange?.end)
  const activeGroupCount = useMemo(
    () => Object.keys(filters ?? {}).filter((key) => Array.isArray(filters?.[key]) && filters[key].length > 0).length + (hasCustomRange ? 1 : 0),
    [filters, hasCustomRange],
  )

  useEffect(() => {
    if (!open) return undefined

    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggleValue = (key, value) => {
    const current = filters[key] ?? []
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value]

    const updated = { ...filters }
    if (next.length) updated[key] = next
    else delete updated[key]
    onChange?.(updated)
  }

  const removeDimension = (key) => {
    const updated = { ...filters }
    delete updated[key]
    onChange?.(updated)
  }

  return (
    <section ref={rootRef} className="filter-bar" aria-label="Filters">
      <div className="filter-bar__row">
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          aria-expanded={open}
          className="btn"
        >
          <Icon name="filter" className="w-3.5 h-3.5" />
          Filters
          {activeGroupCount > 0 && (
            <span className="filter-bar__count" aria-label={`${activeGroupCount} active filter groups`}>
              {activeGroupCount}
            </span>
          )}
        </button>

        <div className="filter-bar__chips" aria-label="Active filters">
          {Object.entries(filters).map(([key, values]) => {
            const dimension = dimensions.find((option) => option.key === key)
            if (!Array.isArray(values) || values.length === 0) return null
            return (
              <button
                key={key}
                type="button"
                onClick={() => removeDimension(key)}
                className="chip chip--active"
                aria-label={`Remove ${dimension?.label ?? key} filter`}
              >
                <span className="font-semibold">{dimension?.label ?? key}:</span>
                <span className="truncate" style={{ maxWidth: 140 }}>
                  {values.length === 1 ? values[0] : `${values.length} selected`}
                </span>
                <Icon name="close" className="w-3 h-3" />
              </button>
            )
          })}

          {hasCustomRange && (
            <span className="chip chip--static">
              <Icon name="calendar" className="w-3 h-3" />
              {customRange.start} → {customRange.end}
            </span>
          )}
        </div>

        {(activeGroupCount > 0) && (
          <button
            type="button"
            onClick={onClear}
            className="filter-bar__clear"
          >
            Clear all
          </button>
        )}
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="filter-popover"
            role="dialog"
            aria-label="Filter options"
            initial={{ opacity: 0, y: -4, scale: 0.995 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.995 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="filter-popover__header">
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Filters</p>
                <p className="panel-hint">Choose what you want to see, then close the panel.</p>
              </div>
              <button type="button" className="btn-icon" onClick={() => setOpen(false)} aria-label="Close filters">
                <Icon name="close" className="w-4 h-4" />
              </button>
            </div>

            <div className="filter-popover__body">
              <fieldset>
                <legend className="panel-title mb-1.5">Custom date range</legend>
                <div className="flex flex-wrap items-center gap-2">
                  <label className="filter-date-field">
                    <span>From</span>
                    <input
                      type="date"
                      value={customRange?.start ?? ''}
                      min={dateRange?.min_date ?? undefined}
                      max={dateRange?.max_date ?? undefined}
                      onChange={(event) => onCustomRangeChange?.({ ...customRange, start: event.target.value })}
                    />
                  </label>
                  <label className="filter-date-field">
                    <span>To</span>
                    <input
                      type="date"
                      value={customRange?.end ?? ''}
                      min={customRange?.start ?? dateRange?.min_date ?? undefined}
                      max={dateRange?.max_date ?? undefined}
                      onChange={(event) => onCustomRangeChange?.({ ...customRange, end: event.target.value })}
                    />
                  </label>
                  {dateRange?.min_date && (
                    <span className="filter-popover__range-note">
                      Data available {dateRange.min_date} → {dateRange.max_date}
                    </span>
                  )}
                </div>
              </fieldset>

              {dimensions.length === 0 ? (
                <p className="panel-hint">No filterable columns detected in this file.</p>
              ) : (
                <div className="filter-popover__grid">
                  {dimensions.map((dimension) => (
                    <fieldset key={dimension.key} className="min-w-0">
                      <legend className="panel-title mb-1.5">
                        {dimension.label}
                        {dimension.truncated && (
                          <span className="font-normal normal-case" style={{ color: 'var(--text-muted)' }}>
                            {' '}(first {dimension.values.length})
                          </span>
                        )}
                      </legend>
                      <div className="filter-values" role="listbox" aria-label={dimension.label}>
                        {dimension.values.map((value) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => toggleValue(dimension.key, value)}
                            aria-pressed={(filters[dimension.key] ?? []).includes(value)}
                            className="chip"
                          >
                            {value}
                          </button>
                        ))}
                      </div>
                    </fieldset>
                  ))}
                </div>
              )}
            </div>

            <div className="filter-popover__footer">
              <button type="button" className="btn" onClick={onClear}>Clear all</button>
              <button type="button" className="btn-primary" onClick={() => setOpen(false)}>Done</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
