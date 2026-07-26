import { lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

import api from '../services/api'
import useSalesStore, { buildQueryBody } from '../store/useSalesStore'
import Card from '../components/common/Card'
import ErrorBoundary from '../components/common/ErrorBoundary'
import Icon from '../components/common/Icon'
import Loader from '../components/common/Loader'
import SummaryStats from '../components/dashboard/SummaryStats'

// Everything below the KPI row is code-split: the Financial Report and
// Inventory tabs are never downloaded until the user opens them.
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
 * Layout follows the "answer first" idea: automated findings sit at the top,
 * then the KPI row, then the forecast + trend, then the chart studio for
 * open-ended exploration, and finally the item tables. Inventory and the
 * CA-style financial report are separate tabs.
 *
 * All view state (tab, date window, custom range, filters) is mirrored into the
 * URL, so a filtered view survives a refresh and can be shared with an
 * accountant — deep-linkable state is an explicit UX requirement for dashboards.
 */

const DATE_FILTERS = [
  { value: 'today', label: 'Today', minSpanDays: 1 },
  { value: 'week', label: 'Last 7 Days', minSpanDays: 8 },
  { value: '30days', label: 'Last 30 Days', minSpanDays: 31 },
  { value: 'month', label: 'This Month', minSpanDays: 8 },
  { value: 'all', label: 'All Time', minSpanDays: 1 },
]

const VIEW_TABS = [
  { value: 'overview', label: 'Overview', icon: 'chart' },
  { value: 'inventory', label: 'Inventory', icon: 'box' },
  { value: 'report', label: 'Financial Report', icon: 'document' },
]

/**
 * A preset is meaningless when the data's span doesn't exceed its window — it
 * would return exactly the same rows as "All Time", which reads as a bug.
 * Disabling (not hiding) it keeps the UI predictable and lets a tooltip explain.
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
  const [chartRequest, setChartRequest] = useState({
    dimension: 'category',
    measure: 'revenue',
    top_n: 10,
    needsHeatmap: false,
  })

  // ── Hydrate query state from the URL once per navigation ───────────────
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
    // Intentionally keyed on the raw search string: this runs on back/forward
    // navigation, not on every state change we ourselves make.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  useEffect(() => {
    if (!fileId) return
    if (useSalesStore.getState().fileId !== fileId) {
      useSalesStore.setState({ fileId })
    }
    fetchDimensions(fileId)
  }, [fileId, fetchDimensions])

  // A custom range is only valid once both ends are picked.
  const queryReady = query.timeFilter !== 'custom' || Boolean(query.startDate && query.endDate)

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
    syncUrl({ filters: {}, timeFilter: query.timeFilter === 'custom' ? 'all' : query.timeFilter, startDate: null, endDate: null })
  }

  const handleDrillDown = (point) => {
    if (!fileId) return
    openDrillDown(fileId, { dimension: chartRequest.dimension, point })
  }

  const exportPDF = async () => {
    if (!fileId) return
    setExporting(true)
    try {
      // The PDF is generated server-side as real tables (P&L, findings,
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

  // ── Guard states ───────────────────────────────────────────────────────

  if (!fileId) {
    return <NoFileState />
  }

  if (isLoading && !data) return <LoadingSkeleton />

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 md:py-24 text-center px-4">
        <Helmet>
          <title>Error — SENOVA Digital Lab</title>
        </Helmet>
        <div className="p-4 rounded-full mb-4" style={{ background: 'rgba(239,68,68,0.1)' }}>
          <Icon name="alert" className="w-8 h-8" style={{ color: 'var(--accent-red)' }} />
        </div>
        <p className="text-lg font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
          Something went wrong
        </p>
        <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
          {error}
        </p>
        <Link to="/upload" className="underline underline-offset-2" style={{ color: 'var(--accent-blue)' }}>
          Upload a new file
        </Link>
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
    <section className="space-y-5 sm:space-y-7">
      <Helmet>
        <title>Dashboard — SENOVA Digital Lab | Retail &amp; MSME Analytics</title>
        <meta
          name="description"
          content="AI retail analytics: automated insights, revenue forecasting, reorder intelligence, seven chart types and drill-down into every transaction."
        />
      </Helmet>

      {/* ── Header: title, presets, export ──────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Analytics Overview
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            All values in INR (₹) · {periodLabel}
            {activeFilterCount > 0 && ` · ${activeFilterCount} filter(s) applied`}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div
            role="group"
            aria-label="Filter analytics by date range"
            className="flex items-center gap-1 p-1 rounded-xl overflow-x-auto"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}
          >
            {DATE_FILTERS.map((filter) => {
              const disabled = !isFilterMeaningful(filter, dateRange?.span_days)
              const active = query.timeFilter === filter.value
              return (
                <button
                  key={filter.value}
                  onClick={() => !disabled && changeTimeFilter(filter.value)}
                  disabled={disabled}
                  aria-pressed={active}
                  title={
                    disabled
                      ? `Your data only spans ${dateRange?.span_days} day(s) — this filter would show the same results as "All Time".`
                      : undefined
                  }
                  className="text-xs font-medium rounded-lg whitespace-nowrap transition-colors"
                  style={{
                    padding: '10px 14px',
                    minHeight: 40,
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled ? 0.35 : 1,
                    background: active
                      ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                      : 'transparent',
                    color: active ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                    boxShadow: active ? '0 2px 8px var(--accent-blue-glow)' : 'none',
                  }}
                >
                  {filter.label}
                </button>
              )
            })}
          </div>

          <button
            onClick={exportPDF}
            disabled={exporting}
            aria-busy={exporting}
            className="btn-primary flex items-center justify-center gap-2 whitespace-nowrap cursor-pointer"
          >
            <Icon name="download" className="w-4 h-4" />
            {exporting ? 'Generating…' : 'Export PDF'}
          </button>
        </div>
      </div>

      {/* ── Filters ─────────────────────────────────────────────────── */}
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

      {/* Short-span explainer — prevents "why are all filters the same?" */}
      {dateRange?.span_days > 0 && dateRange.span_days < 8 && (
        <div
          className="card px-4 sm:px-5 py-3 flex items-start gap-3"
          style={{ border: '1px solid var(--border-active)' }}
          role="note"
        >
          <Icon name="info" className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Your uploaded data covers only{' '}
            <strong style={{ color: 'var(--text-primary)' }}>{dateRange.span_days} day(s)</strong> (
            {dateRange.min_date} to {dateRange.max_date}). Wider presets are disabled because they'd show
            identical results to "All Time" — there simply isn't more data to compare yet.
          </p>
        </div>
      )}

      {data.errors?.length > 0 && (
        <ErrorBoundary>
          <RowErrorsBanner errors={data.errors} />
        </ErrorBoundary>
      )}

      {/* ── Tabs ────────────────────────────────────────────────────── */}
      <div
        role="tablist"
        aria-label="Dashboard view"
        className="flex items-center gap-1 p-1 rounded-xl w-fit"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}
      >
        {VIEW_TABS.map((tab) => {
          const active = activeTab === tab.value
          return (
            <button
              key={tab.value}
              role="tab"
              aria-selected={active}
              onClick={() => changeTab(tab.value)}
              className="flex items-center gap-2 text-xs sm:text-sm font-medium rounded-lg cursor-pointer transition-colors"
              style={{
                padding: '10px 14px',
                minHeight: 40,
                background: active
                  ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                  : 'transparent',
                color: active ? 'var(--text-on-accent)' : 'var(--text-secondary)',
              }}
            >
              <Icon name={tab.icon} className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* ── Overview ────────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="space-y-5 sm:space-y-7">
          {isEmpty ? (
            <EmptyPeriodState onReset={() => changeTimeFilter('all')} hasFilters={activeFilterCount > 0} onClear={clearAll} />
          ) : (
            <>
              <ErrorBoundary>
                <InsightCards insights={insights} loading={insightsLoading} />
              </ErrorBoundary>

              <SummaryStats key={querySignature} summary={data.summary} />

              <ErrorBoundary>
                <ForecastSummary
                  forecast={forecast}
                  loading={forecastLoading}
                  horizon={forecastHorizon}
                  onHorizonChange={setForecastHorizon}
                />
              </ErrorBoundary>

              <Card title="Daily Sales Trend & Forecast">
                <ErrorBoundary>
                  <TrendChart
                    trend={data.daily_trend}
                    forecast={forecast}
                    anomalyDates={insights?.anomaly_dates ?? []}
                  />
                </ErrorBoundary>
              </Card>

              <ErrorBoundary>
                <ChartStudio
                  chartData={chartData}
                  heatmapData={heatmapData}
                  loading={chartLoading || heatmapLoading}
                  availableDimensions={dimensions}
                  onQueryChange={setChartRequest}
                  onDrillDown={handleDrillDown}
                  selectedLabel={drillSelection?.label}
                />
              </ErrorBoundary>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-6">
                <ErrorBoundary>
                  <TopItems items={data.top_items} />
                </ErrorBoundary>
                <ErrorBoundary>
                  <DeadStockTable items={data.dead_stock} />
                </ErrorBoundary>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Inventory ───────────────────────────────────────────────── */}
      {activeTab === 'inventory' && (
        <ErrorBoundary>
          <InventoryPanel inventory={inventory} loading={inventoryLoading} forecast={forecast} />
        </ErrorBoundary>
      )}

      {/* ── Financial report ────────────────────────────────────────── */}
      {activeTab === 'report' && (
        <div className="space-y-5 sm:space-y-7">
          {caReportError && (
            <div className="card px-4 py-3" style={{ border: '1px solid rgba(239,68,68,0.3)' }}>
              <p className="text-sm" style={{ color: 'var(--accent-red)' }}>
                {caReportError}
              </p>
            </div>
          )}
          <ErrorBoundary>
            {caReportLoading && !caReport ? (
              <Loader message="Building financial report…" />
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

      {/* ── Drill-down overlay ──────────────────────────────────────── */}
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
    </section>
  )
}

/** Skeleton that reserves the real layout's height, so nothing jumps on load. */
function LoadingSkeleton() {
  return (
    <div className="space-y-6 sm:space-y-8 animate-pulse">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
        {[...Array(3)].map((_, index) => (
          <div key={index} className="card p-4" style={{ minHeight: 120 }}>
            <div className="h-3 rounded w-24 mb-3" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-3 rounded w-full mb-2" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-3 rounded w-4/5" style={{ background: 'var(--bg-skeleton)' }} />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        {[...Array(5)].map((_, index) => (
          <div key={index} className="card p-4 sm:p-6">
            <div className="h-3 rounded w-20 mb-3" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-7 rounded w-28" style={{ background: 'var(--bg-skeleton)' }} />
          </div>
        ))}
      </div>
      <div className="card p-4 sm:p-6">
        <div className="h-4 rounded w-48 mb-6" style={{ background: 'var(--bg-skeleton)' }} />
        <div className="h-64 rounded" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
      </div>
    </div>
  )
}

/** No file selected / no analytics yet. */
function NoFileState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 md:py-24 text-center px-4">
      <Helmet>
        <title>No Data — SENOVA Digital Lab</title>
      </Helmet>
      <div className="card max-w-sm w-full p-8">
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
          style={{ background: 'var(--accent-blue-glow)' }}
        >
          <Icon name="chart" className="w-6 h-6" style={{ color: 'var(--accent-blue)' }} />
        </div>
        <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
          No analytics yet
        </p>
        <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
          Upload a sales file to generate your first dashboard.
        </p>
        <Link to="/upload" className="btn-primary inline-block cursor-pointer">
          Upload a file
        </Link>
      </div>
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
    <div className="flex flex-col items-center justify-center py-16 text-center card max-w-md mx-auto">
      <Icon name="inbox" className="w-10 h-10 mb-4" style={{ color: 'var(--text-muted)' }} />
      <h3 className="text-lg font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
        No data for this selection
      </h3>
      <p className="text-sm mb-6 px-6" style={{ color: 'var(--text-secondary)' }}>
        {hasFilters
          ? 'Your filters and date range together match no transactions.'
          : 'The selected date range returned no matching records.'}
      </p>
      <div className="flex flex-wrap gap-3 justify-center">
        {hasFilters && (
          <button onClick={onClear} className="btn-primary cursor-pointer" type="button">
            Clear filters
          </button>
        )}
        <button
          onClick={onReset}
          type="button"
          className="cursor-pointer rounded-lg px-4"
          style={{ minHeight: 40, border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
        >
          Show all time
        </button>
      </div>
    </div>
  )
}
