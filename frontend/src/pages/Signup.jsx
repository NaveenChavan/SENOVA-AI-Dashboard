import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import { signInWithGoogle, signUpWithEmail } from '../services/firebase'
import { checkPasswordStrength, isValidEmail } from '../utils/authValidation'
import { friendlyAuthError } from '../utils/friendlyAuthError'
import Icon from '../components/common/Icon'
import PasswordField from '../components/common/PasswordField'
import Spinner from '../components/common/Spinner'
import GoogleGlyph from '../components/common/GoogleGlyph'
import ThemeToggle from '../components/common/ThemeToggle'
import AuthDisclaimer from '../components/common/AuthDisclaimer'

const EASE = [0.16, 1, 0.3, 1]

const TABS = [
  { id: 'google', label: 'Google' },
  { id: 'email', label: 'Email' },
]

export default function Signup() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('email')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleGoogleSignUp = async () => {
    setError('')
    setLoading(true)
    try {
      await signInWithGoogle()
      navigate('/upload')
    } catch (err) {
      const info = friendlyAuthError(err)
      if (info) setError(info.message)
    } finally {
      setLoading(false)
    }
  }

  const handleEmailSignUp = async (event) => {
    event.preventDefault()
    setError('')

    if (!isValidEmail(email)) {
      setError('Enter a valid email address.')
      return
    }
    const { valid } = checkPasswordStrength(password)
    if (!valid) {
      setError('Password does not meet the requirements below.')
      return
    }

    setLoading(true)
    try {
      await signUpWithEmail(email, password)
      navigate('/verify-email')
    } catch (err) {
      const info = friendlyAuthError(err)
      if (info) setError(info.message)
    } finally {
      setLoading(false)
      setEmail('')
      setPassword('')
    }
  }

  return (
    <div className="min-h-dvh w-full flex items-center justify-center relative px-4 py-10" style={{ background: 'var(--bg-primary)' }}>
      <Helmet>
        <title>Create account — SENOVA Digital Lab</title>
        <meta name="description" content="Create a SENOVA account to access AI-powered retail sales analytics." />
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
            <h2 className="text-display text-xl mb-1.5">Create your account</h2>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Choose how you'd like to sign up
            </p>
          </div>

          {/* Tab switcher */}
          <div role="tablist" aria-label="Sign-up method" className="grid grid-cols-2 gap-1.5 p-1 rounded-xl mb-5" style={{ background: 'var(--bg-card-hover)' }}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={activeTab === tab.id}
                onClick={() => {
                  setActiveTab(tab.id)
                  setError('')
                }}
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

          {activeTab === 'google' && (
            <button onClick={handleGoogleSignUp} disabled={loading} aria-busy={loading} className="btn-gradient w-full" style={{ height: 48, fontSize: '0.9375rem' }}>
              {loading ? (
                <Spinner label="Signing up…" />
              ) : (
                <>
                  <GoogleGlyph />
                  Continue with Google
                </>
              )}
            </button>
          )}

          {activeTab === 'email' && (
            <form onSubmit={handleEmailSignUp} className="space-y-4">
              <div>
                <label htmlFor="signup-email" className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Email address
                </label>
                <input
                  id="signup-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="field-input"
                  required
                />
              </div>
              <PasswordField id="signup-password" label="Password" value={password} onChange={setPassword} showStrength autoComplete="new-password" />
              <button type="submit" disabled={loading} aria-busy={loading} className="btn-gradient w-full" style={{ height: 48, fontSize: '0.9375rem' }}>
                {loading ? <Spinner label="Creating account…" /> : 'Create account'}
              </button>
            </form>
          )}

          {error && (
            <p role="alert" className="note mt-3" data-tone="danger">
              <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
              <span>{error}</span>
            </p>
          )}

          <p className="mt-6 pt-4 text-center text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            Already have an account?{' '}
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
