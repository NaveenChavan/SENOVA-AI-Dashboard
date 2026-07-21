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

  uploadFile: async (file) => {
    set({
      isLoading: true,
      error: null,
      data: null,
      uploadErrors: [],
      validationMessage: 'Uploading to server...',
    })

    try {
      const form = new FormData()
      form.append('file', file)

      const { data: uploadRes } = await api.post('/upload/', form)
      const newFileId = uploadRes.file_id

      if (uploadRes.valid_count === 0) {
        const msg =
          'No valid rows found. Check your file format and column headers.'
        set({
          error: msg,
          fileId: newFileId,
          filename: uploadRes.filename,
          uploadErrors: uploadRes.errors || [],
          validationMessage: '',
        })
        throw new Error(msg)
      }

      set({
        fileId: newFileId,
        filename: uploadRes.filename,
        uploadErrors: uploadRes.errors || [],
        validationMessage: '',
      })

      return { ...uploadRes, file_id: newFileId }
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

  fetchAnalytics: async (fileId, timeFilter = 'all') => {
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
      const msg =
        err?.response?.data?.detail || 'Failed to load dashboard. Please retry.'
      set({ error: msg, isLoading: false, validationMessage: '' })
    }
  },

  clearData: () => set({
    data: null, error: null, fileId: null, filename: '',
    validationMessage: '', uploadErrors: [],
  }),

  clearUploadErrors: () => set({ uploadErrors: [] }),
}))

export default useSalesStore
