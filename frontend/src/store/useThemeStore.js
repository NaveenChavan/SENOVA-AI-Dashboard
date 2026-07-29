import { create } from 'zustand'

const STORAGE_KEY = 'senova-theme'

function getInitialTheme() {
  if (typeof window === 'undefined') return 'light'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'dark') return 'dark'
  } catch {
    // localStorage unavailable (private browsing, etc.) — fall through to light.
  }
  // Light is the product default on a fresh visit, regardless of the OS/
  // browser's dark-mode preference — must match the inline script in
  // index.html exactly, or React's initial state would disagree with the
  // data-theme attribute that script already applied before mount.
  return 'light'
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
