import { useState, useEffect } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import { signInWithGoogle, signInWithEmail } from '../services/firebase'
import { isValidEmail } from '../utils/authValidation'
import { friendlyAuthError } from '../utils/friendlyAuthError'
import Icon from '../components/common/Icon'
import PasswordField from '../components/common/PasswordField'
import Spinner from '../components/common/Spinner'
import GoogleGlyph from '../components/common/GoogleGlyph'
import ThemeToggle from '../components/common/ThemeToggle'
import AuthDisclaimer from '../components/common/AuthDisclaimer'

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

const LOGIN_TABS = [
  { id: 'google', label: 'Google' },
  { id: 'email', label: 'Email' },
]

// How long the submit button stays disabled after auth/too-many-requests,
// so the user can't immediately retry into the same throttle.
const TOO_MANY_REQUESTS_COOLDOWN_SECONDS = 60

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTab, setActiveTab] = useState('email')
  // error is either null or { code, message } from friendlyAuthError,
  // so the UI below can branch behavior (inline CTA, disable submit, etc.)
  // off the stable Firebase code rather than string-matching the message.
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [fieldError, setFieldError] = useState('')
  const [cooldown, setCooldown] = useState(0)
  // One-time success message passed via navigation state, e.g. from
  // /reset-password-confirm after a successful password change. Cleared
  // from history state on mount so a page refresh doesn't re-show it.
  const [infoMessage, setInfoMessage] = useState(location.state?.message || '')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (location.state?.message) {
      navigate(location.pathname, { replace: true, state: {} })
    }
    // Only run once on mount — intentionally not reacting to further
    // location changes, which would immediately clear the message we just
    // set from state above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Countdown for the too-many-requests submit-disable window.
  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [cooldown])

  const startCooldown = (seconds) => {
    setCooldown(seconds)
  }

  const focusTab = (index) => {
    const el = document.getElementById(`login-tab-${LOGIN_TABS[index].id}`)
    el?.focus()
  }

  const handleTabKeyDown = (event, index) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      const next = (index + 1) % LOGIN_TABS.length
      setActiveTab(LOGIN_TABS[next].id)
      setError(null)
      focusTab(next)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      const prev = (index - 1 + LOGIN_TABS.length) % LOGIN_TABS.length
      setActiveTab(LOGIN_TABS[prev].id)
      setError(null)
      focusTab(prev)
    }
  }

  const switchToEmailTabWithPrefill = (prefillEmail) => {
    setActiveTab('email')
    if (prefillEmail) setEmail(prefillEmail)
    setError(null)
  }

  const handleGoogleSignIn = async () => {
    setError(null)
    setLoading(true)
    try {
      await signInWithGoogle()
      navigate('/upload')
    } catch (err) {
      const info = friendlyAuthError(err)
      if (!info) {
        // auth/popup-closed-by-user, auth/cancelled-popup-request — the user
        // closed the popup themselves; not an error, stay silent.
      } else if (info.code === 'auth/account-exists-with-different-credential') {
        // This email already has a password account — send the user to the
        // Email tab instead of showing a dead-end error here. Firebase does
        // not reliably expose the attempted email on this error, so prefill
        // is best-effort only.
        switchToEmailTabWithPrefill(err?.customData?.email)
        setError({
          code: info.code,
          message: 'This email is linked to a password account. Sign in with email and password instead.',
        })
      } else {
        setError(info)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleEmailSignIn = async (event) => {
    event.preventDefault()
    setError(null)

    if (!email.trim() || !password) {
      setFieldError('Email and password are required.')
      return
    }
    setFieldError('')

    if (!isValidEmail(email)) {
      setError({ code: 'auth/invalid-email', message: "That doesn't look like a valid email address." })
      return
    }

    setLoading(true)
    try {
      await signInWithEmail(email, password)
      navigate('/upload')
    } catch (err) {
      const info = friendlyAuthError(err)
      if (info) {
        setError(info)
        if (info.code === 'auth/too-many-requests') {
          startCooldown(TOO_MANY_REQUESTS_COOLDOWN_SECONDS)
        }
      }
      // Keep the email filled in on failure — only the password is cleared,
      // so the user isn't forced to retype an address they got right.
      setPassword('')
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

            {infoMessage && (
              <p role="status" className="note mb-4" data-tone="info">
                <Icon name="check" className="w-4 h-4 shrink-0 mt-px" />
                <span>{infoMessage}</span>
              </p>
            )}

            <div
              role="tablist"
              aria-label="Sign-in method"
              className="grid grid-cols-2 gap-1.5 p-1 rounded-xl mb-5"
              style={{ background: 'var(--bg-card-hover)' }}
            >
              {LOGIN_TABS.map((tab, index) => (
                <button
                  key={tab.id}
                  id={`login-tab-${tab.id}`}
                  role="tab"
                  type="button"
                  aria-selected={activeTab === tab.id}
                  aria-controls={`login-panel-${tab.id}`}
                  tabIndex={activeTab === tab.id ? 0 : -1}
                  onClick={() => {
                    setActiveTab(tab.id)
                    setError(null)
                  }}
                  onKeyDown={(event) => handleTabKeyDown(event, index)}
                  className="rounded-lg px-2 py-2 text-xs font-semibold transition-colors"
                  style={
                    activeTab === tab.id
                      ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: 'var(--shadow-low)' }
                      : { color: 'var(--text-muted)' }
                  }
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div
              id="login-panel-google"
              role="tabpanel"
              aria-labelledby="login-tab-google"
              hidden={activeTab !== 'google'}
            >
              {activeTab === 'google' && (
                <button
                  onClick={handleGoogleSignIn}
                  disabled={loading}
                  aria-busy={loading}
                  className="btn-gradient w-full"
                  style={{ height: 48, fontSize: '0.9375rem' }}
                >
                  {loading ? (
                    <Spinner label="Signing in…" />
                  ) : (
                    <>
                      <GoogleGlyph />
                      Continue with Google
                    </>
                  )}
                </button>
              )}
            </div>

            <div
              id="login-panel-email"
              role="tabpanel"
              aria-labelledby="login-tab-email"
              hidden={activeTab !== 'email'}
            >
              {activeTab === 'email' && (
                <form onSubmit={handleEmailSignIn} className="space-y-4" noValidate>
                  <div>
                    <label htmlFor="login-email" className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                      Email address
                    </label>
                    <input
                      id="login-email"
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value)
                        if (fieldError) setFieldError('')
                      }}
                      autoComplete="email"
                      placeholder="you@example.com"
                      className="field-input"
                      aria-invalid={Boolean(fieldError)}
                    />
                  </div>
                  <PasswordField
                    id="login-password"
                    label="Password"
                    value={password}
                    onChange={(value) => {
                      setPassword(value)
                      if (fieldError) setFieldError('')
                    }}
                    autoComplete="current-password"
                  />
                  <div className="flex justify-end -mt-1">
                    <Link to="/forgot-password" className="text-xs font-semibold underline underline-offset-2" style={{ color: 'var(--accent-blue)' }}>
                      Forgot password?
                    </Link>
                  </div>
                  {fieldError && (
                    <p role="alert" className="note" data-tone="danger">
                      <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
                      <span>{fieldError}</span>
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={loading || cooldown > 0}
                    aria-busy={loading}
                    className="btn-gradient w-full"
                    style={{ height: 48, fontSize: '0.9375rem' }}
                  >
                    {loading ? (
                      <Spinner label="Signing in…" />
                    ) : cooldown > 0 ? (
                      `Try again in ${cooldown}s`
                    ) : (
                      'Sign in'
                    )}
                  </button>
                </form>
              )}
            </div>

            {error && (
              <div role="alert" className="note mt-3" data-tone="danger">
                <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
                <div>
                  <span>{error.message}</span>

                  {/* auth/account-exists-with-different-credential, Google-side:
                      the inline "Continue with Google" CTA the email tab needs. */}
                  {error.code === 'auth/account-exists-with-different-credential' && activeTab === 'email' && (
                    <button
                      type="button"
                      onClick={handleGoogleSignIn}
                      className="btn w-full mt-2.5"
                      style={{ height: 40 }}
                    >
                      <GoogleGlyph />
                      Continue with Google
                    </button>
                  )}

                  {error.code === 'auth/user-disabled' && (
                    <a href="mailto:support@senova.app" className="block mt-1.5 text-xs font-semibold underline underline-offset-2">
                      Contact support
                    </a>
                  )}

                  {error.code === 'auth/too-many-requests' && (
                    <Link to="/forgot-password" className="block mt-1.5 text-xs font-semibold underline underline-offset-2">
                      Reset your password instead
                    </Link>
                  )}

                  {(error.code === 'auth/user-not-found' || error.code === 'auth/wrong-password' || error.code === 'auth/invalid-credential') && (
                    <Link to="/signup" className="block mt-1.5 text-xs font-semibold underline underline-offset-2">
                      Sign up instead
                    </Link>
                  )}
                </div>
              </div>
            )}

            <p className="mt-6 pt-4 text-center text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              New to SENOVA?{' '}
              <Link to="/signup" className="font-semibold underline underline-offset-2" style={{ color: 'var(--accent-blue)' }}>
                Create an account
              </Link>
            </p>
          </div>

          <AuthDisclaimer />
        </motion.div>
      </div>
    </div>
  )
}
