import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { hasGuardianSession } from './guardianToken'
import { TOKEN_STORAGE_KEY } from './tokenStorageKey'

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

  it('reads the shared TOKEN_STORAGE_KEY, so the kid and guardian halves cannot drift', () => {
    // Guards the ADR-014 split: guardianToken.ts must key off the SAME constant
    // AuthContext/useApi persist under, without importing them (which would pull
    // Supabase into the kid chunk). Both now import ./tokenStorageKey, so a
    // token written under that shared key is what hasGuardianSession detects.
    expect(TOKEN_STORAGE_KEY).toBe('auth_token')
    localStorage.setItem(TOKEN_STORAGE_KEY, 'guardian-jwt')
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
    // Spy on Storage.prototype, not the window.localStorage instance: jsdom's
    // getItem lives on the prototype, so an instance-level spy never shadows
    // the method the code calls, the mock silently no-ops, and the catch path
    // (guardianToken.ts) goes unexercised. This matches deviceGrant.test.ts /
    // childSession.test.ts, which spy the prototype to genuinely throw.
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: storage disabled')
    })
    expect(hasGuardianSession()).toBe(false)
  })
})
