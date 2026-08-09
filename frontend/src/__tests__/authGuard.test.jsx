import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { isVerificationExempt } from '../services/firebase'

/**
 * AuthGuard's routing decision (signed out -> /login, unverified email/password
 * user -> /verify-email, Google user -> straight through even if
 * `emailVerified` is false) depends on two things: the live `auth.currentUser`
 * object and the `onAuthStateChanged` subscription. Both are mocked here so
 * the test exercises AuthGuard's actual branching logic without touching the
 * real Firebase SDK (which would need live project credentials to initialise
 * meaningfully in a test environment).
 */

const mockUnsubscribe = vi.fn()
let mockCurrentUser = null
let mockOnAuthStateChangedImpl = (callback) => {
  callback(mockCurrentUser)
  return mockUnsubscribe
}

vi.mock('../services/firebase', async () => {
  const actual = await vi.importActual('../services/firebase')
  return {
    ...actual,
    auth: {
      get currentUser() {
        return mockCurrentUser
      },
    },
    onAuthStateChanged: (_auth, callback) => mockOnAuthStateChangedImpl(callback),
  }
})

// AuthGuard is imported after the mock is registered so it picks up the
// mocked `auth`/`onAuthStateChanged` exports.
const AuthGuard = (await import('../components/common/AuthGuard')).default

function renderGuarded(initialPath = '/upload') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="/verify-email" element={<div>Verify email page</div>} />
        <Route path="/upload" element={<AuthGuard><div>Protected content</div></AuthGuard>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('isVerificationExempt', () => {
  it('is true for a Google-provider user regardless of emailVerified', () => {
    const googleUser = { providerData: [{ providerId: 'google.com' }], emailVerified: false }
    expect(isVerificationExempt(googleUser)).toBe(true)
  })

  it('is false for an email/password-provider user', () => {
    const passwordUser = { providerData: [{ providerId: 'password' }], emailVerified: false }
    expect(isVerificationExempt(passwordUser)).toBe(false)
  })

  it('is false for no user at all', () => {
    expect(isVerificationExempt(null)).toBe(false)
  })
})

describe('AuthGuard', () => {
  it('redirects to /login when no user is signed in', async () => {
    mockCurrentUser = null
    renderGuarded()
    await waitFor(() => expect(screen.getByText('Login page')).toBeTruthy())
  })

  it('redirects an unverified email/password user to /verify-email', async () => {
    mockCurrentUser = {
      emailVerified: false,
      providerData: [{ providerId: 'password' }],
    }
    renderGuarded()
    await waitFor(() => expect(screen.getByText('Verify email page')).toBeTruthy())
  })

  it('lets an unverified Google user through without redirecting to /verify-email', async () => {
    mockCurrentUser = {
      emailVerified: false,
      providerData: [{ providerId: 'google.com' }],
    }
    renderGuarded()
    await waitFor(() => expect(screen.getByText('Protected content')).toBeTruthy())
  })

  it('lets a verified email/password user through', async () => {
    mockCurrentUser = {
      emailVerified: true,
      providerData: [{ providerId: 'password' }],
    }
    renderGuarded()
    await waitFor(() => expect(screen.getByText('Protected content')).toBeTruthy())
  })
})
