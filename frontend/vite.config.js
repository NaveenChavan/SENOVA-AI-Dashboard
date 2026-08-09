import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Single proxy prefix, deliberately. Proxying the real API paths
    // (`/upload`, `/analytics`, …) directly would collide with the SPA's own
    // client-side routes of the same name: a reload at
    // http://localhost:5173/upload got proxied to the backend instead of
    // serving index.html, and FastAPI's redirect to `/upload/` came back as
    // an absolute cross-origin URL that the browser then blocked
    // ("Unsafe attempt to load URL … Domains, protocols and ports must
    // match"). Routing every call under `/api` keeps API traffic and page
    // routes in separate namespaces, and automatically covers new backend
    // route groups without another proxy rule per group.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          recharts: ['recharts'],
        },
      },
    },
  },
  // Component smoke tests (`npm test`). jsdom is required because the chart
  // components measure and paint DOM nodes; ``globals`` lets the test files use
  // describe/it/expect without importing them everywhere.
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{js,jsx}'],
  },
})
