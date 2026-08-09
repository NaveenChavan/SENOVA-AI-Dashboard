import Icon from './Icon'

/**
 * Standard footer note shown under the sign-in card on every auth page.
 * Calm, factual, one line — a security/legal footnote should read as
 * routine reassurance, not a warning. Kept as a single shared component so
 * the wording never drifts between Login, Signup and Forgot Password.
 */
export default function AuthDisclaimer() {
  return (
    <div className="mt-4 space-y-2">
      <p
        className="flex items-center justify-center gap-1.5 text-xs"
        style={{ color: 'var(--text-muted)' }}
      >
        <Icon name="lock" className="w-3.5 h-3.5" />
        Your credentials are handled by Firebase Authentication — SENOVA never sees or stores your password.
      </p>
      <p className="text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        By continuing, you agree to SENOVA's Terms of Service and Privacy Policy.
      </p>
    </div>
  )
}
