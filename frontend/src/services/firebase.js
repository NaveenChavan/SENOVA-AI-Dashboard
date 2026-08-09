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
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendPasswordResetEmail,
  sendEmailVerification,
  verifyPasswordResetCode,
  confirmPasswordReset,
  EmailAuthProvider,
  reauthenticateWithCredential,
  reauthenticateWithPopup,
  deleteUser,
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

// ── Email / Password ──────────────────────────────────────────────────────

/**
 * Creates a new account with email + password, then immediately sends a
 * verification email. Firebase enforces a 6-char minimum server-side; the
 * app's own password strength rule (see `utils/authValidation.js`) is
 * stricter and is checked client-side before this is ever called.
 *
 * The account exists in Firebase right away (so a duplicate signup attempt
 * correctly fails with `auth/email-already-in-use`), but the caller is
 * expected to keep the user out of the app itself — see `isEmailVerified`
 * and the `AuthGuard` gate — until they click the link in that email. This
 * is what stops someone from typing a bogus/typo'd address and getting
 * straight into the dashboard.
 */
export async function signUpWithEmail(email, password) {
  const result = await createUserWithEmailAndPassword(auth, email, password)
  await sendEmailVerification(result.user)
  return result.user
}

export async function signInWithEmail(email, password) {
  const result = await signInWithEmailAndPassword(auth, email, password)
  return result.user
}

/**
 * Firebase's own built-in password-reset email. Used only as a fallback
 * when the backend reports it can't send the branded SendGrid version yet
 * (`email_dispatched: false`) — see `pages/ForgotPassword.jsx`. Delivery
 * from Firebase's shared `firebaseapp.com` sender frequently lands in
 * Spam, which is exactly why the SendGrid path exists; this keeps password
 * reset functional in the meantime rather than silently doing nothing.
 */
export async function sendEmailPasswordReset(email) {
  await sendPasswordResetEmail(auth, email)
}

/**
 * Verifies a password-reset action code (the `oobCode` query param on
 * `/reset-password-confirm`) without consuming it. Returns the email
 * address the code was issued for, or throws `auth/expired-action-code` /
 * `auth/invalid-action-code` if the link is expired or already used.
 */
export async function verifyResetCode(oobCode) {
  return verifyPasswordResetCode(auth, oobCode)
}

/**
 * Consumes the action code and sets the new password. Throws the same
 * expired/invalid-action-code errors as `verifyResetCode` if the code was
 * valid a moment ago but has since expired or been used elsewhere.
 */
export async function confirmReset(oobCode, newPassword) {
  await confirmPasswordReset(auth, oobCode, newPassword)
}

/** Re-sends the verification email to the currently signed-in user. */
export async function resendVerificationEmail() {
  const user = auth.currentUser
  if (!user) throw new Error('No signed-in user to verify.')
  await sendEmailVerification(user)
}

/**
 * Re-fetches the current user's record from Firebase and returns whether
 * their email is verified. `user.emailVerified` on the cached client object
 * only updates after a token refresh, so this reload is what lets the
 * "I've clicked the link, check again" button actually see the change.
 */
export async function refreshEmailVerified() {
  const user = auth.currentUser
  if (!user) return false
  await user.reload()
  return user.emailVerified
}

/**
 * True if this signed-in user's provider requires no further verification:
 * Google accounts are pre-verified by Google. Plain email/password
 * accounts still need the `emailVerified` flag checked.
 */
export function isVerificationExempt(user) {
  if (!user) return false
  const providerIds = user.providerData.map((p) => p.providerId)
  return providerIds.includes('google.com')
}

// ── Account deletion ──────────────────────────────────────────────────────

/**
 * Permanently deletes the current user's Firebase Auth account.
 *
 * Firebase requires a "recent" sign-in for this sensitive operation and
 * throws `auth/requires-recent-login` otherwise, so callers must supply
 * how to re-authenticate first:
 *   - `password` — for Email/Password accounts.
 *   - no `password` — re-opens the Google popup instead, since Google
 *     accounts have no password to check.
 *
 * This only removes the Firebase Auth identity. It does not delete any
 * uploaded files — those already expire on their own TTL sweep
 * (`UPLOAD_TTL_MINUTES`, see backend), and there is no separate per-user
 * profile store on the backend to clean up.
 */
export async function deleteCurrentAccount(password) {
  const user = auth.currentUser
  if (!user) throw new Error('No signed-in user to delete.')

  const providerIds = user.providerData.map((p) => p.providerId)
  if (providerIds.includes('google.com')) {
    // Re-authentication must happen as the SAME account that's signed in —
    // picking a different one in the account chooser makes Firebase throw
    // `auth/user-mismatch`. A dedicated provider instance with `login_hint`
    // pre-selects the right account instead of showing a blank picker, and
    // deliberately does NOT carry the `prompt: 'select_account'` parameter
    // the sign-in provider uses (that parameter is what forces the chooser
    // open and invites picking the wrong account here).
    const reauthProvider = new GoogleAuthProvider()
    if (user.email) {
      reauthProvider.setCustomParameters({ login_hint: user.email })
    }
    await reauthenticateWithPopup(user, reauthProvider)
  } else {
    if (!user.email) throw new Error('Cannot re-authenticate this account.')
    const credential = EmailAuthProvider.credential(user.email, password)
    await reauthenticateWithCredential(user, credential)
  }

  await deleteUser(user)
}

export { onAuthStateChanged }
