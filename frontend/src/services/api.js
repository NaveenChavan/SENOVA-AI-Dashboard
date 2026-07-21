import axios from 'axios'
import { getIdToken } from './firebase'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 30_000,
})

// Attach the current Firebase ID token to every outgoing request.
// getIdToken() refreshes the token automatically if it's within 5 minutes
// of expiry, so callers never have to think about refresh logic.
api.interceptors.request.use(async (config) => {
  const token = await getIdToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// If a request still comes back 401 (e.g. token was revoked server-side),
// retry it exactly once with a force-refreshed token before giving up.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    if (response?.status === 401 && !config._retried) {
      config._retried = true
      const freshToken = await getIdToken(true)
      if (freshToken) {
        config.headers.Authorization = `Bearer ${freshToken}`
        return api.request(config)
      }
    }
    return Promise.reject(error)
  },
)

export default api
