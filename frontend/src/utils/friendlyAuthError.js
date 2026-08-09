/**
 * Maps Firebase Auth error codes to structured, user-safe error info.
 *
 * Returns `{ code, message }` (or `null` for errors that aren't worth
 * surfacing, e.g. the user closed the sign-in popup themselves) instead of
 * a bare string, so callers can branch UI behavior — inline CTAs, disabling
 * the submit button, auto-switching tabs — off the stable Firebase `code`
 * without re-parsing the message text.
 *
 * `auth/user-not-found` and `auth/wrong-password` (and `auth/invalid-credential`,
 * which newer Firebase SDK versions return for both) are deliberately merged
 * into one message — telling a caller which half of a credential pair is
 * wrong is a user-enumeration and credential-stuffing aid. The merged copy
 * still tells the user both real possibilities so they aren't left guessing
 * why the request "failed silently".
 */
export function friendlyAuthError(err) {
  const code = err?.code || ''

  if (code === 'auth/popup-closed-by-user' || code === 'auth/cancelled-popup-request') return null

  if (
    code === 'auth/invalid-credential' ||
    code === 'auth/user-not-found' ||
    code === 'auth/wrong-password'
  ) {
    return { code, message: "Incorrect email or password. If you don't have an account, sign up instead." }
  }
  if (code === 'auth/invalid-email') {
    return { code, message: "That doesn't look like a valid email address." }
  }
  if (code === 'auth/user-disabled') {
    return { code, message: 'This account has been disabled. Contact support.' }
  }
  if (code === 'auth/account-exists-with-different-credential') {
    // Message is intentionally generic here — Login.jsx/Signup.jsx render a
    // provider-specific variant (Google-side vs email-side) using `code`.
    return { code, message: 'An account with this email already exists using a different sign-in method.' }
  }
  if (code === 'auth/email-already-in-use') {
    return { code, message: 'An account with these details already exists. Try signing in instead.' }
  }
  if (code === 'auth/weak-password') {
    return { code, message: 'Choose a stronger password.' }
  }
  if (code === 'auth/network-request-failed') {
    return { code, message: 'Connection issue. Check your internet and try again.' }
  }
  if (code === 'auth/popup-blocked') {
    return { code, message: 'Popup blocked. Allow popups for this site and try again.' }
  }
  if (code === 'auth/invalid-phone-number') {
    return { code, message: 'Enter a valid phone number.' }
  }
  if (code === 'auth/too-many-requests') {
    return { code, message: 'Too many attempts. Try again in a few minutes or reset your password.' }
  }
  if (code === 'auth/credential-already-in-use') {
    return { code, message: 'An account with these details already exists. Try signing in instead.' }
  }
  if (code === 'auth/invalid-verification-code') {
    return { code, message: 'Incorrect code. Check the SMS and try again.' }
  }
  if (code === 'auth/code-expired') {
    return { code, message: 'That code expired. Request a new one.' }
  }
  if (code === 'auth/requires-recent-login') {
    return { code, message: 'For security, please sign in again before retrying this action.' }
  }
  if (code === 'auth/user-mismatch') {
    return {
      code,
      message: 'That was a different Google account. Choose the same account you are currently signed in with.',
    }
  }
  if (code === 'auth/invalid-app-credential' || code === 'auth/captcha-check-failed' || code === 'auth/argument-error') {
    return { code, message: "Couldn't verify this device for phone sign-in. Refresh the page and try again." }
  }
  if (code === 'auth/quota-exceeded') {
    return { code, message: 'SMS quota reached for this project. Try again later or contact support.' }
  }
  // Password-reset action-code errors (used on /reset-password-confirm).
  if (code === 'auth/expired-action-code') {
    return { code, message: 'This link has expired. Request a new one.' }
  }
  if (code === 'auth/invalid-action-code') {
    return { code, message: 'This link has already been used or is invalid. Request a new one.' }
  }

  // Anything not mapped above — log the real Firebase code to the console
  // so it's diagnosable (this is a stable string like "auth/xyz", never a
  // credential or personal data), while the UI still only ever shows the
  // generic message below.
  if (code) {
    // eslint-disable-next-line no-console
    console.error(`[auth] Unhandled Firebase error code: ${code}`, err?.message || '')
  }
  return { code: code || 'unknown', message: 'Something went wrong. Please try again.' }
}
