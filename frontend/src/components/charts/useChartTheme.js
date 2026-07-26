import { useEffect, useState } from 'react'
import useThemeStore from '../../store/useThemeStore'

/**
 * Recharts renders SVG with colours passed as literal JS strings (stroke,
 * fill, tick.fill, etc.) — it can't read our CSS custom properties the way
 * Tailwind classes can. This hook re-reads the resolved CSS variable values
 * from the document whenever the theme changes, so every chart repaints with
 * the correct palette instead of being stuck with hex codes fixed at author
 * time.
 *
 * It also exposes the semantic roles the Pro charts need — actual vs forecast,
 * anomaly, and an 8-colour categorical ramp — so no component has to invent
 * its own colours and drift from the design system.
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

  const blue = get('--accent-blue', FALLBACK.accentBlue)
  const green = get('--accent-green', FALLBACK.accentGreen)
  const purple = get('--accent-purple', FALLBACK.accentPurple)
  const amber = get('--accent-amber', FALLBACK.accentAmber)
  const red = get('--accent-red', FALLBACK.accentRed)
  const blueStrong = get('--accent-blue-strong', FALLBACK.accentBlueStrong)

  return {
    accentBlue: blue,
    accentBlueStrong: blueStrong,
    accentGreen: green,
    accentPurple: purple,
    accentAmber: amber,
    accentRed: red,
    textSecondary: get('--text-secondary', FALLBACK.textSecondary),
    textMuted: get('--text-muted', FALLBACK.textMuted),
    borderSubtle: get('--border-subtle', FALLBACK.borderSubtle),
    borderStrong: get('--border-strong', FALLBACK.borderStrong),
    bgPrimary: get('--bg-primary', FALLBACK.bgPrimary),
    bgCard: get('--bg-card-solid', FALLBACK.bgPrimary),

    // Semantic roles for the forecast chart. The design guidance asks for a
    // solid "actual" line, a dashed "forecast" line in a clearly different
    // hue, and a shaded band — expressed here with brand accents so the chart
    // still looks like the rest of the product.
    actual: blue,
    forecast: amber,
    anomaly: red,

    // 8-colour categorical ramp for donut / treemap / grouped series. Ordered
    // so neighbouring slices never share a hue, which keeps a 6-slice donut
    // readable without relying on the legend alone.
    categorical: [blue, green, amber, purple, blueStrong, red, mix(green, blue), mix(purple, amber)],
  }
}

/**
 * Blend two hex colours 50/50 — used to extend the categorical ramp without
 * introducing off-brand hues. Falls back to the first colour if either value
 * isn't a plain 6-digit hex (e.g. a theme override using rgb()).
 */
function mix(a, b) {
  const parse = (hex) => {
    const match = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim())
    return match ? parseInt(match[1], 16) : null
  }
  const left = parse(a)
  const right = parse(b)
  if (left === null || right === null) return a

  const channel = (shift) =>
    Math.round((((left >> shift) & 0xff) + ((right >> shift) & 0xff)) / 2)
      .toString(16)
      .padStart(2, '0')

  return `#${channel(16)}${channel(8)}${channel(0)}`
}

const FALLBACK = {
  accentBlue: '#38bdf8',
  accentBlueStrong: '#0ea5e9',
  accentGreen: '#10b981',
  accentPurple: '#a78bfa',
  accentAmber: '#f59e0b',
  accentRed: '#f87171',
  textSecondary: '#7a9cc4',
  textMuted: '#3d5875',
  borderSubtle: 'rgba(56,189,248,0.12)',
  borderStrong: 'rgba(148,163,184,0.25)',
  bgPrimary: '#050d1a',
}
