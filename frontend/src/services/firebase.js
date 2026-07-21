/**
 * Firebase initialisation — single source of truth for the app's Firebase
 * instance, Auth instance, and Google sign-in provider.
 *
 * All config values come from Vite environment variables (see `.env.example`)
 * so no secrets are hardcoded in source. Firebase web config values are safe
 * to expose client-side by design (they identify the project, not a secret
 * key), but env vars still keep per-environment (dev/staging/prod) config
 * out of source control and easy to rotate.
 */

import { initializeApp } from 'firebase/app'
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged,
} from 'firebase/auth'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

if (!firebaseConfig.apiKey || !firebaseConfig.projectId) {
  // Fail loudly in dev instead of silently producing confusing auth errors later.
  console.error(
    '[firebase] Missing VITE_FIREBASE_* environment variables. ' +
      'Copy frontend/.env.example to frontend/.env and fill in your Firebase config.',
  )
}

export const firebaseApp = initializeApp(firebaseConfig)
export const auth = getAuth(firebaseApp)

const googleProvider = new GoogleAuthProvider()
// Always show the account picker so users on shared machines don't get
// silently signed in as the last cached Google account.
googleProvider.setCustomParameters({ prompt: 'select_account' })

/**
 * Opens the Google sign-in popup and returns the signed-in Firebase user.
 * Throws on popup-closed-by-user / network errors — callers should catch
 * and show a friendly message.
 */
export async function signInWithGoogle() {
  const result = await signInWithPopup(auth, googleProvider)
  return result.user
}

export async function signOut() {
  await firebaseSignOut(auth)
}

/**
 * Returns the current user's Firebase ID token, refreshing it if it's
 * close to expiry. Returns null if no user is signed in.
 */
export async function getIdToken(forceRefresh = false) {
  const user = auth.currentUser
  if (!user) return null
  return user.getIdToken(forceRefresh)
}

export { onAuthStateChanged }
