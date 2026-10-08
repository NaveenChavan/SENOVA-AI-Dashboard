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
  const signal = controller.signal
  // AbortController cancellation is necessary but not sufficient: a response
  // can still win the race if it resolves after abort. Tag the signal so every
  // fetcher can ignore any response that is no longer the newest request.
  signal.__senovaController = controller
  controllers.set(key, controller)
  return signal
}

function isLatestSignal(key, signal) {
  return Boolean(signal && controllers.get(key) === signal.__senovaController)
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

/**
 * Opt-in AI consent, in localStorage.
 *
 * UX only — the real guarantee is server-side. Both Gemini-calling endpoints
 * require `ai_consent` explicitly, so this value can only ever *withhold* a
 * request, never widen one. Kept under a versioned key so a future consent
 * that covers more than this does not silently inherit an older answer.
 */
const CONSENT_KEY = 'senova.aiConsent.v1'

/** 'granted' | 'declined', or null when the user has never been asked. */
export function readStoredConsent() {
  try {
    const raw = window.localStorage.getItem(CONSENT_KEY)
    return raw === 'granted' || raw === 'declined' ? raw : null
  } catch {
    // Private browsing or storage disabled. "Not answered" is the safe reading:
    // the server then sends nothing, and we ask again next time.
    return null
  }
}

export function writeStoredConsent(answer) {
  try {
    if (answer) window.localStorage.setItem(CONSENT_KEY, answer)
    else window.localStorage.removeItem(CONSENT_KEY)
  } catch {
    // Consent still applies for this session in memory; only the memory of it
    // is lost, which costs one extra prompt.
  }
}

/**
 * Index the AI rewrites by insight id, keeping only the verified ones.
 *
 * Done here rather than in the component so an unverified rewrite has no path
 * to the screen at all: the guarantee is "the UI cannot render it", not "the UI
 * is careful not to render it". The backend already decided this, so this is a
 * filter, not a second opinion — but the render is the thing worth making
 * unforgeable, because a bug there would put an invented number on a card.
 */
export function verifiedNarratives(aiText) {
  const map = {}
  for (const entry of aiText ?? []) {
    if (entry?.verified && entry?.text) map[entry.id] = entry.text
  }
  return map
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

  // ── Opt-in AI (2-tier column understanding) ───────────────────────────
  //
  // 'granted' | 'declined' | null. Null is the common first-run state and means
  // the upload page still owes the user a decision — not that consent is
  // assumed either way.
  aiConsentAnswer: readStoredConsent(),
  aiConsent: readStoredConsent() === 'granted',

  /** Whether the server says the AI tier could run at all (from GET /health). */
  aiAvailable: false,
  aiCapabilitiesLoading: false,

  /** Server explanation when the AI tier was unavailable or failed. */
  aiNotice: null,

  /** Real per-stage milliseconds from the last upload — measured, not invented. */
  pipelineTimings: null,

  /** Record the answer and remember it. Called by the consent modal. */
  persistConsent: (granted) => {
    const answer = granted ? 'granted' : 'declined'
    writeStoredConsent(answer)
    set({ aiConsent: granted, aiConsentAnswer: answer })
  },

  /**
   * Ask the server whether AI disambiguation is even available.
   *
   * Needed before uploading, because consent travels on the upload request
   * itself: a page that only learned the answer afterwards could never grant it
   * on the first upload. A failed probe reports "not available" on purpose —
   * with consent unset the server sends nothing either way, so a wrong "no" is
   * merely a missing prompt, while a wrong "yes" would be a consent the user
   * never gave.
   */
  fetchAiCapabilities: async () => {
    set({ aiCapabilitiesLoading: true })
    try {
      const { data } = await api.get('/health')
      const available = Boolean(data?.ai_enabled)
      set({ aiAvailable: available, aiCapabilitiesLoading: false })
      return available
    } catch {
      set({ aiAvailable: false, aiCapabilitiesLoading: false })
      return false
    }
  },

  /**
   * Step 1: store the file server-side and get back our best guess at
   * the column mapping. No analysis runs yet.
   */
  uploadFile: async (file) => {
    set({
      isLoading: true,
      error: null,
      data: null,
      uploadErrors: [],
      mappingPreview: null,
      aiNotice: null,
      pipelineTimings: null,
      validationMessage: 'Uploading to server...',
    })

    try {
      const form = new FormData()
      form.append('file', file)
      // Always sent, and false unless the user actively granted consent. The
      // server defaults an omitted field to false too, so this is belt and
      // braces — the point is that forgetting to send it can never widen
      // consent, only withhold it.
      form.append('ai_consent', get().aiConsent ? 'true' : 'false')

      const { data: preview } = await api.post('/upload/', form)

      set({
        fileId: preview.file_id,
        filename: preview.filename,
        mappingPreview: preview,
        // The server's own account of what it could and could not do, plus the
        // measured stage timings. Both are absent on an older backend.
        aiNotice: preview.ai_notice ?? null,
        pipelineTimings: preview.pipeline_timings ?? null,
        aiAvailable: preview.ai_enabled ?? get().aiAvailable,
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
   * Step 1.5: Run Tier 2 asynchronously if needed
   */
  runTier2Async: async (fileId) => {
    try {
      const currentConsent = useSalesStore.getState().aiConsent
      const { data: updatedPreview } = await api.post(`/upload/${fileId}/tier2`, {
        ai_consent: currentConsent
      })
      set((state) => {
        if (!state.mappingPreview || state.fileId !== fileId) return state
        // Keep the original preview but update the columns and timings
        return {
          mappingPreview: {
            ...state.mappingPreview,
            detected_columns: updatedPreview.detected_columns,
            ai_notice: updatedPreview.ai_notice ?? state.mappingPreview.ai_notice,
            pipeline_timings: updatedPreview.pipeline_timings ?? state.mappingPreview.pipeline_timings
          },
          aiNotice: updatedPreview.ai_notice ?? state.aiNotice,
          pipelineTimings: updatedPreview.pipeline_timings ?? state.pipelineTimings
        }
      })
      return updatedPreview
    } catch (err) {
      // Background AI failures shouldn't block the UI, just leave it as manual mapping
      // but WE MUST show the reason code so it doesn't fail silently.
      console.warn('Background AI tier failed:', err)
      
      const fallbackNotice = {
        reason_code: err.response?.data?.detail?.reason_code || err.response?.data?.reason_code || 'server_error',
        message: err.response?.data?.detail?.message || err.response?.data?.message || 'Background AI failed.'
      }
      
      set((state) => {
        if (!state.mappingPreview || state.fileId !== fileId) return state
        
        // Count how many are still pending (which will now fall back to manual mapping)
        const affected = state.mappingPreview.detected_columns.filter(c => c.source === 'pending').length
        const notice = { ...fallbackNotice, affected_columns: affected }
        
        const fallbackColumns = state.mappingPreview.detected_columns.map(c => 
          c.source === 'pending' ? { ...c, source: 'fallback' } : c
        )
        
        return {
          mappingPreview: {
            ...state.mappingPreview,
            detected_columns: fallbackColumns,
            ai_notice: notice
          },
          aiNotice: notice
        }
      })
      return null
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
      aiNotice: null,
      pipelineTimings: null,
      dynamicSchema: null,
      aiNarratives: {},
      aiSource: 'skipped',
      aiInsightNotice: null,
      aiInsightReasonCode: null,
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
    const signal = freshSignal('dimensions')
    set({ dimensionsLoading: true })
    try {
      const { data } = await api.get(`/analytics/${fileId}/dimensions`, { signal })
      if (!isLatestSignal('dimensions', signal)) return
      set({
        dimensions: data.dimensions ?? [],
        dateRange: data.date_range ?? get().dateRange,
        optionalFields: data.optional_measures ?? get().optionalFields,
        dimensionsLoading: false,
      })
      return data
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('dimensions', signal)) return
      // A missing dimensions call must not block the dashboard: the filter panel
      // simply shows nothing to filter on.
      set({ dimensions: [], dimensionsLoading: false })
    }
  },

  /**
   * Search one dimension using the current staged filters. The backend excludes
   * the dimension being edited from the context, which makes Category ↔ Item
   * cascading deterministic and makes Invoice No search work beyond the initial
   * 200-value metadata preview.
   */
  fetchDimensionOptions: async (fileId, request) => {
    const key = `dimension-options:${request?.dimension ?? 'unknown'}`
    const signal = freshSignal(key)
    try {
      const { data } = await api.post(`/analytics/${fileId}/dimensions/options`, request, { signal })
      if (!isLatestSignal(key, signal)) return null
      return data
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal(key, signal)) return null
      throw err
    }
  },

  // ── KPIs / trend / top items / categories / dead stock ────────────────
  /**
   * Pro summary fetch. Sends the full query body so filters and custom ranges
   * apply to every number on the page.
   */
  fetchAnalytics: async (fileId, query = get().query) => {
    const signal = freshSignal('summary')
    set({ isLoading: true, error: null, validationMessage: 'Loading analytics...' })

    try {
      const { data } = await api.post(`/analytics/${fileId}/summary`, buildQueryBody(query), { signal })
      if (!isLatestSignal('summary', signal)) return
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
      if (isCancelled(err) || !isLatestSignal('summary', signal)) return
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
    const signal = freshSignal('chart')
    set({ chartLoading: true, chartError: null })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/chart-data`,
        { ...buildQueryBody(query), dimension, measure, top_n: topN },
        { signal },
      )
      if (!isLatestSignal('chart', signal)) return
      set({ chartData: data, chartLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('chart', signal)) return
      set({ chartError: messageFrom(err, 'Could not build that chart.'), chartLoading: false })
    }
  },

  heatmapData: null,
  heatmapLoading: false,

  fetchHeatmap: async (fileId, query, measure = 'revenue') => {
    const signal = freshSignal('heatmap')
    set({ heatmapLoading: true })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/heatmap`,
        { ...buildQueryBody(query), measure },
        { signal },
      )
      if (!isLatestSignal('heatmap', signal)) return
      set({ heatmapData: data, heatmapLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('heatmap', signal)) return
      set({ heatmapLoading: false })
    }
  },

  // ── Feature 1: insights ───────────────────────────────────────────────
  insights: null,
  insightsLoading: false,

  /**
   * The deterministic insights, unchanged and always fetched the same way.
   *
   * Kept separate from `fetchAiInsights` below because it is the correctness
   * guarantee: every figure in it is computed by `insights_engine`, so it works
   * with the whole AI tier switched off and is what every other widget's
   * numbers are reconciled against.
   */
  fetchInsights: async (fileId, query = get().query) => {
    const signal = freshSignal('insights')
    set({ insightsLoading: true })
    try {
      const { data } = await api.post(`/analytics/${fileId}/insights`, buildQueryBody(query), { signal })
      if (!isLatestSignal('insights', signal)) return
      set({ insights: data, insightsLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('insights', signal)) return
      set({ insights: null, insightsLoading: false })
    }
  },

  // ── Opt-in AI: same findings, nicer wording ───────────────────────────
  aiNarratives: {},
  aiSource: 'skipped',
  aiInsightNotice: null,
  aiInsightReasonCode: null,

  /**
   * The same findings plus AI-written wording, where every figure in that
   * wording traces back to the insight's own metrics.
   *
   * This is a *superset* of `fetchInsights`, not a replacement, so it is called
   * in addition to it rather than instead of it: if this request fails the
   * dashboard still has the deterministic sentences, and no number that the
   * engine did not compute is ever shown.
   */
  fetchAiInsights: async (fileId, query = get().query) => {
    const signal = freshSignal('ai-insights')
    set({ aiInsightLoading: true })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/ai-insights`,
        { ...buildQueryBody(query), ai_consent: get().aiConsent },
        { signal },
      )
      if (!isLatestSignal('ai-insights', signal)) return
      set({
        aiNarratives: verifiedNarratives(data?.ai_text),
        aiSource: data?.ai_source ?? 'skipped',
        aiInsightNotice: data?.ai_notice ?? null,
        aiInsightReasonCode: data?.ai_reason_code ?? null,
        aiInsightElapsedMs: data?.ai_elapsed_ms ?? 0,
        aiInsightLoading: false,
      })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('ai-insights', signal)) return
      // Loses wording only. The insights themselves came from the other call
      // and are untouched, so there is nothing to recover here.
      set({ aiNarratives: {}, aiInsightNotice: null, aiInsightReasonCode: null, aiInsightLoading: false })
    }
  },

  aiInsightLoading: false,
  aiInsightElapsedMs: 0,

  // ── Dynamic schema: what this particular file can be asked ────────────
  dynamicSchema: null,
  schemaLoading: false,

  /**
   * Ask the server which cards, charts, dimensions and measures *this* file can
   * actually produce, each flagged unavailable with the reason when it isn't.
   *
   * Purely additive: it carries no business figures, so it cannot disagree with
   * the numbers already on the page. A failure is swallowed on purpose — a file
   * whose mapping is not confirmed yet answers 409, and the dashboard must not
   * fall over because an optional panel could not load.
   */
  fetchSchema: async (fileId) => {
    const signal = freshSignal('schema')
    set({ schemaLoading: true })
    try {
      const { data } = await api.post(`/analytics/${fileId}/schema`, null, { signal })
      if (!isLatestSignal('schema', signal)) return null
      set({ dynamicSchema: data, schemaLoading: false })
      return data
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('schema', signal)) return
      set({ dynamicSchema: null, schemaLoading: false })
    }
  },

  // ── Feature 3: inventory ──────────────────────────────────────────────
  inventory: null,
  inventoryLoading: false,

  fetchInventory: async (fileId, query = get().query) => {
    const signal = freshSignal('inventory')
    set({ inventoryLoading: true })
    try {
      const { data } = await api.post(`/analytics/${fileId}/inventory`, buildQueryBody(query), { signal })
      if (!isLatestSignal('inventory', signal)) return
      set({ inventory: data, inventoryLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('inventory', signal)) return
      set({ inventory: null, inventoryLoading: false })
    }
  },

  // ── Feature 2: forecast ───────────────────────────────────────────────
  forecast: null,
  forecastLoading: false,
  forecastHorizon: 14,

  setForecastHorizon: (horizon) => set({ forecastHorizon: horizon }),

  fetchForecast: async (fileId, query = get().query, horizon = get().forecastHorizon) => {
    const signal = freshSignal('forecast')
    set({ forecastLoading: true })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/forecast`,
        { ...buildQueryBody(query), horizon },
        { signal },
      )
      if (!isLatestSignal('forecast', signal)) return
      set({ forecast: data, forecastLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('forecast', signal)) return
      set({ forecast: null, forecastLoading: false })
    }
  },

  // ── CA-style financial report (P&L + category ledger) ─────────────────
  caReport: null,
  caReportLoading: false,
  caReportError: null,

  fetchCAReport: async (fileId, query = get().query) => {
    const signal = freshSignal('report')
    set({ caReportLoading: true, caReportError: null })
    try {
      const { data } = await api.post(`/analytics/${fileId}/report`, buildQueryBody(query), { signal })
      if (!isLatestSignal('report', signal)) return
      set({ caReport: data, caReportLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('report', signal)) return
      set({ caReportError: messageFrom(err, 'Failed to load the financial report.'), caReportLoading: false })
    }
  },

  // ── Detailed transaction ledger (paginated) ───────────────────────────
  ledgerPage: null,
  ledgerLoading: false,
  ledgerError: null,

  fetchLedgerPage: async (fileId, { query = get().query, page = 1, pageSize = 50 } = {}) => {
    const signal = freshSignal('ledger')
    set({ ledgerLoading: true, ledgerError: null })
    try {
      const { data } = await api.post(
        `/analytics/${fileId}/ledger`,
        { ...buildQueryBody(query), page, page_size: pageSize },
        { signal },
      )
      if (!isLatestSignal('ledger', signal)) return
      set({ ledgerPage: data, ledgerLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('ledger', signal)) return
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

    const signal = freshSignal('drill')
    set({ drillSelection: { ...point, dimension }, drillLoading: true, drillLedger: null })

    try {
      const { data } = await api.post(
        `/analytics/${fileId}/ledger`,
        { ...buildQueryBody(query), page, page_size: 25 },
        { signal },
      )
      if (!isLatestSignal('drill', signal)) return
      set({ drillLedger: data, drillLoading: false })
    } catch (err) {
      if (isCancelled(err) || !isLatestSignal('drill', signal)) return
      set({ drillLoading: false })
    }
  },
}))

export default useSalesStore
