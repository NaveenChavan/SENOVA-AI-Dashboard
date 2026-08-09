import axios from 'axios'
import { getIdToken } from './firebase'

const api = axios.create({
  // In production `VITE_API_URL` points straight at the deployed backend
  // origin. Left empty (local dev) we fall back to the `/api` prefix that
  // `vite.config.js` proxies to 127.0.0.1:8000 — not to `''`, because bare
  // relative paths like `/upload/` would collide with the SPA's own
  // client-side route of the same name.
  baseURL: import.meta.env.VITE_API_URL || '/api',
  // Generous on purpose. A first request against a freshly uploaded 30–50k
  // row Excel file has to parse and validate the whole sheet before it can
  // answer, which is measured in seconds, not milliseconds — and the
  // dashboard's cold load fires several such requests at once. 30s was tight
  // enough that a 30k-row file could trip it and surface as a bare
  // "timeout of 30000ms exceeded" on the dashboard.
  timeout: 60_000,
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
