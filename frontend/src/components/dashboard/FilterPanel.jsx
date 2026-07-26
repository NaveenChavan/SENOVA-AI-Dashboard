import { useState } from 'react'

import Icon from '../common/Icon'

/**
 * Feature 5a — the filter panel.
 *
 * Filters are applied **server-side before aggregation**, so every widget on the
 * page (KPIs, charts, insights, inventory, P&L, ledger and the PDF) reflects the
 * same slice. That's why the panel only offers dimensions the uploaded file
 * actually contains — the list comes from ``GET /analytics/{id}/dimensions``.
 *
 * "No filtering" is listed as an anti-pattern for data-dense dashboards, and the
 * cure has to be discoverable: active filters are shown as removable chips, and
 * the whole state is mirrored into the URL by the page so a filtered view can be
 * shared or reloaded.
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
    <section
      className="card p-3 sm:p-4"
      aria-label="Filters"
      style={{ transition: 'box-shadow 200ms ease' }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          aria-expanded={open}
          className="flex items-center gap-2 text-sm font-medium rounded-lg px-3 cursor-pointer transition-colors"
          style={{
            minHeight: 40,
            border: '1px solid var(--border-subtle)',
            background: open ? 'var(--accent-blue-glow)' : 'var(--bg-input)',
            color: open ? 'var(--accent-blue)' : 'var(--text-secondary)',
          }}
        >
          <Icon name="filter" className="w-4 h-4" />
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
              className="flex items-center gap-1.5 text-xs rounded-full px-3 cursor-pointer transition-colors"
              style={{
                minHeight: 32,
                background: 'var(--accent-blue-glow)',
                color: 'var(--accent-blue)',
                border: '1px solid var(--border-active)',
              }}
              aria-label={`Remove ${dimension?.label ?? key} filter`}
            >
              <span className="font-medium">{dimension?.label ?? key}:</span>
              <span>{values.length === 1 ? values[0] : `${values.length} selected`}</span>
              <Icon name="close" className="w-3 h-3" />
            </button>
          )
        })}

        {hasCustomRange && (
          <span
            className="flex items-center gap-1.5 text-xs rounded-full px-3"
            style={{
              minHeight: 32,
              background: 'var(--bg-input)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <Icon name="calendar" className="w-3.5 h-3.5" />
            {customRange.start} → {customRange.end}
          </span>
        )}

        {(activeCount > 0 || hasCustomRange) && (
          <button
            type="button"
            onClick={onClear}
            className="text-xs underline underline-offset-2 cursor-pointer ml-auto"
            style={{ color: 'var(--text-muted)' }}
          >
            Clear all
          </button>
        )}
      </div>

      {open && (
        <div className="mt-4 pt-4 space-y-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {/* Custom date range — the presets can't express "1st to 15th". */}
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
              Custom date range
            </legend>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="block mb-1">From</span>
                <input
                  type="date"
                  className="filter-select cursor-pointer"
                  value={customRange?.start ?? ''}
                  min={dateRange?.min_date ?? undefined}
                  max={dateRange?.max_date ?? undefined}
                  onChange={(event) =>
                    onCustomRangeChange?.({ ...customRange, start: event.target.value })
                  }
                />
              </label>
              <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="block mb-1">To</span>
                <input
                  type="date"
                  className="filter-select cursor-pointer"
                  value={customRange?.end ?? ''}
                  min={customRange?.start ?? dateRange?.min_date ?? undefined}
                  max={dateRange?.max_date ?? undefined}
                  onChange={(event) =>
                    onCustomRangeChange?.({ ...customRange, end: event.target.value })
                  }
                />
              </label>
              {dateRange?.min_date && (
                <p className="text-[11px] pb-2" style={{ color: 'var(--text-muted)' }}>
                  Data available {dateRange.min_date} → {dateRange.max_date}
                </p>
              )}
            </div>
          </fieldset>

          {/* One group per available dimension. */}
          {dimensions.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              No filterable columns detected in this file.
            </p>
          ) : (
            dimensions.map((dimension) => (
              <fieldset key={dimension.key}>
                <legend className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                  {dimension.label}
                  {dimension.truncated && (
                    <span className="ml-2 font-normal normal-case" style={{ color: 'var(--text-muted)' }}>
                      (showing first {dimension.values.length})
                    </span>
                  )}
                </legend>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                  {dimension.values.map((value) => {
                    const selected = (filters[dimension.key] ?? []).includes(value)
                    return (
                      <button
                        key={value}
                        type="button"
                        onClick={() => toggleValue(dimension.key, value)}
                        aria-pressed={selected}
                        className="text-xs rounded-full px-3 cursor-pointer transition-colors"
                        style={{
                          minHeight: 32,
                          background: selected ? 'var(--accent-blue)' : 'var(--bg-input)',
                          color: selected ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                          border: `1px solid ${selected ? 'var(--accent-blue)' : 'var(--border-subtle)'}`,
                        }}
                      >
                        {value}
                      </button>
                    )
                  })}
                </div>
              </fieldset>
            ))
          )}
        </div>
      )}
    </section>
  )
}
