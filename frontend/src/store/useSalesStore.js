import { create } from 'zustand'
import api from '../services/api'

const useSalesStore = create((set) => ({
  data: null,
  isLoading: false,
  error: null,
  fileId: null,
  filename: '',
  validationMessage: '',
  uploadErrors: [],

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
    set({
      isLoading: true,
      error: null,
      validationMessage: 'Loading analytics...',
    })

    try {
      const { data } = await api.get(`/analytics/${fileId}`, {
        params: { time_filter: timeFilter },
      })
      set({ data, validationMessage: '' })
    } catch (err) {
      const msg =
        err?.response?.data?.detail || 'Failed to load dashboard. Please retry.'
      set({ error: msg, validationMessage: '' })
    } finally {
      set({ isLoading: false })
    }
  },

  clearData: () => set({
    data: null, error: null, fileId: null, filename: '',
    validationMessage: '', uploadErrors: [],
  }),

  clearUploadErrors: () => set({ uploadErrors: [] }),
}))

export default useSalesStore
