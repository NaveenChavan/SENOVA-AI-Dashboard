import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import { signInWithGoogle } from '../services/firebase'
import Icon from '../components/common/Icon'
import ThemeToggle from '../components/common/ThemeToggle'

/**
 * Sign-in page — a two-column split on desktop, a single centred card on mobile.
 *
 * The brand column carries the headline, the animated forecast graphic and the
 * three feature cards; the sign-in card is a fixed 320px column so the page
 * still fits one viewport height on a laptop screen. Colours come from the
 * theme tokens, so the page follows the same design system as the dashboard —
 * this is the same product wearing its best clothes, not a separate skin.
 *
 * Motion is entrance-only (fade/slide-in on mount, once, respecting
 * prefers-reduced-motion via the global CSS rule) plus one slow ambient loop
 * on the hero graphic's forecast line — nothing here blocks interaction or
 * delays the sign-in button being clickable.
 */

const FEATURES = [
  { icon: 'spark', title: 'Automated findings', desc: 'Anomalies, movers and margin leaks, written in plain language.' },
  { icon: 'chart', title: 'Forecast & reorder', desc: 'Revenue projection with accuracy, plus what to buy first.' },
  { icon: 'check', title: 'Row-level validation', desc: 'Every row checked — bad data flagged, never silently dropped.' },
]

const EASE = [0.16, 1, 0.3, 1]

/**
 * Abstract hero graphic: a bar cluster (daily revenue) with an animated
 * trend/forecast line drawn over it, and a dashed forward-projection segment —
 * a compressed visual metaphor for "SENOVA turns your rows into a forecast."
 * Entirely inline SVG, no external assets, themeable via currentColor + tokens.
 */
