import axios from 'axios'

/**
 * Pre-configured Axios instance.
 * Requests to /upload and /process are proxied through Vite in dev mode.
 * Update `baseURL` when moving to production.
 */
const api = axios.create({
  baseURL: '', // Uses Vite proxy in dev; set to backend URL in production.
  timeout: 30_000,
})

export default api
