# SENOVA AI Dashboard — Auth System Session (2026-07-31)

Session summary: added a full email/password + Google authentication system
(originally scoped to include phone/password too, later removed on request),
fixed a critical crash bug, hardened several security/UX gaps found during
manual testing, and diagnosed a Firebase phone-auth SMS region issue before
phone auth was ultimately dropped entirely.

---

## 1. Initial build — three sign-in methods

**Plan confirmed before coding:** Firebase Auth (JWT ID tokens) — not Auth0.
Backend already verifies Firebase ID tokens the same way regardless of
provider, so **no backend changes were needed** at any point in this session.

Built:
- **Google sign-in** — already existed, untouched.
- **Email + Password** — `signUpWithEmail`, `signInWithEmail`,
  `sendEmailPasswordReset` in `frontend/src/services/firebase.js`.
- **Phone + Password** (later removed, see §4) — Firebase has no native
  "phone + password" provider, so this was built as: OTP-verify once at
  signup → link an Email/Password credential using a synthetic,
  non-routable email (`p<digits>@phone.senova.internal`) → plain
  phone+password login afterwards with no SMS needed.

New files created:
- `frontend/src/pages/Signup.jsx` — tabbed sign-up (Google / Email / Phone
  at the time).
- `frontend/src/pages/ForgotPassword.jsx` — password reset.
- `frontend/src/pages/VerifyEmail.jsx` — post-signup email verification
  gate.
- `frontend/src/components/common/PasswordField.jsx` — show/hide + live
  strength checklist.
- `frontend/src/components/common/Spinner.jsx`, `GoogleGlyph.jsx` — shared
  UI pieces extracted to avoid duplication across Login/Signup.
- `frontend/src/components/common/AuthDisclaimer.jsx` — shared, calm
  footer disclaimer ("Firebase handles your credentials…").
- `frontend/src/components/common/GuestGuard.jsx` — inverse of
  `AuthGuard`; redirects an already-signed-in user away from
  `/login`, `/signup`, `/forgot-password`.
- `frontend/src/components/common/DeleteAccountDialog.jsx` — account
  self-deletion with re-auth + type-DELETE-to-confirm.
- `frontend/src/utils/authValidation.js` — password strength rule (8+
  chars, upper/lower/digit), email shape check, `displayIdentifier`
  helper.
- `frontend/src/utils/friendlyAuthError.js` — maps Firebase error codes to
  generic, non-enumerating user-facing messages.

## 2. Security hardening pass

- **Email verification enforced.** `signUpWithEmail` now sends a
  verification email immediately; `AuthGuard` redirects unverified
  email/password users to `/verify-email` until they click the link.
  Google accounts are exempt (Google already verifies the address).
- **Anti-enumeration:** forgot-password always shows "if an account
  exists…" regardless of whether it does; login errors never reveal
  which half of a credential pair (email vs. password) was wrong.
- **Fixed a real data leak:** `App.jsx`'s account menu was displaying
  raw `user.email` — for the (then-existing) phone accounts this would
  have shown the internal synthetic email. Added `displayIdentifier()`
  to resolve a safe value instead. (Simplified further once phone auth
  was removed — see §4.)
- **Account deletion** added to the header user menu, gated behind
  re-authentication (password re-entry, or a fresh Google popup) plus a
  type-`DELETE` confirmation — Firebase requires a recent sign-in for
  this operation regardless.
- Forms clear their fields after every submit attempt (success or
  failure), all submit buttons are `disabled` while a request is in
  flight, and a `.field-input` CSS class was added to `index.css` so
  the new inputs match the existing design-token system exactly.

## 3. Bugs found and fixed during manual testing

- **Critical crash:** `Login.jsx` was calling `friendlyAuthError(err)` in
  three handlers without importing it — every email/phone sign-in
  attempt threw `ReferenceError` and surfaced as a generic
  "Something went wrong." Fixed by restoring the missing import.
- **Duplicate theme toggle:** `App.jsx`'s `isAuthScreen` check only
  matched `/login`, so `/signup` and `/forgot-password` were rendering
  *both* the full navbar (with its own toggle) *and* the page's own
  standalone toggle. Fixed by matching all four auth routes
  (`/login`, `/signup`, `/forgot-password`, `/verify-email`).

## 4. Firebase phone-auth diagnosis (for the record)

Phone sign-in initially failed in the browser with a generic
"Something went wrong." Root-caused step by step:

1. Added console logging of the raw Firebase error code in
   `friendlyAuthError` (kept — useful for any future unmapped error).
2. First real error surfaced: `auth/operation-not-allowed` — Firebase's
   **SMS region policy** had India blocked by default. Fixed in
   Firebase Console → Authentication → Settings → SMS region policy
   (Allow + India).
3. Confirmed via Firebase's own docs that `localhost` is not an
   authorized domain for phone auth by design, and that phone auth at
   any real volume requires the **Blaze (pay-as-you-go) plan** for SMS
   billbilling — this was the deciding factor to drop phone auth.
4. A visible reCAPTCHA badge was also traced to Google's script
   injecting its floating badge even in invisible mode; a
   `.grecaptcha-badge { visibility: hidden !important; }` rule was
   added and later removed along with the rest of the phone code.

## 5. Phone auth fully removed

Per final instruction, phone/password sign-in was removed entirely,
leaving **Google and Email/Password only**:

- `firebase.js` — removed `sendPhoneOtp`, `confirmPhoneOtpAndSetPassword`,
  `signInWithPhonePassword`, `confirmPhoneOtpAndResetPassword`,
  `getRecaptchaVerifier`/`resetRecaptcha`, `phoneToSyntheticEmail`, the
  `SYNTHETIC_EMAIL_DOMAIN` constant, and all now-unused imports
  (`RecaptchaVerifier`, `signInWithPhoneNumber`, `linkWithCredential`,
  `updatePassword`). Simplified `isVerificationExempt` to a single
  Google-provider check.
- `Login.jsx` — Phone tab, state and handler removed; tab grid is now
  2-column (Google / Email).
- `Signup.jsx` — rewritten without the phone/OTP flow (375 → 192 lines).
- `ForgotPassword.jsx` — rewritten as a single email-only form, no
  method tabs needed (330 → 150 lines).
- `AuthDisclaimer.jsx` / `index.css` — removed the reCAPTCHA disclosure
  text and the `.grecaptcha-badge` hiding rule (no longer relevant).
- `authValidation.js` — removed `isValidE164Phone`/`toE164`; simplified
  `displayIdentifier` to `email || 'Signed in'`.
- Tests updated to match (`authValidation.test.js`: 14 → 9 cases).

## Verification

Run at each stage of this session:

```bash
cd frontend
npm test -- --run   # final state: 5 files, 64 tests passed
npm run build        # final state: clean, smaller chunks confirm dead code removed
```

No backend changes were made or required at any point.

## Firebase Console changes made this session

- Confirmed Email/Password, Phone, Google providers enabled (Spark plan).
- Set SMS region policy to Allow + India (no longer relevant — phone
  auth removed — but left as-is in the console; harmless if unused).
- Phone provider can be safely disabled in Firebase Console
  (Authentication → Sign-in method → Phone) since the app no longer
  calls it, though this was not done as part of this session.
