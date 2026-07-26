import { create } from 'zustand'
import axios from 'axios'
import api from '../services/api'

/**
 * Single source of truth for upload + analytics state.
 *
 * Structure
 * ---------
 * 1. **Upload flow** — file → column-mapping preview → confirmed mapping.
 * 2. **Query state** — the date window and dimension filters that every Pro
 *    request carries, so the KPI cards, charts, insights, inventory, P&L and PDF
 *    always describe the same slice of data.
 * 3. **Fetchers** — one per endpoint. Each is cancellable: switching filter
 *    quickly must not let a slow earlier response overwrite a newer one.
 */

/** In-flight requests, keyed by purpose, so a newer call aborts the older one. */
const controllers = new Map()

function freshSignal(key) {
  controllers.get(key)?.abort()
  const controller = new AbortController()
  controllers.set(key, controller)
  return controller.signal
}

/** True for the "request superseded / component unmounted" cases we ignore. */
function isCancelled(error) {
  return axios.isCancel(error) || error?.code === 'ERR_CANCELED'
}

/** Human-readable error text, preferring the server's own explanation. */
function messageFrom(error, fallback) {
  if (error?.response?.status === 409) {
    return 'Please re-upload this file and confirm your column mapping.'
  }
  if (error?.response?.status === 404) {
    return 'This file is no longer available. Upload it again to continue.'
  }
  return error?.response?.data?.detail || error?.message || fallback
}

/**
 * Translate the UI's query state into the ``AnalysisQuery`` body the Pro
 * endpoints expect. Kept in one place so no caller can send a subtly different
 * shape (and get subtly different numbers).
 */
export function buildQueryBody(query) {
  const body = {
    time_filter: query.timeFilter ?? 'all',
    filters: query.filters ?? {},
  }
  if (query.timeFilter === 'custom') {
    body.start_date = query.startDate
    body.end_date = query.endDate
  }
  return body
}

const INITIAL_QUERY = {
  timeFilter: '30days',
  startDate: null,
  endDate: null,
  filters: {},
}

