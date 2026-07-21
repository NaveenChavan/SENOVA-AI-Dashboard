import { create } from 'zustand'
import axios from 'axios'
import api from '../services/api'

let _abortController = null

const useSalesStore = create((set) => ({
  data: null,
  isLoading: false,
  error: null,
  fileId: null,
  filename: '',
  validationMessage: '',
  uploadErrors: [],
  refreshKey: 0,

  // Column-mapping confirmation state — populated right after upload,
  // cleared once the user confirms their mapping. Every shop's export
  // format is different, so we always show this screen before analysing.
  mappingPreview: null,

  // Actual date span of the uploaded data (set once mapping is confirmed).
  // Drives which date-filter buttons make sense to show as active on the
  // dashboard — a filter wider than the data itself can't show a
  // different result, which looks like a bug if left unexplained.
  dateRange: null,

  /**
   * Step 1 of the upload flow: save the file on the server and get back
   * our best-guess column mapping. Does NOT run analysis yet — the user
   * must confirm (or correct) the mapping via confirmMapping() first.
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
      const msg =
        err?.response?.data?.detail ||
        err.message ||
        'Upload failed. Please try again.'
      set({ error: msg, validationMessage: '' })
      throw err
    } finally {
      set({ isLoading: false })
    }
  },

  /**
   * Step 2: send the user-confirmed (or corrected) column mapping. Runs
   * full row-level validation on the server and persists the mapping so
   * every later read of this file (date filters, PDF, ledger) reuses it.
   *
   * `mapping` is a plain object: { rawColumnName: canonicalFieldName }.
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
      })

      return uploadRes
    } catch (err) {
      const msg =
        err?.response?.data?.detail || err.message || 'Could not validate your data. Please try again.'
      set({ error: msg, validationMessage: '' })
      throw err
    } finally {
      set({ isLoading: false })
    }
  },

  cancelMapping: () => set({ mappingPreview: null, fileId: null, filename: '' }),

  fetchAnalytics: async (fileId, timeFilter = '30days') => {
    if (_abortController) {
      _abortController.abort()
    }
    _abortController = new AbortController()
    const signal = _abortController.signal

    set({ isLoading: true, error: null, data: null, validationMessage: 'Loading analytics...' })

    try {
      // Use the shared `api` instance so requests get the correct baseURL
      // (VITE_API_URL in production) AND the Firebase auth interceptor.
      const response = await api.get(`/analytics/${fileId}`, {
        params: { time_filter: timeFilter, _: Date.now() },
        signal,
        headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' },
      })
      if (signal.aborted) return
      // Spread + freeze guarantees a brand-new object reference every time
      const fresh = {
        ...response.data,
        summary: response.data.summary
          ? {
              ...response.data.summary,
              revenue: { ...response.data.summary.revenue },
              profit: { ...response.data.summary.profit },
              cost: { ...response.data.summary.cost },
              units_sold: { ...response.data.summary.units_sold },
              unique_items_sold: { ...response.data.summary.unique_items_sold },
            }
          : response.data.summary,
      }
      set((state) => ({
        data: fresh,
        isLoading: false,
        refreshKey: state.refreshKey + 1,
        validationMessage: '',
      }))
    } catch (err) {
      if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return
      // 409 = mapping was never confirmed for this file_id (e.g. stale link).
      const msg =
        err?.response?.status === 409
          ? 'Please re-upload this file and confirm your column mapping.'
          : err?.response?.data?.detail || 'Failed to load dashboard. Please retry.'
      set({ error: msg, isLoading: false, validationMessage: '' })
    }
  },

  clearData: () => set({
    data: null, error: null, fileId: null, filename: '',
    validationMessage: '', uploadErrors: [], mappingPreview: null,
    caReport: null, ledgerPage: null, dateRange: null,
  }),

  clearUploadErrors: () => set({ uploadErrors: [] }),

  // ── CA-style financial report (P&L + category ledger) ──────────────────
  caReport: null,
  caReportLoading: false,
  caReportError: null,

  fetchCAReport: async (fileId, timeFilter = '30days') => {
    set({ caReportLoading: true, caReportError: null })
    try {
      const { data } = await api.get(`/analytics/${fileId}/report`, {
        params: { time_filter: timeFilter },
      })
      set({ caReport: data, caReportLoading: false })
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to load the financial report.'
      set({ caReportError: msg, caReportLoading: false })
    }
  },

  // ── Detailed transaction ledger (paginated) ─────────────────────────────
  ledgerPage: null,
  ledgerLoading: false,
  ledgerError: null,

  fetchLedgerPage: async (fileId, { timeFilter = 'all', page = 1, pageSize = 50 } = {}) => {
    set({ ledgerLoading: true, ledgerError: null })
    try {
      const { data } = await api.get(`/analytics/${fileId}/ledger`, {
        params: { time_filter: timeFilter, page, page_size: pageSize },
      })
      set({ ledgerPage: data, ledgerLoading: false })
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to load the transaction ledger.'
      set({ ledgerError: msg, ledgerLoading: false })
    }
  },
}))

export default useSalesStore
