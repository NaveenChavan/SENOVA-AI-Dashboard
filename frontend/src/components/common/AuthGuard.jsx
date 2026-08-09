import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { auth, onAuthStateChanged, isVerificationExempt } from '../../services/firebase'
import Loader from './Loader'

/**
 * Gates a route behind Firebase Auth. Shows a loader while Firebase
 * resolves the initial auth state (it's async on page load), then
 * redirects to /login if there's no signed-in user, or to /verify-email
 * if they signed up with email/password and haven't clicked the
 * verification link yet (Google and Phone accounts are exempt — see
 * `isVerificationExempt`).
 */
export default function AuthGuard({ children }) {
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

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!user.emailVerified && !isVerificationExempt(user)) {
    return <Navigate to="/verify-email" replace />
  }

  return children
}
