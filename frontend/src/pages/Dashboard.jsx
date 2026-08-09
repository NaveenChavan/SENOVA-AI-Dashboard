import { lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import api from '../services/api'
import useSalesStore, { buildQueryBody } from '../store/useSalesStore'
import useDensityStore from '../store/useDensityStore'
import Card from '../components/common/Card'
import CommandPalette from '../components/common/CommandPalette'
import ErrorBoundary from '../components/common/ErrorBoundary'
import Icon from '../components/common/Icon'
import SummaryStats from '../components/dashboard/SummaryStats'
import { CHART_TYPES, MEASURES, resolveChartRequest, useChartView } from '../components/charts/chartView'

// Everything below the KPI row is code-split: the Inventory and Financial
// Report tabs are never downloaded until the user opens them.
const RowErrorsBanner = lazy(() => import('../components/dashboard/RowErrorsBanner'))
const TopItems = lazy(() => import('../components/dashboard/TopItems'))
const DeadStockTable = lazy(() => import('../components/dashboard/DeadStockTable'))
const PnLReportTable = lazy(() => import('../components/dashboard/PnLReportTable'))
const TransactionLedgerTable = lazy(() => import('../components/dashboard/TransactionLedgerTable'))
const InsightCards = lazy(() => import('../components/dashboard/InsightCards'))
const InventoryPanel = lazy(() => import('../components/dashboard/InventoryPanel'))
const ForecastSummary = lazy(() => import('../components/dashboard/ForecastSummary'))
const FilterPanel = lazy(() => import('../components/dashboard/FilterPanel'))
const DrillDownPanel = lazy(() => import('../components/dashboard/DrillDownPanel'))
const ChartStudio = lazy(() => import('../components/charts/ChartStudio'))
const TrendChart = lazy(() => import('../components/charts/TrendChart'))

/**
 * The dashboard page.
 *
 * Layout is answer-first and fixed-height: a 52px shell header, one toolbar
 * row (title + date presets + export), one filter row, one tab row, then the
 * content grid. Every control is the same height and every card the same
 * padding, so the first screen fits without scrolling a card to see its edges.
 *
 * All view state (tab, date window, custom range, filters) is mirrored into the
 * URL, so a filtered view survives a refresh and can be shared.
 */

const DATE_FILTERS = [
  { value: 'today', label: 'Today', minSpanDays: 1 },
  { value: 'week', label: '7 Days', minSpanDays: 8 },
  { value: '30days', label: '30 Days', minSpanDays: 31 },
  { value: 'month', label: 'This Month', minSpanDays: 8 },
  { value: 'all', label: 'All Time', minSpanDays: 1 },
]

const VIEW_TABS = [
  { value: 'overview', label: 'Overview', icon: 'chart' },
  { value: 'inventory', label: 'Inventory', icon: 'box' },
  { value: 'report', label: 'Financial Report', icon: 'document' },
]

const EASE = [0.16, 1, 0.3, 1]

/** Shared entrance variants for the staggered content grid — fast and precise
 * (0.35-0.4s), never bouncy, so the "computed intelligence" feel holds. */
const fadeUp = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: EASE },
}

/**
 * A preset is meaningless when the data's span doesn't exceed its window — it
 * would return exactly the same rows as "All Time", which reads as a bug.
 * Disabling (not hiding) it keeps the toolbar stable and lets a tooltip explain.
 */
function isFilterMeaningful(filter, spanDays) {
  if (filter.value === 'today' || filter.value === 'all') return true
  if (!spanDays) return true
  return spanDays >= filter.minSpanDays
}

