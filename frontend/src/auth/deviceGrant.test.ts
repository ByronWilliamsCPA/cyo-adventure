import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle, getDeviceGrantMirror } from '../offline/db'
import {
  clearDeviceGrant,
  getDeviceGrant,
  getValidDeviceGrant,
  hasValidDeviceGrant,
  hydrateDeviceGrant,
  isDeviceGrantAuthRoute,
  isDeviceGrantExpired,
  setDeviceGrant,
} from './deviceGrant'

const GRANT_KEY = 'device_grant'

const grant = {
  token: 'tok-1',
  expiresAt: '2026-07-11T12:00:00Z',
  familyId: 'fam-1',
  id: 'grant-1',
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  localStorage.clear()
})

describe('setDeviceGrant / getDeviceGrant', () => {
  it('round-trips a stored grant through a single JSON-blob key', () => {
    setDeviceGrant(grant)
    expect(localStorage.getItem(GRANT_KEY)).not.toBeNull()
    expect(getDeviceGrant()).toEqual(grant)
  })

  it('returns null when nothing is stored', () => {
    expect(getDeviceGrant()).toBeNull()
  })

  it('returns null when the stored blob is corrupt (unparseable)', () => {
    localStorage.setItem(GRANT_KEY, '{not-json')
    expect(getDeviceGrant()).toBeNull()
  })

  it('returns null when the stored blob is missing a field', () => {
    localStorage.setItem(GRANT_KEY, JSON.stringify({ token: 'tok-1', familyId: 'fam-1' }))
    expect(getDeviceGrant()).toBeNull()
  })

  it('storage failure on read is swallowed as no grant', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(getDeviceGrant()).toBeNull()
    spy.mockRestore()
  })

  it('storage failure on write is swallowed', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() => setDeviceGrant(grant)).not.toThrow()
    spy.mockRestore()
  })

  it('mirrors a set grant to IndexedDB', async () => {
    setDeviceGrant(grant)
    // The mirror write is fire-and-forget; give its microtask a tick.
    await vi.waitFor(async () => {
      const mirrored = await getDeviceGrantMirror()
      expect(mirrored).toEqual(grant)
    })
  })
})

describe('clearDeviceGrant', () => {
  it('removes the blob key', () => {
    setDeviceGrant(grant)
    clearDeviceGrant()
    expect(getDeviceGrant()).toBeNull()
    expect(localStorage.getItem(GRANT_KEY)).toBeNull()
  })

  it('storage failure on clear is swallowed', () => {
    const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() => clearDeviceGrant()).not.toThrow()
    spy.mockRestore()
  })

  it('clears the IndexedDB mirror too', async () => {
    setDeviceGrant(grant)
    await vi.waitFor(async () => {
      expect(await getDeviceGrantMirror()).toEqual(grant)
    })
    clearDeviceGrant()
    await vi.waitFor(async () => {
      expect(await getDeviceGrantMirror()).toBeUndefined()
    })
  })
})

describe('isDeviceGrantExpired', () => {
  it('is false strictly before the expiry instant', () => {
    expect(isDeviceGrantExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T11:59:59.999Z'))).toBe(
      false
    )
  })

  it('is true exactly at the expiry instant (inclusive boundary)', () => {
    expect(isDeviceGrantExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T12:00:00Z'))).toBe(
      true
    )
  })

  it('is true after the expiry instant', () => {
    expect(
      isDeviceGrantExpired('2026-07-11T12:00:00Z', new Date('2026-07-11T12:00:00.001Z'))
    ).toBe(true)
  })

  it('treats an unparseable timestamp as expired (fail closed)', () => {
    expect(isDeviceGrantExpired('not-a-date')).toBe(true)
  })
})

describe('getValidDeviceGrant / hasValidDeviceGrant', () => {
  it('returns the grant when not expired', () => {
    setDeviceGrant(grant)
    const now = new Date('2026-07-11T11:00:00Z')
    expect(getValidDeviceGrant(now)).toEqual(grant)
    expect(hasValidDeviceGrant(now)).toBe(true)
  })

  it('returns null and clears storage when expired', () => {
    setDeviceGrant(grant)
    const now = new Date('2026-07-11T13:00:00Z')
    expect(getValidDeviceGrant(now)).toBeNull()
    expect(getDeviceGrant()).toBeNull()
    expect(hasValidDeviceGrant(now)).toBe(false)
  })

  it('returns null/false when nothing is stored', () => {
    expect(getValidDeviceGrant()).toBeNull()
    expect(hasValidDeviceGrant()).toBe(false)
  })
})

describe('hydrateDeviceGrant', () => {
  it('returns the localStorage grant without touching IndexedDB when it is already valid', async () => {
    setDeviceGrant(grant)
    const now = new Date('2026-07-11T11:00:00Z')
    expect(await hydrateDeviceGrant(now)).toEqual(grant)
  })

  it('falls back to the IndexedDB mirror when localStorage is cleared', async () => {
    setDeviceGrant(grant)
    await vi.waitFor(async () => {
      expect(await getDeviceGrantMirror()).toEqual(grant)
    })
    // Simulate a localStorage clear (private mode eviction, user clears site
    // data) that leaves the IndexedDB mirror intact.
    localStorage.removeItem(GRANT_KEY)
    expect(getDeviceGrant()).toBeNull()

    const now = new Date('2026-07-11T11:00:00Z')
    const recovered = await hydrateDeviceGrant(now)

    expect(recovered).toEqual(grant)
    // The synchronous path is repaired: a later sync check no longer needs
    // to touch IndexedDB.
    expect(getDeviceGrant()).toEqual(grant)
  })

  it('drops an expired mirror entry and returns null', async () => {
    setDeviceGrant(grant)
    await vi.waitFor(async () => {
      expect(await getDeviceGrantMirror()).toEqual(grant)
    })
    localStorage.removeItem(GRANT_KEY)

    const now = new Date('2026-07-11T13:00:00Z')
    expect(await hydrateDeviceGrant(now)).toBeNull()
    expect(await getDeviceGrantMirror()).toBeUndefined()
  })

  it('returns null when neither store has anything', async () => {
    expect(await hydrateDeviceGrant()).toBeNull()
  })
})

describe('isDeviceGrantAuthRoute', () => {
  it('matches the profile picker path', () => {
    expect(isDeviceGrantAuthRoute('/kids')).toBe(true)
  })

  it('excludes a library route', () => {
    expect(isDeviceGrantAuthRoute('/library/p1')).toBe(false)
  })

  it('excludes a guardian route', () => {
    expect(isDeviceGrantAuthRoute('/guardian')).toBe(false)
  })
})

afterEach(() => {
  localStorage.clear()
})
