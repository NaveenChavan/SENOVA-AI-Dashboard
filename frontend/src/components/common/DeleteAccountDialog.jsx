import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { deleteCurrentAccount } from '../../services/firebase'
import { friendlyAuthError } from '../../utils/friendlyAuthError'
import Icon from './Icon'
import Spinner from './Spinner'

/**
 * Confirmation dialog for permanent account deletion. Google accounts
 * re-authenticate via a fresh popup (no password to check); Email/Password
 * and Phone/Password accounts must type their current password — Firebase
 * requires a recent sign-in for this operation regardless.
 */
export default function DeleteAccountDialog({ open, onClose, isGoogleAccount, accountEmail }) {
  const [password, setPassword] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit = isGoogleAccount ? confirmText === 'DELETE' : confirmText === 'DELETE' && password.length > 0

  const handleClose = () => {
    setPassword('')
    setConfirmText('')
    setError('')
    onClose()
  }

  const handleDelete = async (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      // Safety net: if the browser silently blocks the re-auth popup
      // (some browsers never reject the promise in that case, they just
      // never resolve it), don't leave the button stuck on "Deleting…"
      // forever — time out and tell the user what to check.
      const timeout = new Promise((_, reject) =>
        window.setTimeout(
          () => reject({ code: 'auth/popup-blocked' }),
          20000,
        ),
      )
      await Promise.race([deleteCurrentAccount(isGoogleAccount ? undefined : password), timeout])
      // Firebase signs the user out automatically once their account is
      // deleted — the app's own onAuthStateChanged listener in App.jsx
      // picks that up and the header/nav update on its own.
    } catch (err) {
      // Unlike the sign-in flow, a closed/blocked re-auth popup here must
      // NOT be treated as "silent, no error" — the user is still looking
      // at this dialog and needs to know the delete did not happen,
      // otherwise the button appears to hang indefinitely with no feedback.
      if (err?.code === 'auth/popup-closed-by-user' || err?.code === 'auth/cancelled-popup-request') {
        setError('Google confirmation was closed before finishing. Try again to delete your account.')
      } else if (err?.code === 'auth/popup-blocked') {
        setError('Your browser blocked the confirmation popup. Allow popups for this site and try again.')
      } else if (err?.code === 'auth/user-mismatch') {
        setError(
          accountEmail
            ? `That was a different Google account. Confirm with ${accountEmail} — the account you're signed in as.`
            : "That was a different Google account. Confirm with the account you're currently signed in as.",
        )
      } else {
        const info = friendlyAuthError(err)
        setError(info?.message || 'Could not delete your account. Please try again.')
      }
    } finally {
      setLoading(false)
      setPassword('')
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div
            className="absolute inset-0"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={handleClose}
            aria-hidden="true"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-account-title"
            className="relative w-full rounded-xl overflow-hidden"
            style={{ maxWidth: 420, background: 'var(--bg-card-solid)', border: '1px solid var(--border-subtle)', boxShadow: 'var(--shadow-high)' }}
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <form onSubmit={handleDelete} className="p-5">
              <div className="flex items-start gap-3 mb-4">
                <span
                  className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center"
                  style={{ background: 'rgba(220, 38, 38, 0.12)' }}
                >
                  <Icon name="alert" className="w-4.5 h-4.5" style={{ color: 'var(--accent-red)' }} />
                </span>
                <div>
                  <h2 id="delete-account-title" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Delete your account
                  </h2>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                    This permanently removes your sign-in. It cannot be undone.
                  </p>
                </div>
              </div>

              {isGoogleAccount ? (
                <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
                  {accountEmail ? (
                    <>
                      You'll be asked to confirm via Google as{' '}
                      <strong style={{ color: 'var(--text-primary)' }}>{accountEmail}</strong>. Choose that same
                      account — picking a different one will fail.
                    </>
                  ) : (
                    "You'll be asked to confirm via Google before deletion."
                  )}
                </p>
              ) : (
                <div className="mb-4">
                  <label htmlFor="delete-password" className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                    Current password
                  </label>
                  <input
                    id="delete-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    className="field-input"
                    required
                  />
                </div>
              )}

              <div className="mb-4">
                <label htmlFor="delete-confirm" className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Type <span style={{ color: 'var(--text-primary)' }}>DELETE</span> to confirm
                </label>
                <input
                  id="delete-confirm"
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="field-input"
                  autoComplete="off"
                  required
                />
              </div>

              {error && (
                <p role="alert" className="note mb-4" data-tone="danger">
                  <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
                  <span>{error}</span>
                </p>
              )}

              <div className="flex gap-2 justify-end">
                <button type="button" onClick={handleClose} className="btn" disabled={loading}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!canSubmit || loading}
                  aria-busy={loading}
                  className="btn"
                  style={{ background: 'var(--accent-red)', borderColor: 'transparent', color: '#ffffff' }}
                >
                  {loading ? <Spinner label="Deleting…" /> : 'Delete permanently'}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
