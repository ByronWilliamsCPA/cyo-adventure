import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  clearChildSession,
  getChildSession,
  getValidChildSession,
  isExpired,
  isKidTokenRoute,
  routeProfileId,
  setChildSession,
} from './childSession'

const SESSION_KEY = 'child_session'
const LEGACY_KEYS = ['child_session_token', 'child_session_expires_at', 'child_session_profile_id']

afterEach(() => {
  localStorage.clear()
})

describe('setChildSession / getChildSession', () => {
  it('round-trips a stored session through a single JSON-blob key', () => {
    setChildSession({ token: 'tok-1', expiresAt: '2026-07-11T12:00:00Z', profileId: 'p1' })
    // One key holds the whole session; no non-atomic triple to half-write.
    expect(localStorage.getItem(SESSION_KEY)).not.toBeNull()
    expect(getChildSession()).toEqual({
      token: 'tok-1',
      expiresAt: '2026-07-11T12:00:00Z',
      profileId: 'p1',
    })
  })

  it('returns null when nothing is stored', () => {
    expect(getChildSession()).toBeNull()
  })

  it('treats a legacy pre-blob triple as absent (no cross-version confusion)', () => {
    // A complete triple written by the old three-key implementation must not
    // be revived as a session under the blob reader; only the blob key counts.
    for (const key of LEGACY_KEYS) {
      localStorage.setItem(key, 'p1')
    }
    expect(getChildSession()).toBeNull()
  })

  it('returns null when the stored blob is corrupt (unparseable)', () => {
    localStorage.setItem(SESSION_KEY, '{not-json')
    expect(getChildSession()).toBeNull()
  })

  it('returns null when the stored blob is missing a field', () => {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ token: 'tok-1', profileId: 'p1' }))
    expect(getChildSession()).toBeNull()
  })

  it('storage failure on read is swallowed as no session', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(getChildSession()).toBeNull()
    spy.mockRestore()
  })

  it('storage failure on write is swallowed', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() =>
      setChildSession({ token: 'tok-1', expiresAt: '2026-07-11T12:00:00Z', profileId: 'p1' })
    ).not.toThrow()
    spy.mockRestore()
  })
})

describe('clearChildSession', () => {
  it('removes the blob key and any lingering legacy triple', () => {
    setChildSession({ token: 'tok-1', expiresAt: '2026-07-11T12:00:00Z', profileId: 'p1' })
    // Plant a stale legacy triple too, to prove clear sweeps both shapes.
    for (const key of LEGACY_KEYS) {
      localStorage.setItem(key, 'stale')
    }
    clearChildSession()
    expect(getChildSession()).toBeNull()
    expect(localStorage.getItem(SESSION_KEY)).toBeNull()
    for (const key of LEGACY_KEYS) {
      expect(localStorage.getItem(key)).toBeNull()
    }
  })

  it('storage failure on clear is swallowed', () => {
    const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() => clearChildSession()).not.toThrow()
    spy.mockRestore()
  })
})

describe('isExpired', () => {
  it('is false strictly before the expiry instant', () => {
    expect(isExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T11:59:59.999Z'))).toBe(false)
  })

  it('is true exactly at the expiry instant (inclusive boundary)', () => {
    expect(isExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T12:00:00Z'))).toBe(true)
  })

  it('is true after the expiry instant', () => {
    expect(isExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T12:00:00.001Z'))).toBe(true)
  })

  it('treats an unparseable timestamp as expired (fail closed)', () => {
    expect(isExpired('not-a-date')).toBe(true)
  })
})

describe('getValidChildSession', () => {
  it('returns the session when not expired', () => {
    setChildSession({ token: 'tok-1', expiresAt: '2026-07-11T12:00:00Z', profileId: 'p1' })
    const now = new Date('2026-07-11T11:00:00Z')
    expect(getValidChildSession(now)).toEqual({
      token: 'tok-1',
      expiresAt: '2026-07-11T12:00:00Z',
      profileId: 'p1',
    })
  })

  it('returns null and clears storage when expired', () => {
    setChildSession({ token: 'tok-1', expiresAt: '2026-07-11T12:00:00Z', profileId: 'p1' })
    const now = new Date('2026-07-11T13:00:00Z')
    expect(getValidChildSession(now)).toBeNull()
    expect(getChildSession()).toBeNull()
  })

  it('returns null when nothing is stored', () => {
    expect(getValidChildSession()).toBeNull()
  })
})

describe('isKidTokenRoute', () => {
  it('matches a library route', () => {
    expect(isKidTokenRoute('/library/p1')).toBe(true)
  })

  it('matches a reader route', () => {
    expect(isKidTokenRoute('/read/p1/story-1/3')).toBe(true)
  })

  // The picker deliberately prefers the guardian token even when a stale
  // child session exists; see the #ASSUME note on isKidTokenRoute itself for
  // why (multi-child "Switch reader" flow needs every family profile listed).
  it('excludes the profile picker path', () => {
    expect(isKidTokenRoute('/kids')).toBe(false)
  })

  it('excludes the guardian console', () => {
    expect(isKidTokenRoute('/guardian')).toBe(false)
  })

  it('excludes the landing page', () => {
    expect(isKidTokenRoute('/')).toBe(false)
  })
})

describe('routeProfileId', () => {
  it('extracts the profile id from a library route', () => {
    expect(routeProfileId('/library/p1')).toBe('p1')
  })

  it('extracts the profile id from a reader route', () => {
    expect(routeProfileId('/read/p1/story-1/3')).toBe('p1')
  })

  it('returns null for the picker path', () => {
    expect(routeProfileId('/kids')).toBeNull()
  })

  it('returns null for a guardian route', () => {
    expect(routeProfileId('/guardian/console')).toBeNull()
  })

  it('returns null for a library route with no profile segment', () => {
    expect(routeProfileId('/library')).toBeNull()
  })
})
