import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API calls to the FastAPI backend during development.
    proxy: {
      '/upload': 'http://127.0.0.1:8000',
      '/process': 'http://127.0.0.1:8000',
      '/analytics': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
