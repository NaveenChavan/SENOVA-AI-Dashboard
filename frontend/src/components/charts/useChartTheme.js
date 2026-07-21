import { useEffect, useState } from 'react'
import useThemeStore from '../../store/useThemeStore'

/**
 * Recharts renders SVG with colours passed as literal JS strings (stroke,
 * fill, tick.fill, etc.) — it can't read our CSS custom properties
 * directly the way Tailwind classes can. This hook re-reads the resolved
 * CSS variable values from the document whenever the theme changes, so
 * every chart repaints with the correct palette instead of being stuck
 * with whatever hex codes were hardcoded at author time.
 */
export default function useChartTheme() {
  const theme = useThemeStore((s) => s.theme)
  const [palette, setPalette] = useState(() => readPalette())

  useEffect(() => {
    setPalette(readPalette())
  }, [theme])

  return palette
}

function readPalette() {
  if (typeof window === 'undefined') return FALLBACK
  const styles = getComputedStyle(document.documentElement)
  const get = (name, fallback) => styles.getPropertyValue(name).trim() || fallback

  return {
    accentBlue: get('--accent-blue', FALLBACK.accentBlue),
    accentGreen: get('--accent-green', FALLBACK.accentGreen),
    accentPurple: get('--accent-purple', FALLBACK.accentPurple),
    accentAmber: get('--accent-amber', FALLBACK.accentAmber),
    textSecondary: get('--text-secondary', FALLBACK.textSecondary),
    textMuted: get('--text-muted', FALLBACK.textMuted),
    borderSubtle: get('--border-subtle', FALLBACK.borderSubtle),
    borderStrong: get('--border-strong', FALLBACK.borderStrong),
    bgPrimary: get('--bg-primary', FALLBACK.bgPrimary),
    // A 4-colour categorical palette for pie/donut charts — kept visually
    // distinct in both themes rather than reusing the 2 brand accents.
    categorical: [
      get('--accent-green', FALLBACK.accentGreen),
      get('--accent-blue', FALLBACK.accentBlue),
      get('--accent-purple', FALLBACK.accentPurple),
      get('--accent-amber', FALLBACK.accentAmber),
    ],
  }
}

const FALLBACK = {
  accentBlue: '#38bdf8',
  accentGreen: '#10b981',
  accentPurple: '#a78bfa',
  accentAmber: '#f59e0b',
  textSecondary: '#7a9cc4',
  textMuted: '#3d5875',
  borderSubtle: 'rgba(56,189,248,0.12)',
  borderStrong: 'rgba(148,163,184,0.25)',
  bgPrimary: '#050d1a',
}
