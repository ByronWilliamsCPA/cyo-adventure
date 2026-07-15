import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { hasGuardianSession } from './guardianToken'

describe('hasGuardianSession', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('is true when a guardian bearer is stored under auth_token', () => {
    localStorage.setItem('auth_token', 'guardian-jwt')
    expect(hasGuardianSession()).toBe(true)
  })

  it('is false when no auth_token is present (device-grant-only kid device)', () => {
    expect(hasGuardianSession()).toBe(false)
  })

  it('is false for an empty-string token', () => {
    localStorage.setItem('auth_token', '')
    expect(hasGuardianSession()).toBe(false)
  })

  it('returns false instead of throwing when localStorage access throws', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: storage disabled')
    })
    expect(hasGuardianSession()).toBe(false)
  })
})
