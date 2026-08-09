import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { auth, onAuthStateChanged } from '../../services/firebase'
import Loader from './Loader'

/**
 * The inverse of `AuthGuard` — gates the public auth pages (login, signup,
 * forgot-password) behind having NO session. An already-signed-in user who
 * lands on /login (e.g. via a bookmark, back button, or a stale tab) is
 * sent straight to /upload instead of being shown the sign-in form again.
 *
 * Verification status isn't checked here — an unverified email/password
 * user is still "logged in" for this purpose; `AuthGuard` on the protected
 * routes is what redirects them onward to /verify-email.
 */
export default function GuestGuard({ children }) {
  const [user, setUser] = useState(auth.currentUser)
  const [checked, setChecked] = useState(auth.currentUser !== null)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      setChecked(true)
    })
    return unsubscribe
  }, [])

  if (!checked) {
    return <Loader message="Checking your session…" />
  }

  if (user) {
    return <Navigate to="/upload" replace />
  }

  return children
}
