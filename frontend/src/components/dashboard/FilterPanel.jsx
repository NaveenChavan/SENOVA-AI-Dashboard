import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'

import Icon from '../common/Icon'

/**
 * Format a YYYY-MM-DD string into 'Latest day (DD Mon)' e.g. 'Latest day (17 Jun)'
 */
function formatLatestDay(maxDateStr) {
  if (!maxDateStr) return 'Latest day'
  try {
    const parts = maxDateStr.split('-')
    if (parts.length === 3) {
      const year = Number(parts[0])
      const month = Number(parts[1])
      const day = Number(parts[2])
      const date = new Date(Date.UTC(year, month - 1, day))
      const monthShort = date.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })
      return `Latest day (${day} ${monthShort})`
    }
  } catch {}
  return 'Latest day'
}

/**
 * FilterPanel supporting both drawer and popover modes.
 *
 * Implements:
 * - Active filter groups count badge (including time preset / custom range).
 * - Staged filtering: options & presets update in memory until Apply is pressed.
 * - Searchable tall dimensions (Item, Invoice No, etc.).
 * - Dimension header with 'X of Y selected', 'Select all', and 'Clear' buttons.
 * - Cascading dimension options via fetchDimensionOptions.
 * - Non-empty loading indicator ('Loading…') without flashing 'No matching values.'.
 * - Support for extra dimensions (x_dim:) passed in dimensions list.
 */
