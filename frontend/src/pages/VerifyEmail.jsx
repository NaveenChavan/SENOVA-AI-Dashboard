import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import { auth, onAuthStateChanged, resendVerificationEmail, refreshEmailVerified, signOut, isVerificationExempt } from '../services/firebase'
import { friendlyAuthError } from '../utils/friendlyAuthError'
import Icon from '../components/common/Icon'
import Spinner from '../components/common/Spinner'
import ThemeToggle from '../components/common/ThemeToggle'

const EASE = [0.16, 1, 0.3, 1]
const RESEND_COOLDOWN_SECONDS = 30

/**
 * Shown right after email/password signup, and to any signed-in
 * email/password user whose address isn't verified yet (see `AuthGuard`).
 * Not shown to Google or Phone accounts — `isVerificationExempt` sends
 * those straight through instead.
 */
export default function VerifyEmail() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [email, setEmail] = useState(auth.currentUser?.email ?? '')

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (!user) {
        navigate('/login', { replace: true })
        return
      }
      setEmail(user.email ?? '')
      if (user.emailVerified || isVerificationExempt(user)) {
        navigate('/upload', { replace: true })
      }
    })
    return unsubscribe
  }, [navigate])

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [cooldown])

  const handleCheckAgain = async () => {
    setError('')
    setMessage('')
    setChecking(true)
    try {
      const verified = await refreshEmailVerified()
      if (verified) {
        navigate('/upload', { replace: true })
      } else {
        setMessage("Not verified yet — click the link in the email we sent, then check again.")
      }
    } catch (err) {
      const info = friendlyAuthError(err)
      if (info) setError(info.message)
    } finally {
      setChecking(false)
    }
  }

  const handleResend = async () => {
    setError('')
    setMessage('')
    setResending(true)
    try {
      await resendVerificationEmail()
      setMessage('Verification email sent again — check your inbox and spam folder.')
      setCooldown(RESEND_COOLDOWN_SECONDS)
    } catch (err) {
      const info = friendlyAuthError(err)
      if (info) setError(info.message)
    } finally {
      setResending(false)
    }
  }

  const handleUseDifferentAccount = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="min-h-dvh w-full flex items-center justify-center relative px-4 py-10" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Verify your email — SENOVA Digital Lab</title>
        <meta name="description" content="Verify your email address to finish creating your SENOVA account." />
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

        <div className="card text-center" style={{ padding: 32 }}>
          <span
            className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-3"
            style={{ background: 'var(--gradient-accent-soft)' }}
          >
            <Icon name="inbox" className="w-5 h-5" style={{ color: 'var(--accent-blue)' }} />
          </span>
          <h2 className="text-display text-xl mb-1.5">Check your email</h2>
          <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
            We sent a verification link to{' '}
            {email && <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>}. Click it, then come back and
            select "I've verified" below.
          </p>

          <button
            onClick={handleCheckAgain}
            disabled={checking}
            aria-busy={checking}
            className="btn-gradient w-full"
            style={{ height: 48, fontSize: '0.9375rem' }}
          >
            {checking ? <Spinner label="Checking…" /> : "I've verified — continue"}
          </button>

          <button
            onClick={handleResend}
            disabled={resending || cooldown > 0}
            aria-busy={resending}
            className="btn w-full mt-2.5"
            style={{ height: 44 }}
          >
            {resending ? <Spinner label="Sending…" /> : cooldown > 0 ? `Resend available in ${cooldown}s` : 'Resend verification email'}
          </button>

          {message && (
            <p role="status" className="note mt-3" data-tone="info">
              <Icon name="info" className="w-4 h-4 shrink-0 mt-px" />
              <span>{message}</span>
            </p>
          )}
          {error && (
            <p role="alert" className="note mt-3" data-tone="danger">
              <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
              <span>{error}</span>
            </p>
          )}

          <p className="mt-6 pt-4 text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            Wrong email?{' '}
            <button
              type="button"
              onClick={handleUseDifferentAccount}
              className="font-semibold underline underline-offset-2"
              style={{ color: 'var(--accent-blue)' }}
            >
              Sign out and use a different one
            </button>
          </p>
        </div>
      </motion.div>
    </div>
  )
}
