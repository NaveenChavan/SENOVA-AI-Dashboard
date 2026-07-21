import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { auth, onAuthStateChanged } from '../../services/firebase'
import Loader from './Loader'

/**
 * Gates a route behind Firebase Auth. Shows a loader while Firebase
 * resolves the initial auth state (it's async on page load), then
 * redirects to /login if there's no signed-in user.
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

  return children
}
