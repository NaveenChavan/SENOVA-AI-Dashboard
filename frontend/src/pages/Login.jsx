import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { signInWithGoogle } from '../services/firebase'

const FEATURES = [
  {
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 17V7m3 10v-4m3 4v-7m3-4v11M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z" />
    ),
    title: 'Instant analytics',
    desc: 'Revenue, profit & margin the moment you upload a file.',
  },
  {
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    ),
    title: 'Row-level validation',
    desc: 'Every row checked — bad data flagged, never silently dropped.',
  },
  {
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M13 10V3L4 14h7v7l9-11h-7z" />
    ),
    title: 'Dead stock detection',
    desc: 'Spot slow-moving inventory before it ties up your capital.',
  },
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
      const friendly =
        err?.code === 'auth/network-request-failed'
          ? 'Network error. Check your connection and try again.'
          : err?.code === 'auth/popup-blocked'
            ? 'Popup was blocked by your browser. Allow popups for this site and retry.'
            : 'Sign-in failed. Please try again.'
      setError(friendly)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen w-full flex" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Sign in — SENOVA Digital Lab</title>
        <meta name="description" content="Sign in to SENOVA to access AI-powered retail sales analytics." />
      </Helmet>

      {/* Left panel — brand story, hidden on small screens */}
      <div
        className="hidden lg:flex lg:w-1/2 relative flex-col justify-between p-12 overflow-hidden"
        style={{
          background: 'linear-gradient(160deg, #071427 0%, #050d1a 60%, #030712 100%)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        <div
          aria-hidden="true"
          className="absolute -top-32 -left-32 w-96 h-96 rounded-full blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(56,189,248,0.15), transparent 70%)' }}
        />
        <div
          aria-hidden="true"
          className="absolute bottom-0 right-0 w-80 h-80 rounded-full blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.12), transparent 70%)' }}
        />

        <div className="relative z-10 flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
              boxShadow: '0 0 20px rgba(56,189,248,0.35)',
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-xl font-bold" style={{ color: 'var(--accent-blue)' }}>
            SENOVA <span className="font-light" style={{ color: 'var(--text-primary)' }}>Digital Lab</span>
          </span>
        </div>

        <div className="relative z-10 max-w-md">
          <h1 className="text-4xl font-bold leading-tight mb-4" style={{ color: 'var(--text-primary)' }}>
            Retail intelligence,
            <br />
            <span className="glow-blue-text" style={{ color: 'var(--accent-blue)' }}>zero spreadsheets.</span>
          </h1>
          <p className="text-base mb-10" style={{ color: 'var(--text-secondary)' }}>
            Upload your daily sales file and get an AI-generated dashboard —
            revenue, margins, top movers, and dead stock — in seconds.
          </p>

          <ul className="space-y-5">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex items-start gap-4">
                <div
                  className="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                  style={{ background: 'rgba(56,189,248,0.08)', border: '1px solid var(--border-subtle)' }}
                >
                  <svg className="w-5 h-5" style={{ color: 'var(--accent-blue)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    {f.icon}
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{f.title}</p>
                  <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>{f.desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs" style={{ color: 'var(--text-muted)' }}>
          &copy; {new Date().getFullYear()} SENOVA Digital Lab. All rights reserved.
        </p>
      </div>

      {/* Right panel — sign-in card */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-8 py-12 relative">
        <div
          aria-hidden="true"
          className="lg:hidden absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at 50% 0%, rgba(56,189,248,0.08) 0%, transparent 55%)',
          }}
        />

        <div className="relative z-10 w-full max-w-sm">
          {/* Mobile-only brand mark */}
          <div className="lg:hidden flex items-center justify-center gap-3 mb-10">
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
                boxShadow: '0 0 20px rgba(56,189,248,0.35)',
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-xl font-bold" style={{ color: 'var(--accent-blue)' }}>
              SENOVA <span className="font-light" style={{ color: 'var(--text-primary)' }}>Digital Lab</span>
            </span>
          </div>

          <div
            className="rounded-2xl p-8 sm:p-10"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', backdropFilter: 'blur(12px)' }}
          >
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                Welcome back
              </h2>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Sign in to access your sales dashboard
              </p>
            </div>

            <button
              onClick={handleGoogleSignIn}
              disabled={loading}
              aria-busy={loading}
              className="w-full flex items-center justify-center gap-3 px-4 py-3.5 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-400/50"
              style={{
                background: 'rgba(15, 28, 52, 0.9)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.borderColor = 'var(--border-active)' }}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </>
              ) : (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24">
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
              <div
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5' }}
              >
                <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            <div className="mt-8 pt-6 flex items-center justify-center gap-2 text-xs" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 10-8 0v4h8z" />
              </svg>
              Secured by Firebase Authentication
            </div>
          </div>

          <p className="text-center text-xs mt-6" style={{ color: 'var(--text-muted)' }}>
            By continuing, you agree to SENOVA's Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  )
}
