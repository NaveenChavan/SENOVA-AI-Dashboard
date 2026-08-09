import { describe, it, expect } from 'vitest'
import { checkPasswordStrength, isValidEmail, displayIdentifier } from '../utils/authValidation'

describe('checkPasswordStrength', () => {
  it('rejects a password missing every rule', () => {
    const { valid, reasons } = checkPasswordStrength('')
    expect(valid).toBe(false)
    expect(reasons).toContain('At least 8 characters')
    expect(reasons).toContain('One lowercase letter')
    expect(reasons).toContain('One uppercase letter')
    expect(reasons).toContain('One number')
  })

  it('rejects a password missing a digit', () => {
    const { valid, reasons } = checkPasswordStrength('Abcdefgh')
    expect(valid).toBe(false)
    expect(reasons).toEqual(['One number'])
  })

  it('rejects a password under the length minimum even if otherwise varied', () => {
    const { valid, reasons } = checkPasswordStrength('Ab1')
    expect(valid).toBe(false)
    expect(reasons).toContain('At least 8 characters')
  })

  it('accepts a password meeting every rule', () => {
    const { valid, reasons } = checkPasswordStrength('Str0ngPass')
    expect(valid).toBe(true)
    expect(reasons).toEqual([])
  })
})

describe('isValidEmail', () => {
  it('accepts a well-formed email', () => {
    expect(isValidEmail('user@example.com')).toBe(true)
  })

  it('rejects strings without an @ or domain', () => {
    expect(isValidEmail('not-an-email')).toBe(false)
    expect(isValidEmail('user@')).toBe(false)
    expect(isValidEmail('')).toBe(false)
  })
})

describe('displayIdentifier', () => {
  it('returns the email for a signed-in user', () => {
    expect(displayIdentifier({ email: 'user@example.com' })).toBe('user@example.com')
  })

  it('falls back to a neutral label when there is no email', () => {
    expect(displayIdentifier({})).toBe('Signed in')
  })

  it('returns a neutral label for a null user', () => {
    expect(displayIdentifier(null)).toBe('')
  })
})
