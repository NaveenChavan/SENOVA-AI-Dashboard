import { useState } from 'react'

import Icon from '../common/Icon'

/**
 * Feature 5a — the filter bar.
 *
 * Collapsed it is a single 42px row: a Filters button, the active filters as
 * removable chips, and a Clear all link. Expanded it reveals the custom date
 * range and one chip group per dimension the uploaded file actually contains
 * (the list comes from `GET /analytics/{id}/dimensions`).
 *
 * Filters are applied server-side before aggregation, so every widget on the
 * page reflects the same slice. "No filtering" is an explicit anti-pattern for
 * data-dense dashboards — and the cure has to be discoverable, which is why the
 * active state is always visible as chips rather than hidden behind a panel.
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

  const activeCount = Object.values(filters).reduce((total, values) => total + values.length, 0)
  const hasCustomRange = Boolean(customRange?.start && customRange?.end)

  /** Toggle one value of one dimension, keeping the rest intact. */
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
    <section className="card" aria-label="Filters">
      <div className="flex items-center gap-1.5 flex-wrap px-[var(--card-pad)]" style={{ minHeight: 42, paddingTop: 5, paddingBottom: 5 }}>
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          aria-expanded={open}
          className="btn"
          style={open ? { borderColor: 'var(--accent-blue)', color: 'var(--accent-blue)' } : undefined}
        >
          <Icon name="filter" className="w-3.5 h-3.5" />
          Filters
          {activeCount > 0 && (
            <span
              className="text-[11px] font-bold rounded-full px-1.5"
              style={{ background: 'var(--accent-blue)', color: 'var(--text-on-accent)' }}
            >
              {activeCount}
            </span>
          )}
        </button>

        {/* Active filters as removable chips — visible state, one click to undo. */}
        {Object.entries(filters).map(([key, values]) => {
          const dimension = dimensions.find((option) => option.key === key)
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

        {(activeCount > 0 || hasCustomRange) && (
          <button
            type="button"
            onClick={onClear}
            className="text-[12px] underline underline-offset-2 cursor-pointer ml-auto"
            style={{ color: 'var(--text-muted)' }}
          >
            Clear all
          </button>
        )}
      </div>

      {open && (
        <div
          className="px-[var(--card-pad)] py-3 space-y-3"
          style={{ borderTop: '1px solid var(--border-subtle)' }}
        >
          {/* Custom date range — the presets can't express "1st to 15th". */}
          <fieldset>
            <legend className="panel-title mb-1.5">Custom date range</legend>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                From
                <input
                  type="date"
                  value={customRange?.start ?? ''}
                  min={dateRange?.min_date ?? undefined}
                  max={dateRange?.max_date ?? undefined}
                  onChange={(event) => onCustomRangeChange?.({ ...customRange, start: event.target.value })}
                />
              </label>
              <label className="flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--text-muted)' }}>
                To
                <input
                  type="date"
                  value={customRange?.end ?? ''}
                  min={customRange?.start ?? dateRange?.min_date ?? undefined}
                  max={dateRange?.max_date ?? undefined}
                  onChange={(event) => onCustomRangeChange?.({ ...customRange, end: event.target.value })}
                />
              </label>
              {dateRange?.min_date && (
                <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  Data available {dateRange.min_date} → {dateRange.max_date}
                </span>
              )}
            </div>
          </fieldset>

          {/* One chip group per available dimension. */}
          {dimensions.length === 0 ? (
            <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
              No filterable columns detected in this file.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
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
                  {/* Capped height: a dimension with 200 values must not turn
                      the filter panel into a full-page list. */}
                  <div className="flex flex-wrap gap-1 overflow-y-auto" style={{ maxHeight: 96 }}>
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
      )}
    </section>
  )
}
