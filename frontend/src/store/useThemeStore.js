import { create } from 'zustand'

const STORAGE_KEY = 'senova-theme'

function getInitialTheme() {
  if (typeof window === 'undefined') return 'dark'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // localStorage unavailable (private browsing, etc.) — fall through to OS preference.
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function applyTheme(theme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', theme)
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Ignore write failures (e.g. storage quota, private browsing) — the
    // theme still applies for this session via the DOM attribute.
  }
}

/**
 * Theme store — dark/light mode with persistence. The initial theme is
 * already applied synchronously by a tiny inline script in index.html
 * (before React mounts, to avoid a flash of the wrong theme); this store
 * just keeps React's view of the current theme in sync with that DOM
 * attribute so components can react to it (e.g. the toggle's icon state).
 */
const useThemeStore = create((set, get) => ({
  theme: getInitialTheme(),

  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    set({ theme: next })
  },
}))

export default useThemeStore
