import { create } from 'zustand'

const STORAGE_KEY = 'senova-density'

/**
 * Display density — "compact" (the data-dense default) or "comfortable".
 *
 * Both modes are the same layout; only the spacing/height tokens change, driven
 * by a `data-density` attribute on `<html>` (see index.css). Doing it in CSS
 * rather than in React means switching costs no re-render and every component —
 * including the charts, which read `--chart-h` — follows automatically.
 */

function readInitial() {
  if (typeof window === 'undefined') return 'compact'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'compact' || stored === 'comfortable') return stored
  } catch {
    // Private browsing — fall through to the default.
  }
  return 'compact'
}

function apply(density) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-density', density)
  try {
    window.localStorage.setItem(STORAGE_KEY, density)
  } catch {
    // Persisting is best-effort; the attribute still applies this session.
  }
}

const useDensityStore = create((set, get) => ({
  density: readInitial(),

  setDensity: (density) => {
    apply(density)
    set({ density })
  },

  toggleDensity: () => {
    const next = get().density === 'compact' ? 'comfortable' : 'compact'
    apply(next)
    set({ density: next })
  },
}))

export default useDensityStore