function ForecastGraphic() {
  const bars = [38, 52, 44, 61, 55, 70, 64, 82]
  const barWidth = 18
  const gap = 10
  const chartWidth = bars.length * (barWidth + gap) - gap
  const chartHeight = 100

  // A smooth trend line through the bar tops, plus a dashed continuation
  // (the "forecast") past the last real bar.
  const points = bars.map((h, i) => [i * (barWidth + gap) + barWidth / 2, chartHeight - h])
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0]} ${p[1]}`).join(' ')
  const lastPoint = points[points.length - 1]
  const forecastEnd = [chartWidth + 34, lastPoint[1] - 14]

  return (
    <div className="relative" aria-hidden="true">
      <svg
        viewBox={`-10 -20 ${chartWidth + 60} ${chartHeight + 40}`}
        width="100%"
        height="auto"
        style={{ maxWidth: 360 }}
      >
        <defs>
          <linearGradient id="senova-bar-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-blue)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="var(--accent-blue)" stopOpacity="0.25" />
          </linearGradient>
          <linearGradient id="senova-line-stroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--accent-blue)" />
            <stop offset="100%" stopColor="var(--accent-purple)" />
          </linearGradient>
        </defs>

        {bars.map((h, i) => (
          <motion.rect
            key={i}
            x={i * (barWidth + gap)}
            y={chartHeight - h}
            width={barWidth}
            height={h}
            rx={4}
            fill="url(#senova-bar-fill)"
            initial={{ scaleY: 0, opacity: 0 }}
            animate={{ scaleY: 1, opacity: 1 }}
            style={{ transformOrigin: `${i * (barWidth + gap) + barWidth / 2}px ${chartHeight}px` }}
            transition={{ duration: 0.5, delay: 0.35 + i * 0.05, ease: EASE }}
          />
        ))}

        {/* Trend line over the real bars */}
        <motion.path
          d={linePath}
          fill="none"
          stroke="url(#senova-line-stroke)"
          strokeWidth={2.5}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1, delay: 0.9, ease: EASE }}
        />

        {/* Dashed forecast continuation past the last real day */}
        <motion.path
          d={`M ${lastPoint[0]} ${lastPoint[1]} Q ${lastPoint[0] + 20} ${lastPoint[1] - 20} ${forecastEnd[0]} ${forecastEnd[1]}`}
          fill="none"
          stroke="var(--accent-purple)"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeDasharray="6 5"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 0.7, delay: 1.7, ease: EASE }}
        />

        {/* Endpoint marker with a slow breathing pulse — the "live compute" cue */}
        <motion.circle
          cx={forecastEnd[0]}
          cy={forecastEnd[1]}
          r={5}
          fill="var(--accent-purple)"
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 2.3, ease: EASE }}
        />
        <motion.circle
          cx={forecastEnd[0]}
          cy={forecastEnd[1]}
          r={5}
          fill="none"
          stroke="var(--accent-purple)"
          strokeWidth={1.5}
          initial={{ opacity: 0.6, scale: 1 }}
          animate={{ opacity: 0, scale: 2.4 }}
          transition={{ duration: 1.8, delay: 2.5, repeat: Infinity, ease: 'easeOut' }}
        />
      </svg>
    </div>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleGoogleSignIn = async () => {
    setError('')
    setLoading(true)
    try {
      await signInWithGoogle()
      navigate('/upload')
    } catch (err) {
      if (err?.code === 'auth/popup-closed-by-user' || err?.code === 'auth/cancelled-popup-request') {
        // User cancelled — not an error worth surfacing.
        return
      }
      console.error('[Login] Google sign-in failed:', err)
      setError(
        err?.code === 'auth/network-request-failed'
          ? 'Network error. Check your connection and try again.'
          : err?.code === 'auth/popup-blocked'
            ? 'Popup was blocked by your browser. Allow popups for this site and retry.'
            : 'Sign-in failed. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-dvh w-full flex relative" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Sign in — SENOVA Digital Lab</title>
        <meta name="description" content="Sign in to SENOVA to access AI-powered retail sales analytics." />
      </Helmet>

      {/* Theme toggle — the login screen has no app shell (it owns its own
          full-bleed layout), so it needs its own light/dark switch rather
          than relying on the header's, which doesn't render on this route. */}
      <div className="absolute top-5 right-5 sm:top-6 sm:right-6 z-20">
        <ThemeToggle />
      </div>

      {/* ── Brand column (desktop only) ─────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-1/2 flex-col justify-between p-10 relative overflow-hidden"
        style={{ background: 'var(--bg-card)', borderRight: '1px solid var(--border-subtle)' }}
      >
        {/* Brand mark — pinned to the page corner, detached from the hero
            content block below it, so it reads as a persistent identity mark
            rather than another line of hero copy. The logo is a detailed
            illustrated mark (navy/blue/green hexagon) on its own white
            backing — it needs to sit on a plain rounded tile, not inside a
            gradient chip or blend mode that would fight its own colours. */}
        <motion.div
          className="absolute top-8 left-10 flex items-center gap-3 z-10"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          <span
            className="shrink-0 rounded-xl overflow-hidden"
            style={{ width: 38, height: 38, boxShadow: 'var(--shadow-medium)', border: '1px solid var(--border-subtle)' }}
          >
            <img src="/assets/logo.jpeg" alt="SENOVA" width={38} height={38} className="w-full h-full object-cover" />
          </span>
          <span className="text-display text-base font-bold leading-none tracking-tight" style={{ color: 'var(--text-primary)' }}>
            SENOVA
            <span className="block font-sans text-[10px] font-semibold tracking-[0.14em] uppercase mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Digital Lab
            </span>
          </span>
        </motion.div>

        {/* Faint gradient mesh in the corner — depth without a hardcoded image */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse 60% 40% at 100% 0%, var(--accent-blue-glow) 0%, transparent 70%), radial-gradient(ellipse 50% 35% at 0% 100%, var(--gradient-accent-soft) 0%, transparent 70%)',
          }}
        />

        <div className="max-w-md relative" style={{ marginTop: 56 }}>
          <motion.h1
            className="text-display text-4xl lg:text-5xl leading-tight mb-4"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1, ease: EASE }}
          >
            Retail intelligence,
            <br />
            <span style={{ background: 'var(--gradient-accent)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
              zero spreadsheets.
            </span>
          </motion.h1>
          <motion.p
            className="text-base mb-8"
            style={{ color: 'var(--text-secondary)' }}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: EASE }}
          >
            Upload your daily sales file and get a computed dashboard — findings, forecast, reorder priorities and a
            CA-style report — in seconds.
          </motion.p>

          <motion.div
            className="mb-7"
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.3, ease: EASE }}
          >
            <ForecastGraphic />
          </motion.div>

          <ul className="space-y-2.5">
            {FEATURES.map((feature, i) => (
              <motion.li
                key={feature.title}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: 0.4 + i * 0.08, ease: EASE }}
                whileHover={{ y: -2 }}
                className="flex items-start gap-3 rounded-xl p-2.5 -mx-2.5 cursor-default"
                style={{ transition: 'background-color 160ms ease, border-color 160ms ease' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-card-hover)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent'
                }}
              >
                <span
                  className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: 'var(--gradient-accent-soft)' }}
                >
                  <Icon name={feature.icon} className="w-4 h-4" style={{ color: 'var(--accent-blue)' }} />
                </span>
                <span>
                  <span className="block text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {feature.title}
                  </span>
                  <span className="block text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {feature.desc}
                  </span>
                </span>
              </motion.li>
            ))}
          </ul>
        </div>

        <p className="text-[12px] relative" style={{ color: 'var(--text-muted)' }}>
          &copy; {new Date().getFullYear()} SENOVA Digital Lab. All rights reserved.
        </p>
      </div>

      {/* ── Sign-in column ──────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-8 lg:px-12 py-10">
        <motion.div
          className="w-full"
          style={{ maxWidth: 420 }}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: EASE }}
        >
          {/* Mobile-only brand mark */}
          <div className="lg:hidden flex items-center justify-center gap-2.5 mb-6">
            <span
              className="shrink-0 rounded-lg overflow-hidden"
              style={{ width: 32, height: 32, border: '1px solid var(--border-subtle)' }}
            >
              <img src="/assets/logo.jpeg" alt="SENOVA" width={32} height={32} className="w-full h-full object-cover" />
            </span>
            <span className="text-display text-sm font-bold leading-none tracking-tight" style={{ color: 'var(--text-primary)' }}>
              SENOVA
              <span className="block font-sans text-[9px] font-semibold tracking-[0.14em] uppercase mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Digital Lab
              </span>
            </span>
          </div>

          <div className="card" style={{ padding: 32 }}>
            <div className="text-center mb-6">
              <h2 className="text-display text-xl mb-1.5">Welcome back</h2>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Sign in to access your sales dashboard
              </p>
            </div>

            <button
              onClick={handleGoogleSignIn}
              disabled={loading}
              aria-busy={loading}
              className="btn-gradient w-full"
              style={{ height: 48, fontSize: '0.9375rem' }}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </>
              ) : (
                <>
                  <span
                    className="inline-flex items-center justify-center rounded-md shrink-0"
                    style={{ width: 24, height: 24, background: '#ffffff' }}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                    </svg>
                  </span>
                  Continue with Google
                </>
              )}
            </button>

            {error && (
              <p role="alert" className="note mt-3" data-tone="danger">
                <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
                <span>{error}</span>
              </p>
            )}

            <p
              className="mt-6 pt-4 flex items-center justify-center gap-1.5 text-xs"
              style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
            >
              <Icon name="check" className="w-3.5 h-3.5" />
              Secured by Firebase Authentication
            </p>
          </div>

          <p className="text-center text-xs mt-4" style={{ color: 'var(--text-muted)' }}>
            By continuing, you agree to SENOVA's Terms of Service and Privacy Policy.
          </p>
        </motion.div>
      </div>
    </div>
  )
}
