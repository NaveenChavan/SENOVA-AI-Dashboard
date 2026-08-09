import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import { verifyResetCode, confirmReset } from '../services/firebase'
import { checkPasswordStrength } from '../utils/authValidation'
import { friendlyAuthError } from '../utils/friendlyAuthError'
import Icon from '../components/common/Icon'
import PasswordField from '../components/common/PasswordField'
import Spinner from '../components/common/Spinner'
import ThemeToggle from '../components/common/ThemeToggle'
import AuthDisclaimer from '../components/common/AuthDisclaimer'

const EASE = [0.16, 1, 0.3, 1]

/**
 * The branded landing page for the link sent by the backend's
 * /auth/forgot-password endpoint (see `email_service.py`). Firebase issues
 * the actual reset code — this page only reads it from the URL, verifies
 * it's still valid, and lets the user set a new password without ever
 * bouncing to Firebase's own hosted action page.
 *
 * Three states: checking (verifying the code), form (code valid, collecting
 * the new password), and done (password changed, redirecting to /login).
 * A fourth, implicit state — invalid/expired code — reuses the same error
 * banner as the form state but never shows the password form at all.
 */
export default function ResetPasswordConfirm() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const oobCode = searchParams.get('oobCode')

  const [checking, setChecking] = useState(true)
  const [codeValid, setCodeValid] = useState(false)
  const [email, setEmail] = useState('')
  const [error, setError] = useState(null)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!oobCode) {
      setError({ message: 'This link is missing its reset code. Request a new one.' })
      setChecking(false)
      return
    }
    verifyResetCode(oobCode)
      .then((verifiedEmail) => {
        setEmail(verifiedEmail)
        setCodeValid(true)
      })
      .catch((err) => {
        setError(friendlyAuthError(err) || { message: 'This link is invalid. Request a new one.' })
      })
      .finally(() => setChecking(false))
  }, [oobCode])

  useEffect(() => {
    if (!done) return undefined
    const timer = window.setTimeout(() => {
      navigate('/login', { state: { message: 'Password updated. Please sign in.' } })
    }, 1800)
    return () => window.clearTimeout(timer)
  }, [done, navigate])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError(null)

    const { valid } = checkPasswordStrength(password)
    if (!valid) {
      setError({ message: 'Password does not meet the requirements below.' })
      return
    }
    if (password !== confirmPassword) {
      setError({ message: "Passwords don't match." })
      return
    }

    setSubmitting(true)
    try {
      await confirmReset(oobCode, password)
      setDone(true)
    } catch (err) {
      const info = friendlyAuthError(err)
      setError(info || { message: 'Could not update your password. Please try again.' })
      // An expired/invalid code caught at submit time (e.g. the link was
      // used in another tab moments ago) should fall back to the same
      // "request a new one" dead-end as the initial verification failure.
      if (err?.code === 'auth/expired-action-code' || err?.code === 'auth/invalid-action-code') {
        setCodeValid(false)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-dvh w-full flex items-center justify-center relative px-4 py-10" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Set a new password — SENOVA Digital Lab</title>
        <meta name="description" content="Choose a new password for your SENOVA account." />
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
          {checking && (
            <div className="text-center py-6">
              <Spinner label="Checking your reset link…" />
            </div>
          )}

          {!checking && codeValid && !done && (
            <>
              <div className="text-center mb-6">
                <span
                  className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-3"
                  style={{ background: 'var(--gradient-accent-soft)' }}
                >
                  <Icon name="lock" className="w-5 h-5" style={{ color: 'var(--accent-blue)' }} />
                </span>
                <h2 className="text-display text-xl mb-1.5">Choose a new password</h2>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {email ? (
                    <>
                      For <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
                    </>
                  ) : (
                    'Enter a new password for your account'
                  )}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <PasswordField
                  id="reset-password"
                  label="New password"
                  value={password}
                  onChange={setPassword}
                  showStrength
                  autoComplete="new-password"
                />
                <PasswordField
                  id="reset-password-confirm"
                  label="Confirm new password"
                  value={confirmPassword}
                  onChange={setConfirmPassword}
                  autoComplete="new-password"
                />
                <button
                  type="submit"
                  disabled={submitting}
                  aria-busy={submitting}
                  className="btn-gradient w-full"
                  style={{ height: 48, fontSize: '0.9375rem' }}
                >
                  {submitting ? <Spinner label="Updating…" /> : 'Update password'}
                </button>
              </form>
            </>
          )}

          {!checking && !codeValid && !done && (
            <div className="text-center py-2">
              <span
                className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-3"
                style={{ background: 'var(--accent-red-glow, rgba(220,38,38,0.1))' }}
              >
                <Icon name="alert" className="w-5 h-5" style={{ color: 'var(--accent-red)' }} />
              </span>
              <h2 className="text-display text-xl mb-1.5">Link no longer valid</h2>
              <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
                {error?.message || 'This link has expired or already been used. Request a new one.'}
              </p>
              <Link to="/forgot-password" className="btn-gradient w-full inline-flex" style={{ height: 48, fontSize: '0.9375rem' }}>
                Request a new link
              </Link>
            </div>
          )}

          {done && (
            <div className="text-center py-2">
              <span
                className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-3"
                style={{ background: 'var(--gradient-accent-soft)' }}
              >
                <Icon name="check" className="w-5 h-5" style={{ color: 'var(--accent-blue)' }} />
              </span>
              <h2 className="text-display text-xl mb-1.5">Password updated</h2>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Redirecting you to sign in…
              </p>
            </div>
          )}

          {error && codeValid && !done && (
            <p role="alert" className="note mt-3" data-tone="danger">
              <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
              <span>{error.message}</span>
            </p>
          )}

          {!done && (
            <p className="mt-6 pt-4 text-center text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <Link to="/login" className="font-semibold underline underline-offset-2" style={{ color: 'var(--accent-blue)' }}>
                Back to sign in
              </Link>
            </p>
          )}
        </div>

        <AuthDisclaimer />
      </motion.div>
    </div>
  )
}
