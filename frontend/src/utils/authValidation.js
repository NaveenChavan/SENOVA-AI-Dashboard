/**
 * Client-side validation for the auth forms (signup, login, password reset).
 *
 * These checks exist to give the user immediate feedback and to stop
 * obviously-invalid requests before they hit Firebase — they are not a
 * substitute for Firebase's own server-side enforcement (min length,
 * duplicate-account checks, rate limiting), which still runs regardless.
 */

const MIN_PASSWORD_LENGTH = 8

/**
 * Password rule: at least 8 characters, and at least one lowercase letter,
 * one uppercase letter, and one digit. Stricter than Firebase's own 6-char
 * minimum, deliberately — an email-recoverable account is worth a
 * slightly higher bar than the platform default.
 *
 * Returns `{ valid, reasons }` — `reasons` is a list of unmet rules, in a
 * stable order, so the UI can render them as a checklist.
 */
export function checkPasswordStrength(password) {
  const value = password || ''
  const reasons = []

  if (value.length < MIN_PASSWORD_LENGTH) reasons.push(`At least ${MIN_PASSWORD_LENGTH} characters`)
  if (!/[a-z]/.test(value)) reasons.push('One lowercase letter')
  if (!/[A-Z]/.test(value)) reasons.push('One uppercase letter')
  if (!/[0-9]/.test(value)) reasons.push('One number')

  return { valid: reasons.length === 0, reasons }
}

/** Basic shape check — real validity is enforced by Firebase on submit. */
export function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((email || '').trim())
}

/**
 * Resolves the right thing to display for a signed-in Firebase user: their
 * display name is checked first by callers, then their email, falling
 * back to a neutral label for the rare account with neither (e.g. a
 * Google account that hasn't set a name).
 */
export function displayIdentifier(firebaseUser) {
  if (!firebaseUser) return ''
  return firebaseUser.email || 'Signed in'
}