export default function FilterPanel({
  fileId,
  dimensions = [],
  filters = {},
  timeFilter = 'all',
  onChange,
  dateRange,
  customRange,
  onCustomRangeChange,
  onApply,
  onClear,
  fetchDimensionOptions,
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  // Staged states for drawer modal
  const [stagedFilters, setStagedFilters] = useState(filters ?? {})
  const [stagedTimeFilter, setStagedTimeFilter] = useState(timeFilter ?? 'all')
  const [stagedCustomRange, setStagedCustomRange] = useState(customRange ?? { start: '', end: '' })

  // Search terms and remote options by dimension key
  const [searches, setSearches] = useState({})
  const [remoteOptions, setRemoteOptions] = useState({})
  const [loadingMap, setLoadingMap] = useState({})

  const hasCustomRange = Boolean(customRange?.start && customRange?.end)
  const hasTimeFilter = Boolean(timeFilter && timeFilter !== 'all')

  const activeGroupCount = useMemo(() => {
    const dimensionCount = Object.keys(filters ?? {}).filter(
      (key) => Array.isArray(filters?.[key]) && filters[key].length > 0,
    ).length
    const timeCount = (hasCustomRange || hasTimeFilter) ? 1 : 0
    return dimensionCount + timeCount
  }, [filters, hasCustomRange, hasTimeFilter])

  // Sync staged state when opening
  useEffect(() => {
    if (open) {
      setStagedFilters(filters ?? {})
      setStagedTimeFilter(timeFilter ?? 'all')
      setStagedCustomRange(customRange ?? { start: '', end: '' })
      setSearches({})
      setRemoteOptions({})
      setLoadingMap({})
    }
  }, [open, filters, timeFilter, customRange])

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

  // Fetch cascading options when stagedFilters change
  const triggerFetchOptions = (dimKey, nextFilters, searchVal = '') => {
    if (!fetchDimensionOptions || !fileId) return
    setLoadingMap((prev) => ({ ...prev, [dimKey]: true }))
    fetchDimensionOptions(fileId, {
      dimension: dimKey,
      filters: nextFilters,
      search: searchVal,
    })
      .then((res) => {
        if (res) {
          setRemoteOptions((prev) => ({
            ...prev,
            [dimKey]: {
              values: res.values || [],
              total: res.total ?? res.values?.length ?? 0,
            },
          }))
        }
      })
      .catch(() => {})
      .finally(() => {
        setLoadingMap((prev) => ({ ...prev, [dimKey]: false }))
      })
  }

  const toggleStagedValue = (key, value) => {
    const current = stagedFilters[key] ?? []
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value]

    const updated = { ...stagedFilters }
    if (next.length) updated[key] = next
    else delete updated[key]

    setStagedFilters(updated)

    // Cascade dependent dimensions if fetchDimensionOptions is available
    if (fetchDimensionOptions && fileId) {
      if (key === 'category') {
        triggerFetchOptions('item', updated, searches['item'] || '')
      } else if (key === 'item') {
        triggerFetchOptions('category', updated, searches['category'] || '')
      }
    }
  }

  const handleSelectAll = (key, values) => {
    const updated = { ...stagedFilters, [key]: [...values] }
    setStagedFilters(updated)
    if (fetchDimensionOptions && fileId) {
      if (key === 'category') {
        triggerFetchOptions('item', updated, searches['item'] || '')
      } else if (key === 'item') {
        triggerFetchOptions('category', updated, searches['category'] || '')
      }
    }
  }

  const handleClearDimension = (key) => {
    const updated = { ...stagedFilters }
    delete updated[key]
    setStagedFilters(updated)
    if (fetchDimensionOptions && fileId) {
      if (key === 'category') {
        triggerFetchOptions('item', updated, searches['item'] || '')
      } else if (key === 'item') {
        triggerFetchOptions('category', updated, searches['category'] || '')
      }
    }
  }

  const handleSearch = (key, text) => {
    setSearches((prev) => ({ ...prev, [key]: text }))
    if (fetchDimensionOptions && fileId) {
      triggerFetchOptions(key, stagedFilters, text)
    }
  }

  const removeDimension = (key) => {
    const updated = { ...filters }
    delete updated[key]
    if (onApply) {
      onApply({
        filters: updated,
        timeFilter,
        startDate: customRange?.start || null,
        endDate: customRange?.end || null,
      })
    } else {
      onChange?.(updated)
    }
  }

  const handleApply = () => {
    if (onApply) {
      onApply({
        filters: stagedFilters,
        timeFilter: stagedTimeFilter,
        startDate: stagedCustomRange?.start || null,
        endDate: stagedCustomRange?.end || null,
      })
    } else {
      onChange?.(stagedFilters)
      if (onCustomRangeChange && stagedCustomRange) {
        onCustomRangeChange(stagedCustomRange)
      }
    }
    setOpen(false)
  }

  const handleClearAll = () => {
    setStagedFilters({})
    setStagedTimeFilter('all')
    setStagedCustomRange({ start: '', end: '' })
    onClear?.()
  }

  const latestDayButtonLabel = useMemo(
    () => formatLatestDay(dateRange?.max_date),
    [dateRange?.max_date],
  )

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

        {activeGroupCount > 0 && (
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
            aria-label="Filters"
            initial={{ opacity: 0, y: -4, scale: 0.995 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.995 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="filter-popover__header">
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Filters</p>
                <p className="panel-hint">Choose what you want to see, then apply changes.</p>
              </div>
              <button type="button" className="btn-icon" onClick={() => setOpen(false)} aria-label="Close filters">
                <Icon name="close" className="w-4 h-4" />
              </button>
            </div>

            <div className="filter-popover__body">
              {/* Presets and Date Controls */}
              <fieldset>
                <legend className="panel-title mb-1.5">Date presets</legend>
                <div className="flex flex-wrap items-center gap-1.5 mb-2.5">
                  <button
                    type="button"
                    className={`chip ${stagedTimeFilter === 'today' ? 'chip--active' : ''}`}
                    onClick={() => {
                      setStagedTimeFilter('today')
                      setStagedCustomRange({ start: '', end: '' })
                    }}
                  >
                    {latestDayButtonLabel}
                  </button>
                  <button
                    type="button"
                    className={`chip ${stagedTimeFilter === 'week' ? 'chip--active' : ''}`}
                    onClick={() => {
                      setStagedTimeFilter('week')
                      setStagedCustomRange({ start: '', end: '' })
                    }}
                  >
                    Last 7 days
                  </button>
                  <button
                    type="button"
                    className={`chip ${stagedTimeFilter === '30days' ? 'chip--active' : ''}`}
                    onClick={() => {
                      setStagedTimeFilter('30days')
                      setStagedCustomRange({ start: '', end: '' })
                    }}
                  >
                    Last 30 days
                  </button>
                  <button
                    type="button"
                    className={`chip ${stagedTimeFilter === 'all' && !stagedCustomRange?.start ? 'chip--active' : ''}`}
                    onClick={() => {
                      setStagedTimeFilter('all')
                      setStagedCustomRange({ start: '', end: '' })
                    }}
                  >
                    All time
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <label className="filter-date-field">
                    <span>From</span>
                    <input
                      type="date"
                      value={stagedCustomRange?.start ?? ''}
                      min={dateRange?.min_date ?? undefined}
                      max={dateRange?.max_date ?? undefined}
                      onChange={(event) =>
                        setStagedCustomRange((prev) => ({ ...prev, start: event.target.value }))
                      }
                    />
                  </label>
                  <label className="filter-date-field">
                    <span>To</span>
                    <input
                      type="date"
                      value={stagedCustomRange?.end ?? ''}
                      min={stagedCustomRange?.start ?? dateRange?.min_date ?? undefined}
                      max={dateRange?.max_date ?? undefined}
                      onChange={(event) =>
                        setStagedCustomRange((prev) => ({ ...prev, end: event.target.value }))
                      }
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
                  {dimensions.map((dimension) => {
                    const isTall =
                      ['item', 'invoice_no', 'customer'].includes(dimension.key.toLowerCase()) ||
                      (dimension.total && dimension.total > 10) ||
                      dimension.searchable

                    const optionsData = remoteOptions[dimension.key] || {
                      values: dimension.values || [],
                      total: dimension.total ?? dimension.values?.length ?? 0,
                    }

                    const rawValues = optionsData.values
                    const totalCount = optionsData.total
                    const searchStr = searches[dimension.key] || ''

                    // Client-side fallback search if not remote-fetched
                    const filteredValues =
                      !fetchDimensionOptions && searchStr
                        ? rawValues.filter((v) =>
                            String(v).toLowerCase().includes(searchStr.toLowerCase()),
                          )
                        : rawValues

                    const selectedList = stagedFilters[dimension.key] ?? []
                    const selectedCount = selectedList.length
                    const isLoading = Boolean(loadingMap[dimension.key])

                    return (
                      <fieldset key={dimension.key} className="min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <legend className="panel-title mb-0">{dimension.label}</legend>
                          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                            {selectedCount} of {totalCount} selected
                          </span>
                        </div>

                        <div className="flex items-center gap-2 mb-1.5">
                          <button
                            type="button"
                            className="text-[11px] underline hover:no-underline"
                            style={{ color: 'var(--text-secondary)' }}
                            onClick={() => handleSelectAll(dimension.key, filteredValues)}
                          >
                            Select all
                          </button>
                          <button
                            type="button"
                            className="text-[11px] underline hover:no-underline"
                            style={{ color: 'var(--text-secondary)' }}
                            onClick={() => handleClearDimension(dimension.key)}
                          >
                            Clear
                          </button>
                        </div>

                        {isTall && (
                          <input
                            type="search"
                            role="searchbox"
                            aria-label={`Search ${dimension.label}`}
                            placeholder={`Search ${dimension.label}...`}
                            value={searchStr}
                            onChange={(e) => handleSearch(dimension.key, e.target.value)}
                            className="filter-search-input mb-1.5 w-full text-xs px-2 py-1 rounded"
                            style={{
                              border: '1px solid var(--border-subtle)',
                              background: 'var(--bg-canvas)',
                              color: 'var(--text-primary)',
                            }}
                          />
                        )}

                        <div className="filter-values" role="listbox" aria-label={dimension.label}>
                          {isLoading ? (
                            <div className="text-xs py-1.5 font-medium" style={{ color: 'var(--text-muted)' }}>
                              Loading…
                            </div>
                          ) : filteredValues.length === 0 ? (
                            <div className="text-xs py-1.5" style={{ color: 'var(--text-muted)' }}>
                              No matching values.
                            </div>
                          ) : (
                            filteredValues.map((value) => {
                              const isSelected = selectedList.includes(value)
                              return (
                                <button
                                  key={value}
                                  type="button"
                                  onClick={() => toggleStagedValue(dimension.key, value)}
                                  aria-pressed={isSelected}
                                  className={`chip ${isSelected ? 'chip--active' : ''}`}
                                >
                                  {value}
                                </button>
                              )
                            })
                          )}
                        </div>
                      </fieldset>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="filter-popover__footer">
              <button type="button" className="btn" onClick={handleClearAll}>
                Clear all
              </button>
              <button type="button" className="btn-primary" onClick={handleApply}>
                Apply
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
