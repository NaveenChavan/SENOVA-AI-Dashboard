import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

import { signInWithGoogle } from '../services/firebase'
import Icon from '../components/common/Icon'

/**
 * Sign-in page — a two-column split on desktop, a single centred card on mobile.
 *
 * Both halves are sized so the whole page fits in one viewport at 768px height
 * upward: the brand column carries three short benefit lines (no scrolling
 * story), and the card is a fixed 320px column. Colours come from the theme
 * tokens, so the page follows the same white-first look as the dashboard.
 */

const FEATURES = [
  { icon: 'spark', title: 'Automated findings', desc: 'Anomalies, movers and margin leaks, written in plain language.' },
  { icon: 'chart', title: 'Forecast & reorder', desc: 'Revenue projection with accuracy, plus what to buy first.' },
  { icon: 'check', title: 'Row-level validation', desc: 'Every row checked — bad data flagged, never silently dropped.' },
]

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
    <div className="min-h-dvh w-full flex" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Sign in — SENOVA Digital Lab</title>
        <meta name="description" content="Sign in to SENOVA to access AI-powered retail sales analytics." />
      </Helmet>

      {/* ── Brand column (desktop only) ─────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-1/2 flex-col justify-between p-10"
        style={{ background: 'var(--bg-card)', borderRight: '1px solid var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <img src="/assets/logo.jpeg" alt="SENOVA" width={30} height={30} className="w-[30px] h-[30px] rounded-lg object-cover" />
          <span className="text-sm font-bold" style={{ color: 'var(--accent-blue)' }}>
            SENOVA <span className="font-light" style={{ color: 'var(--text-primary)' }}>Digital Lab</span>
          </span>
        </div>

        <div className="max-w-md">
          <h1 className="text-3xl leading-tight mb-3">
            Retail intelligence,
            <br />
            <span style={{ color: 'var(--accent-blue)' }}>zero spreadsheets.</span>
          </h1>
          <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>
            Upload your daily sales file and get a computed dashboard — findings, forecast, reorder priorities and a
            CA-style report — in seconds.
          </p>

          <ul className="space-y-3.5">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="flex items-start gap-2.5">
                <span
                  className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{ background: 'var(--accent-blue-glow)' }}
                >
                  <Icon name={feature.icon} className="w-3.5 h-3.5" style={{ color: 'var(--accent-blue)' }} />
                </span>
                <span>
                  <span className="block text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {feature.title}
                  </span>
                  <span className="block text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {feature.desc}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
          &copy; {new Date().getFullYear()} SENOVA Digital Lab. All rights reserved.
        </p>
      </div>

      {/* ── Sign-in column ──────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full" style={{ maxWidth: 320 }}>
          {/* Mobile-only brand mark */}
          <div className="lg:hidden flex items-center justify-center gap-2 mb-6">
            <img src="/assets/logo.jpeg" alt="SENOVA" width={32} height={32} className="w-8 h-8 rounded-lg object-cover" />
            <span className="text-sm font-bold" style={{ color: 'var(--accent-blue)' }}>
              SENOVA <span className="font-light" style={{ color: 'var(--text-primary)' }}>Digital Lab</span>
            </span>
          </div>

          <div className="card" style={{ padding: 24 }}>
            <div className="text-center mb-5">
              <h2 className="mb-1">Welcome back</h2>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Sign in to access your sales dashboard
              </p>
            </div>

            <button
              onClick={handleGoogleSignIn}
              disabled={loading}
              aria-busy={loading}
              className="btn w-full"
              style={{ height: 40 }}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
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
              className="mt-5 pt-3.5 flex items-center justify-center gap-1.5 text-[12px]"
              style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
            >
              <Icon name="check" className="w-3 h-3" />
              Secured by Firebase Authentication
            </p>
          </div>

          <p className="text-center text-[12px] mt-3" style={{ color: 'var(--text-muted)' }}>
            By continuing, you agree to SENOVA's Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  )
}
