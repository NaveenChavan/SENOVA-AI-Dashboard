import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import api from '../services/api'
import { sendEmailPasswordReset } from '../services/firebase'
import { isValidEmail } from '../utils/authValidation'
import Icon from '../components/common/Icon'
import Spinner from '../components/common/Spinner'
import ThemeToggle from '../components/common/ThemeToggle'
import AuthDisclaimer from '../components/common/AuthDisclaimer'

const EASE = [0.16, 1, 0.3, 1]

/**
 * Password reset — email accounts only. Google accounts have no password
 * to reset (they sign in via Google's own account picker instead).
 *
 * Prefers the backend's POST /auth/forgot-password, which sends a branded
 * email over SendGrid from an authenticated domain — see
 * `backend/app/services/email_service.py`. If that backend reports it isn't
 * configured to send yet (`email_dispatched: false`, i.e. SendGrid domain
 * authentication still pending), this falls back to Firebase's own built-in
 * reset email so the feature keeps working — just with Firebase's weaker
 * inbox placement (frequently Spam), which is the whole reason the SendGrid
 * path exists.
 *
 * Either way the user sees one identical generic message, because the
 * backend never reveals whether the submitted account exists.
 */
export default function ForgotPassword() {
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [email, setEmail] = useState('')
  const [emailSent, setEmailSent] = useState(false)

  const handleEmailReset = async (event) => {
    event.preventDefault()
    setError('')
    if (!isValidEmail(email)) {
      setError('Enter a valid email address.')
      return
    }
    setLoading(true)
    try {
      const { data } = await api.post('/auth/forgot-password', { email })
      if (data?.email_dispatched === false) {
        // Backend can't send yet — fall back to Firebase's own sender so a
        // reset link still reaches the user.
        await sendEmailPasswordReset(email)
      }
    } catch {
      // Last-resort fallback: if the backend itself is unreachable, still
      // try Firebase directly rather than silently doing nothing.
      try {
        await sendEmailPasswordReset(email)
      } catch {
        // Both paths failed. Deliberately still shows the same generic
        // success state — surfacing "we couldn't send it" here would
        // reveal more about backend state than about this account, and
        // the user's next step (check inbox, retry) is unchanged.
      }
    } finally {
      setLoading(false)
      setEmailSent(true)
    }
  }

  return (
    <div className="min-h-dvh w-full flex items-center justify-center relative px-4 py-10" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Reset password — SENOVA Digital Lab</title>
        <meta name="description" content="Reset your SENOVA account password." />
      </Helmet>

      <div className="absolute top-5 right-5 sm:top-6 sm:right-6 z-20">
        <ThemeToggle />
      </div>

      <motion.div
        className="w-full"
        style={{ maxWidth: 440 }}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: EASE }}
      >
        <div className="flex items-center justify-center gap-2.5 mb-6">
          <span className="shrink-0 rounded-lg overflow-hidden" style={{ width: 32, height: 32, border: '1px solid var(--border-subtle)' }}>
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
            <span
              className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-3"
              style={{ background: 'var(--gradient-accent-soft)' }}
            >
              <Icon name="lock" className="w-5 h-5" style={{ color: 'var(--accent-blue)' }} />
            </span>
            <h2 className="text-display text-xl mb-1.5">Reset your password</h2>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Enter the email address on your account
            </p>
          </div>

          {!emailSent ? (
            <form onSubmit={handleEmailReset} className="space-y-4">
              <div>
                <label htmlFor="reset-email" className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Email address
                </label>
                <input
                  id="reset-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="field-input"
                  required
                />
                <p className="mt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                  We'll email you a link to reset your password.
                </p>
              </div>
              <button type="submit" disabled={loading} aria-busy={loading} className="btn-gradient w-full" style={{ height: 48, fontSize: '0.9375rem' }}>
                {loading ? <Spinner label="Sending…" /> : 'Send reset link'}
              </button>
            </form>
          ) : (
            <div className="text-center py-2">
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                If an account exists for <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>, a password
                reset link has been sent. Check your inbox (and spam folder).
              </p>
            </div>
          )}

          {error && (
            <p role="alert" className="note mt-3" data-tone="danger">
              <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
              <span>{error}</span>
            </p>
          )}

          <p className="mt-6 pt-4 text-center text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            Remembered your password?{' '}
            <Link to="/login" className="font-semibold underline underline-offset-2" style={{ color: 'var(--accent-blue)' }}>
              Sign in
            </Link>
          </p>
        </div>

        <AuthDisclaimer />
      </motion.div>
    </div>
  )
}