const useSalesStore = create((set, get) => ({
  // ── Upload state ───────────────────────────────────────────────────────
  data: null,
  isLoading: false,
  error: null,
  fileId: null,
  filename: '',
  validationMessage: '',
  uploadErrors: [],
  refreshKey: 0,

  /**
   * Column-mapping confirmation state — populated right after upload, cleared
   * once the user confirms. Every shop's export format is different, so this
   * screen always comes before analysis.
   */
  mappingPreview: null,

  /** Actual date span of the uploaded data (set once mapping is confirmed). */
  dateRange: null,

  /** Optional canonical fields this file provided (Branch, Discount, Stock…). */
  optionalFields: [],

  /**
   * Step 1 of upload: store the file server-side and get back our best guess at
   * the column mapping. No analysis runs yet.
   */
  uploadFile: async (file) => {
    set({
      isLoading: true,
      error: null,
      data: null,
      uploadErrors: [],
      mappingPreview: null,
      validationMessage: 'Uploading to server...',
    })

    try {
      const form = new FormData()
      form.append('file', file)

      const { data: preview } = await api.post('/upload/', form)

      set({
        fileId: preview.file_id,
        filename: preview.filename,
        mappingPreview: preview,
        validationMessage: '',
      })

      return preview
    } catch (err) {
      set({ error: messageFrom(err, 'Upload failed. Please try again.'), validationMessage: '' })
      throw err
    } finally {
      set({ isLoading: false })
    }
  },

  /**
   * Step 2: send the confirmed mapping. Runs row-level validation server-side
   * and persists the mapping so every later request reuses it.
   */
  confirmMapping: async (fileId, mapping) => {
    set({ isLoading: true, error: null, validationMessage: 'Validating your data...' })

    try {
      const { data: uploadRes } = await api.post(`/upload/${fileId}/confirm-mapping`, { mapping })

      if (uploadRes.valid_count === 0) {
        const msg = 'No valid rows found after mapping. Check your column choices and try again.'
        set({
          error: msg,
          uploadErrors: uploadRes.errors || [],
          validationMessage: '',
          mappingPreview: null,
        })
        throw new Error(msg)
      }

      set({
        uploadErrors: uploadRes.errors || [],
        validationMessage: '',
        mappingPreview: null,
        dateRange: uploadRes.date_range || null,
        optionalFields: uploadRes.optional_fields || [],
      })

      return uploadRes
    } catch (err) {
      set({ error: messageFrom(err, 'Could not validate your data. Please try again.'), validationMessage: '' })
      throw err
    } finally {
      set({ isLoading: false })
    }
  },

  cancelMapping: () => set({ mappingPreview: null, fileId: null, filename: '' }),

  clearUploadErrors: () => set({ uploadErrors: [] }),

  clearData: () =>
    set({
      data: null,
      error: null,
      fileId: null,
      filename: '',
      validationMessage: '',
      uploadErrors: [],
      mappingPreview: null,
      caReport: null,
      ledgerPage: null,
      dateRange: null,
      optionalFields: [],
      query: { ...INITIAL_QUERY },
      dimensions: [],
      chartData: null,
      heatmapData: null,
      insights: null,
      inventory: null,
      forecast: null,
      drillSelection: null,
      drillLedger: null,
    }),

  // ── Query state (shared by every Pro request) ──────────────────────────
  query: { ...INITIAL_QUERY },

  /** Merge a partial change into the query (e.g. just the filters). */
  setQuery: (partial) => set((state) => ({ query: { ...state.query, ...partial } })),

  resetFilters: () =>
    set((state) => ({
      query: { ...state.query, filters: {}, timeFilter: state.query.timeFilter === 'custom' ? 'all' : state.query.timeFilter, startDate: null, endDate: null },
    })),

  // ── Dimensions available in the current file ───────────────────────────
  dimensions: [],
  dimensionsLoading: false,

  fetchDimensions: async (fileId) => {
    set({ dimensionsLoading: true })
    try {
      const { data } = await api.get(`/analytics/${fileId}/dimensions`, {
        signal: freshSignal('dimensions'),
      })
      set({
        dimensions: data.dimensions ?? [],
        dateRange: data.date_range ?? get().dateRange,
        optionalFields: data.optional_measures ?? get().optionalFields,
        dimensionsLoading: false,
      })
    } catch (err) {
      if (isCancelled(err)) return
      // A missing dimensions call must not block the dashboard: the filter panel
      // simply shows nothing to filter on.
      set({ dimensions: [], dimensionsLoading: false })
    }
  },

  // ── KPIs / trend / top items / categories / dead stock ────────────────
  /**
   * Pro summary fetch. Sends the full query body so filters and custom ranges
   * apply to every number on the page.
   */
  fetchAnalytics: async (fileId, query = get().query) => {
    set({ isLoading: true, error: null, validationMessage: 'Loading analytics...' })

    try {
      const { data } = await api.post(`/analytics/${fileId}/summary`, buildQueryBody(query), {
        signal: freshSignal('summary'),
      })
      // A fresh object graph guarantees new references, so memoised chart
      // components actually re-render when the numbers change.
      set((state) => ({
        data: {
          ...data,
          summary: data.summary
            ? {
                ...data.summary,
                revenue: { ...data.summary.revenue },
                profit: { ...data.summary.profit },
                cost: { ...data.summary.cost },
                units_sold: { ...data.summary.units_sold },
                unique_items_sold: { ...data.summary.unique_items_sold },
              }
            : data.summary,
        },
        isLoading: false,
        refreshKey: state.refreshKey + 1,
        validationMessage: '',
      }))
    } catch (err) {
      if (isCancelled(err)) return
      set({
        error: messageFrom(err, 'Failed to load dashboard. Please retry.'),
        isLoading: false,
        validationMessage: '',
      })
    }
  },

  // ── Chart studio ──────────────────────────────────────────────────────
  chartData: null,
  chartLoading: false,
  chartError: null,

  fetchChartData: async (fileId, query, { dimension, measure, topN = 10 }) => {
    set({ chartLoading: true, chartError: null })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/chart-data`,
        { ...buildQueryBody(query), dimension, measure, top_n: topN },
        { signal: freshSignal('chart') },
      )
      set({ chartData: data, chartLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ chartError: messageFrom(err, 'Could not build that chart.'), chartLoading: false })
    }
  },

  heatmapData: null,
  heatmapLoading: false,

  fetchHeatmap: async (fileId, query, measure = 'revenue') => {
    set({ heatmapLoading: true })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/heatmap`,
        { ...buildQueryBody(query), measure },
        { signal: freshSignal('heatmap') },
      )
      set({ heatmapData: data, heatmapLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ heatmapLoading: false })
    }
  },

  // ── Feature 1: insights ───────────────────────────────────────────────
  insights: null,
  insightsLoading: false,

  fetchInsights: async (fileId, query = get().query) => {
    set({ insightsLoading: true })
    try {
      const { data } = await api.post(`/analytics/${fileId}/insights`, buildQueryBody(query), {
        signal: freshSignal('insights'),
      })
      set({ insights: data, insightsLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ insights: null, insightsLoading: false })
    }
  },

  // ── Feature 3: inventory ──────────────────────────────────────────────
  inventory: null,
  inventoryLoading: false,

  fetchInventory: async (fileId, query = get().query) => {
    set({ inventoryLoading: true })
    try {
      const { data } = await api.post(`/analytics/${fileId}/inventory`, buildQueryBody(query), {
        signal: freshSignal('inventory'),
      })
      set({ inventory: data, inventoryLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ inventory: null, inventoryLoading: false })
    }
  },

  // ── Feature 2: forecast ───────────────────────────────────────────────
  forecast: null,
  forecastLoading: false,
  forecastHorizon: 14,

  setForecastHorizon: (horizon) => set({ forecastHorizon: horizon }),

  fetchForecast: async (fileId, query = get().query, horizon = get().forecastHorizon) => {
    set({ forecastLoading: true })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/forecast`,
        { ...buildQueryBody(query), horizon },
        { signal: freshSignal('forecast') },
      )
      set({ forecast: data, forecastLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ forecast: null, forecastLoading: false })
    }
  },

  // ── CA-style financial report (P&L + category ledger) ─────────────────
  caReport: null,
  caReportLoading: false,
  caReportError: null,

  fetchCAReport: async (fileId, query = get().query) => {
    set({ caReportLoading: true, caReportError: null })
    try {
      const { data } = await api.post(`/analytics/${fileId}/report`, buildQueryBody(query), {
        signal: freshSignal('report'),
      })
      set({ caReport: data, caReportLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ caReportError: messageFrom(err, 'Failed to load the financial report.'), caReportLoading: false })
    }
  },

  // ── Detailed transaction ledger (paginated) ───────────────────────────
  ledgerPage: null,
  ledgerLoading: false,
  ledgerError: null,

  fetchLedgerPage: async (fileId, { query = get().query, page = 1, pageSize = 50 } = {}) => {
    set({ ledgerLoading: true, ledgerError: null })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/ledger`,
        { ...buildQueryBody(query), page, page_size: pageSize },
        { signal: freshSignal('ledger') },
      )
      set({ ledgerPage: data, ledgerLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ ledgerError: messageFrom(err, 'Failed to load the transaction ledger.'), ledgerLoading: false })
    }
  },

  // ── Feature 5: drill-down ─────────────────────────────────────────────
  drillSelection: null,
  drillLedger: null,
  drillLoading: false,

  closeDrillDown: () => set({ drillSelection: null, drillLedger: null }),

  /**
   * Open the drill-down for one chart group.
   *
   * Category/item/branch-style groups become an extra filter. Time groups can't
   * be filtered that way (the server rejects time dimensions as filters, by
   * design), so a clicked day or month becomes a custom date range instead —
   * which is the same thing expressed correctly.
   */
  openDrillDown: async (fileId, { dimension, point, page = 1 }) => {
    if (!point) return
    const baseQuery = get().query
    const query = { ...baseQuery, filters: { ...baseQuery.filters } }

    if (dimension === 'day') {
      query.timeFilter = 'custom'
      query.startDate = point.label
      query.endDate = point.label
    } else if (dimension === 'month') {
      // "2026-07" → the whole of that month.
      const [year, month] = point.label.split('-').map(Number)
      const lastDay = new Date(year, month, 0).getDate()
      query.timeFilter = 'custom'
      query.startDate = `${point.label}-01`
      query.endDate = `${point.label}-${String(lastDay).padStart(2, '0')}`
    } else if (dimension === 'weekday') {
      // A weekday isn't a contiguous range and isn't a filterable column, so
      // there is nothing honest to drill into here.
      return
    } else {
      query.filters[dimension] = [point.label]
    }

    set({ drillSelection: { ...point, dimension }, drillLoading: true, drillLedger: null })

    try {
      const { data } = await api.post(
        `/analytics/${fileId}/ledger`,
        { ...buildQueryBody(query), page, page_size: 25 },
        { signal: freshSignal('drill') },
      )
      set({ drillLedger: data, drillLoading: false })
    } catch (err) {
      if (isCancelled(err)) return
      set({ drillLoading: false })
    }
  },
}))

export default useSalesStore