export default function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const fileId = searchParams.get('fileId')

  const {
    data,
    isLoading,
    error,
    fetchAnalytics,
    query,
    setQuery,
    resetFilters,
    dimensions,
    fetchDimensions,
    chartData,
    chartLoading,
    fetchChartData,
    heatmapData,
    heatmapLoading,
    fetchHeatmap,
    insights,
    insightsLoading,
    fetchInsights,
    inventory,
    inventoryLoading,
    fetchInventory,
    forecast,
    forecastLoading,
    forecastHorizon,
    setForecastHorizon,
    fetchForecast,
    caReport,
    caReportLoading,
    caReportError,
    fetchCAReport,
    ledgerPage,
    ledgerLoading,
    fetchLedgerPage,
    drillSelection,
    drillLedger,
    drillLoading,
    openDrillDown,
    closeDrillDown,
    dateRange,
  } = useSalesStore()

  const [exporting, setExporting] = useState(false)
  const [activeTab, setActiveTab] = useState(() => searchParams.get('tab') ?? 'overview')

  // The studio's view lives here, not inside the panel, so the command palette
  // can switch chart type or measure from anywhere on the page.
  const [chartView, setChartView] = useChartView()
  const chartRequest = useMemo(() => resolveChartRequest(chartView), [chartView])
  const { density, toggleDensity } = useDensityStore()

  // ── Hydrate query state from the URL ──────────────────────────────────
  // Re-runs when the file changes as well as on mount: filters that made sense
  // for the previous upload may name a dimension the new file doesn't have,
  // which the API would (correctly) reject with a 422.
  useEffect(() => {
    const range = searchParams.get('range')
    const from = searchParams.get('from')
    const to = searchParams.get('to')
    const rawFilters = searchParams.get('filters')

    let parsedFilters = {}
    if (rawFilters) {
      // A hand-edited/truncated URL must not break the page.
      try {
        const candidate = JSON.parse(decodeURIComponent(rawFilters))
        if (candidate && typeof candidate === 'object') parsedFilters = candidate
      } catch {
        parsedFilters = {}
      }
    }

    setQuery({
      timeFilter: range ?? '30days',
      startDate: from ?? null,
      endDate: to ?? null,
      filters: parsedFilters,
    })
    // Keyed on the file, not on our own state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId])

  /** Push the current view state into the URL (replace, so back still works). */
  const syncUrl = useCallback(
    (next) => {
      const params = new URLSearchParams(searchParams)
      if (fileId) params.set('fileId', fileId)
      params.set('tab', next.tab ?? activeTab)
      params.set('range', next.timeFilter ?? query.timeFilter)

      if ((next.timeFilter ?? query.timeFilter) === 'custom') {
        params.set('from', next.startDate ?? query.startDate ?? '')
        params.set('to', next.endDate ?? query.endDate ?? '')
      } else {
        params.delete('from')
        params.delete('to')
      }

      const filters = next.filters ?? query.filters
      if (filters && Object.keys(filters).length) {
        params.set('filters', encodeURIComponent(JSON.stringify(filters)))
      } else {
        params.delete('filters')
      }

      setSearchParams(params, { replace: true })
    },
    [searchParams, setSearchParams, fileId, activeTab, query],
  )

  // ── Data loading ───────────────────────────────────────────────────────

  // The query object is rebuilt on every render, so effects key off its
  // serialised body rather than its identity.
  const querySignature = useMemo(() => JSON.stringify(buildQueryBody(query)), [query])

  // A custom range is only valid once both ends are picked.
  const queryReady = query.timeFilter !== 'custom' || Boolean(query.startDate && query.endDate)

  useEffect(() => {
    if (!fileId) return
    if (useSalesStore.getState().fileId !== fileId) {
      useSalesStore.setState({ fileId })
    }
    fetchDimensions(fileId)
  }, [fileId, fetchDimensions])

  useEffect(() => {
    if (!fileId || !queryReady) return
    fetchAnalytics(fileId, query)
    fetchInsights(fileId, query)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, querySignature, queryReady])

  useEffect(() => {
    if (!fileId || !queryReady) return
    fetchForecast(fileId, query, forecastHorizon)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, querySignature, queryReady, forecastHorizon])

  // Chart data follows whatever the studio currently asks for.
  useEffect(() => {
    if (!fileId || !queryReady || activeTab !== 'overview') return
    if (chartRequest.needsHeatmap) {
      fetchHeatmap(fileId, query, chartRequest.measure)
    } else {
      fetchChartData(fileId, query, {
        dimension: chartRequest.dimension,
        measure: chartRequest.measure,
        topN: chartRequest.top_n,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, querySignature, queryReady, activeTab, chartRequest])

  // Inventory and the financial report load lazily, only on their own tab.
  useEffect(() => {
    if (!fileId || !queryReady || activeTab !== 'inventory') return
    fetchInventory(fileId, query)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, querySignature, queryReady, activeTab])

  useEffect(() => {
    if (!fileId || !queryReady || activeTab !== 'report') return
    fetchCAReport(fileId, query)
    fetchLedgerPage(fileId, { query, page: 1, pageSize: 50 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, querySignature, queryReady, activeTab])

  // If the selected preset becomes meaningless once the data's real span is
  // known (default 30 days but the file covers 4), fall back to All Time.
  useEffect(() => {
    if (!dateRange?.span_days || query.timeFilter === 'custom') return
    const current = DATE_FILTERS.find((f) => f.value === query.timeFilter)
    if (current && !isFilterMeaningful(current, dateRange.span_days)) {
      setQuery({ timeFilter: 'all' })
      syncUrl({ timeFilter: 'all' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange, query.timeFilter])

  // ── Handlers ───────────────────────────────────────────────────────────

  const changeTimeFilter = (value) => {
    setQuery({ timeFilter: value, startDate: null, endDate: null })
    syncUrl({ timeFilter: value, startDate: null, endDate: null })
  }

  const changeTab = (value) => {
    setActiveTab(value)
    syncUrl({ tab: value })
  }

  const changeFilters = (filters) => {
    setQuery({ filters })
    syncUrl({ filters })
  }

  const changeCustomRange = (range) => {
    // Only switch to the custom window once both ends exist, otherwise the
    // request would be rejected as an incomplete range.
    const next = { startDate: range.start || null, endDate: range.end || null }
    const complete = Boolean(next.startDate && next.endDate)
    setQuery({ ...next, timeFilter: complete ? 'custom' : query.timeFilter })
    if (complete) syncUrl({ ...next, timeFilter: 'custom' })
  }

  const clearAll = () => {
    resetFilters()
    syncUrl({
      filters: {},
      timeFilter: query.timeFilter === 'custom' ? 'all' : query.timeFilter,
      startDate: null,
      endDate: null,
    })
  }

  const handleDrillDown = (point) => {
    if (!fileId) return
    openDrillDown(fileId, { dimension: chartRequest.dimension, point })
  }

  const exportPDF = async () => {
    if (!fileId) return
    setExporting(true)
    try {
      // The PDF is generated server-side as real tables (findings, P&L,
      // forecast, reorder list, ledger) from the same slice shown on screen.
      const response = await api.post(`/analytics/${fileId}/report.pdf`, buildQueryBody(query), {
        responseType: 'blob',
      })

      const blobUrl = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = `senova-financial-report-${fileId.slice(0, 8)}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      console.error('PDF export failed:', err)
    } finally {
      setExporting(false)
    }
  }

  /**
   * Everything the dashboard can do, as a flat list for the ⌘K palette.
   *
   * Built from the same constants the visible controls use, so a new chart type
   * or measure appears in both places automatically — and a keyboard user never
   * has fewer options than a mouse user.
   */
  const paletteActions = useMemo(
    () => [
      ...VIEW_TABS.map((tab) => ({
        id: `tab-${tab.value}`,
        group: 'Go to',
        label: tab.label,
        icon: tab.icon,
        run: () => changeTab(tab.value),
      })),
      ...DATE_FILTERS.map((filter) => ({
        id: `range-${filter.value}`,
        group: 'Date range',
        label: filter.label,
        icon: 'calendar',
        run: () => changeTimeFilter(filter.value),
      })),
      ...CHART_TYPES.map((type) => ({
        id: `chart-${type.value}`,
        group: 'Chart',
        label: type.label,
        hint: type.hint,
        icon: 'chart',
        run: () => {
          setChartView({ chartType: type.value })
          changeTab('overview')
        },
      })),
      ...MEASURES.map((option) => ({
        id: `measure-${option.value}`,
        group: 'Measure',
        label: option.label,
        icon: 'chart',
        run: () => {
          setChartView({ measure: option.value })
          changeTab('overview')
        },
      })),
      {
        id: 'toggle-table',
        group: 'Chart',
        label: chartView.showTable ? 'Show chart instead of table' : 'Show the chart as a table',
        icon: 'document',
        run: () => setChartView({ showTable: !chartView.showTable }),
      },
      {
        id: 'clear-filters',
        group: 'Filters',
        label: 'Clear all filters',
        icon: 'close',
        run: clearAll,
      },
      {
        id: 'export-pdf',
        group: 'Export',
        label: 'Download the PDF report',
        icon: 'download',
        run: exportPDF,
      },
      {
        id: 'toggle-density',
        group: 'Display',
        label: density === 'compact' ? 'Comfortable spacing' : 'Compact spacing',
        icon: 'refresh',
        run: toggleDensity,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeTab, query, chartView, density],
  )

  // ── Guard states ───────────────────────────────────────────────────────

  if (!fileId) return <NoFileState />
  if (isLoading && !data) return <LoadingSkeleton />

  if (error) {
    const filterCount = Object.values(query.filters ?? {}).reduce((total, values) => total + values.length, 0)
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center px-4">
        <Helmet>
          <title>Error — SENOVA Digital Lab</title>
        </Helmet>
        <Icon name="alert" className="w-7 h-7 mb-3" style={{ color: 'var(--accent-red)' }} />
        <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Something went wrong
        </p>
        <p className="text-xs mb-4 max-w-sm" style={{ color: 'var(--text-secondary)' }}>
          {error}
        </p>
        <div className="flex flex-wrap gap-2 justify-center">
          {/* A filter carried over in the URL from a different upload can name a
              column this file doesn't have — clearing it is the actual fix, so
              offer it here rather than leaving a dead end. */}
          {filterCount > 0 && (
            <button type="button" className="btn-primary" onClick={clearAll}>
              Clear filters and retry
            </button>
          )}
          <Link to="/upload" className={filterCount > 0 ? 'btn' : 'btn-primary'}>
            Upload a new file
          </Link>
        </div>
      </div>
    )
  }

  if (!data) return <NoFileState />

  const isEmpty = data.summary?.revenue?.value === 0 && (data.top_items?.length ?? 0) === 0
  const activeFilterCount = Object.values(query.filters ?? {}).reduce((total, values) => total + values.length, 0)
  const periodLabel =
    query.timeFilter === 'custom'
      ? `${query.startDate} → ${query.endDate}`
      : DATE_FILTERS.find((f) => f.value === query.timeFilter)?.label

  return (
    <section className="space-y-3 sm:space-y-4">
      <Helmet>
        <title>Dashboard — SENOVA Digital Lab | Retail &amp; MSME Analytics</title>
        <meta
          name="description"
          content="AI retail analytics: automated insights, revenue forecasting, reorder intelligence, eight chart views and drill-down into every transaction."
        />
      </Helmet>

      {/* ── Toolbar: title · date presets · export ─────────────────────── */}
      {/* Sticky below the 52px app header: on a long dashboard the date range
          and filters are the controls people reach for while scrolling. */}
      <motion.div
        className="toolbar-sticky space-y-2 sm:space-y-2.5"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: EASE }}
      >
        {/* Row 1: title + export. Row 2: date presets.
            On a phone these were competing for one wrapping flex row, which
            resolved into several stacked rows and pushed the actual data far
            below the fold. Splitting them explicitly keeps it to two rows,
            and the presets get the full width they need to scroll. */}
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h1 className="text-display truncate">Analytics Overview</h1>
            <p className="panel-hint truncate">
              All values in INR (₹) · {periodLabel}
              {activeFilterCount > 0 && ` · ${activeFilterCount} filter(s)`}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Hints the ⌘K palette exists; keyboard users find it anyway. */}
            <span
              className="hidden lg:inline-flex items-center gap-1 text-[11px] font-mono px-2 rounded-md"
              style={{
                height: 'var(--control-h)',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-input)',
                color: 'var(--text-muted)',
              }}
              title="Press Ctrl-K (⌘K on Mac) for the command palette"
            >
              ⌘K
            </span>

            {/* Icon-only below sm to save a whole toolbar row; the label stays
                in the accessibility tree rather than being dropped. */}
            <button onClick={exportPDF} disabled={exporting} aria-busy={exporting} className="btn-primary shrink-0">
              <Icon name="download" className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{exporting ? 'Generating…' : 'Export PDF'}</span>
              <span className="sr-only sm:hidden">{exporting ? 'Generating PDF' : 'Export PDF'}</span>
            </button>
          </div>
        </div>

        <div className="seg w-full sm:w-auto min-w-0" role="group" aria-label="Filter analytics by date range">
          {DATE_FILTERS.map((filter) => {
            const disabled = !isFilterMeaningful(filter, dateRange?.span_days)
            return (
              <button
                key={filter.value}
                type="button"
                className="seg__btn"
                onClick={() => !disabled && changeTimeFilter(filter.value)}
                disabled={disabled}
                aria-pressed={query.timeFilter === filter.value}
                title={
                  disabled
                    ? `Your data only spans ${dateRange?.span_days} day(s) — this filter would show the same results as "All Time".`
                    : undefined
                }
              >
                {filter.label}
              </button>
            )
          })}
        </div>

        {/* ── Filters ──────────────────────────────────────────────────── */}
        <ErrorBoundary>
          <FilterPanel
            dimensions={dimensions}
            filters={query.filters}
            onChange={changeFilters}
            dateRange={dateRange}
            customRange={{ start: query.startDate ?? '', end: query.endDate ?? '' }}
            onCustomRangeChange={changeCustomRange}
            onClear={clearAll}
          />
        </ErrorBoundary>

        {/* ── Tabs ─────────────────────────────────────────────────────── */}
        <div className="seg w-full sm:w-auto min-w-0" role="tablist" aria-label="Dashboard view">
          {VIEW_TABS.map((tab) => (
            <button
              key={tab.value}
              role="tab"
              type="button"
              className="seg__btn"
              aria-selected={activeTab === tab.value}
              onClick={() => changeTab(tab.value)}
            >
              <Icon name={tab.icon} className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Short-span explainer — prevents "why are all filters the same?" */}
      {dateRange?.span_days > 0 && dateRange.span_days < 8 && (
        <p className="note" data-tone="info" role="note">
          <Icon name="info" className="w-4 h-4 shrink-0 mt-px" style={{ color: 'var(--accent-blue)' }} />
          <span>
            This file covers only <strong>{dateRange.span_days} day(s)</strong> ({dateRange.min_date} to{' '}
            {dateRange.max_date}). Wider presets are disabled because they'd show identical results to "All Time".
          </span>
        </p>
      )}

      {data.errors?.length > 0 && (
        <ErrorBoundary>
          <RowErrorsBanner errors={data.errors} />
        </ErrorBoundary>
      )}

      {/* ── Overview ───────────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="space-y-3 sm:space-y-4">
          {isEmpty ? (
            <EmptyPeriodState
              onReset={() => changeTimeFilter('all')}
              hasFilters={activeFilterCount > 0}
              onClear={clearAll}
            />
          ) : (
            <>
              <motion.div {...fadeUp}>
                <ErrorBoundary>
                  <InsightCards insights={insights} loading={insightsLoading} />
                </ErrorBoundary>
              </motion.div>

              <motion.div initial={fadeUp.initial} animate={fadeUp.animate} transition={{ ...fadeUp.transition, delay: 0.05 }}>
                <SummaryStats key={querySignature} summary={data.summary} />
              </motion.div>

              <motion.div initial={fadeUp.initial} animate={fadeUp.animate} transition={{ ...fadeUp.transition, delay: 0.1 }}>
                <ErrorBoundary>
                  <ForecastSummary
                    forecast={forecast}
                    loading={forecastLoading}
                    horizon={forecastHorizon}
                    onHorizonChange={setForecastHorizon}
                  />
                </ErrorBoundary>
              </motion.div>

              {/* Trend and the top-items chart share a row: both are the same
                  tokenised height, so the row has no ragged edge. */}
              <motion.div
                className="grid grid-cols-1 xl:grid-cols-2 gap-[var(--gap)] items-start"
                initial={fadeUp.initial}
                animate={fadeUp.animate}
                transition={{ ...fadeUp.transition, delay: 0.15 }}
              >
                <Card title="Daily trend & forecast" hint="Solid = actual · dashed = projection">
                  <ErrorBoundary>
                    <TrendChart
                      trend={data.daily_trend}
                      forecast={forecast}
                      anomalyDates={insights?.anomaly_dates ?? []}
                    />
                  </ErrorBoundary>
                </Card>

                <ErrorBoundary>
                  <TopItems items={data.top_items} />
                </ErrorBoundary>
              </motion.div>

              {/* The studio is the exploration surface, so it gets the full
                  page width — and correspondingly less height. */}
              <motion.div initial={fadeUp.initial} animate={fadeUp.animate} transition={{ ...fadeUp.transition, delay: 0.2 }}>
                <ErrorBoundary>
                  <ChartStudio
                    chartData={chartData}
                    heatmapData={heatmapData}
                    loading={chartLoading || heatmapLoading}
                    availableDimensions={dimensions}
                    view={chartView}
                    onViewChange={setChartView}
                    onDrillDown={handleDrillDown}
                    selectedLabel={drillSelection?.label}
                    wide
                  />
                </ErrorBoundary>
              </motion.div>

              <motion.div initial={fadeUp.initial} animate={fadeUp.animate} transition={{ ...fadeUp.transition, delay: 0.25 }}>
                <ErrorBoundary>
                  <DeadStockTable items={data.dead_stock} />
                </ErrorBoundary>
              </motion.div>
            </>
          )}
        </div>
      )}

      {/* ── Inventory ──────────────────────────────────────────────────── */}
      {activeTab === 'inventory' && (
        <ErrorBoundary>
          <InventoryPanel inventory={inventory} loading={inventoryLoading} forecast={forecast} />
        </ErrorBoundary>
      )}

      {/* ── Financial report ───────────────────────────────────────────── */}
      {activeTab === 'report' && (
        <div className="space-y-3 sm:space-y-4">
          {caReportError && (
            <p className="note" data-tone="danger">
              <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
              <span>{caReportError}</span>
            </p>
          )}
          <ErrorBoundary>
            {caReportLoading && !caReport ? (
              <div className="card card-pad space-y-2" aria-busy="true" aria-label="Building financial report">
                <div className="skeleton h-3 w-40 mb-1" />
                {[...Array(6)].map((_, index) => (
                  <div key={index} className="flex items-center justify-between gap-3">
                    <div className="skeleton h-2.5 flex-1" style={{ maxWidth: 180 }} />
                    <div className="skeleton h-2.5 w-20" />
                  </div>
                ))}
              </div>
            ) : (
              <PnLReportTable report={caReport} />
            )}
          </ErrorBoundary>
          <ErrorBoundary>
            <TransactionLedgerTable
              ledgerPage={ledgerPage}
              loading={ledgerLoading}
              onPageChange={(page) => fetchLedgerPage(fileId, { query, page, pageSize: 50 })}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* ── Drill-down overlay ─────────────────────────────────────────── */}
      <ErrorBoundary>
        <DrillDownPanel
          selection={drillSelection}
          ledger={drillLedger}
          loading={drillLoading}
          onClose={closeDrillDown}
          onPageChange={(page) =>
            openDrillDown(fileId, { dimension: drillSelection?.dimension, point: drillSelection, page })
          }
        />
      </ErrorBoundary>

      {/* ── ⌘K palette ─────────────────────────────────────────────────── */}
      <CommandPalette actions={paletteActions} />
    </section>
  )
}

/** Skeleton that mirrors the real layout's heights, so nothing jumps on load. */
function LoadingSkeleton() {
  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-[var(--gap)]">
        {[...Array(3)].map((_, index) => (
          <div key={index} className="card card-pad" style={{ height: 104 }}>
            <div className="skeleton h-2.5 w-24 mb-2.5" />
            <div className="skeleton h-2.5 w-full mb-1.5" />
            <div className="skeleton h-2.5 w-4/5" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-[var(--gap)]">
        {[...Array(5)].map((_, index) => (
          <div key={index} className="stat-tile" style={{ height: 76 }}>
            <div className="skeleton h-2 w-16 mb-2.5" />
            <div className="skeleton h-4 w-20" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-[var(--gap)]">
        {[...Array(2)].map((_, index) => (
          <div key={index} className="card card-pad">
            <div className="skeleton h-2.5 w-32 mb-3" />
            <div className="skeleton chart-box" />
          </div>
        ))}
      </div>
    </div>
  )
}

/** No file selected / no analytics yet. */
function NoFileState() {
  return (
    <div className="flex items-center justify-center py-16">
      <Helmet>
        <title>No Data — SENOVA Digital Lab</title>
      </Helmet>
      <motion.div
        className="card card-pad max-w-xs w-full text-center"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: EASE }}
      >
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-3"
          style={{ background: 'var(--gradient-accent-soft)' }}
        >
          <Icon name="chart" className="w-4.5 h-4.5" style={{ color: 'var(--accent-blue)' }} />
        </div>
        <p className="text-display text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          No analytics yet
        </p>
        <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
          Upload a sales file to generate your first dashboard.
        </p>
        <Link to="/upload" className="btn-gradient w-full">
          Upload a file
        </Link>
      </motion.div>
    </div>
  )
}

/**
 * Empty state for a period/filter combination with no rows. Every empty state
 * offers the action that fixes it — a blank panel with no way out is the
 * anti-pattern here.
 */
function EmptyPeriodState({ onReset, hasFilters, onClear }) {
  return (
    <div className="card card-pad text-center py-10 max-w-sm mx-auto">
      <Icon name="inbox" className="w-8 h-8 mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
      <h3 className="mb-1">No data for this selection</h3>
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
        {hasFilters
          ? 'Your filters and date range together match no transactions.'
          : 'The selected date range returned no matching records.'}
      </p>
      <div className="flex flex-wrap gap-2 justify-center">
        {hasFilters && (
          <button onClick={onClear} className="btn-primary" type="button">
            Clear filters
          </button>
        )}
        <button onClick={onReset} type="button" className="btn">
          Show all time
        </button>
      </div>
    </div>
  )
}
