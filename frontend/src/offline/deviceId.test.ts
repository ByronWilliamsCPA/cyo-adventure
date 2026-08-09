import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'cyo_device_id'

/**
 * The in-memory fallback lives in module-scope state (`sessionDeviceId` in
 * deviceId.ts), so a test that needs to observe it in isolation must import a
 * fresh module instance rather than the one a prior test in this file already
 * mutated. `vi.resetModules()` plus a dynamic `import()` gets a clean module
 * every time; a static top-level import would share one mutable module
 * across every test in this file.
 */
async function freshGetOrCreateDeviceId() {
  vi.resetModules()
  const mod = await import('./deviceId')
  return mod.getOrCreateDeviceId
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('getOrCreateDeviceId', () => {
  it('returns the persisted id from a working localStorage on the second call', async () => {
    const getOrCreateDeviceId = await freshGetOrCreateDeviceId()
    const first = getOrCreateDeviceId()
    const second = getOrCreateDeviceId()
    expect(second).toBe(first)
    expect(first).toMatch(/^[0-9a-f-]{36}$/i)
  })

  it('writes the minted id to localStorage when the write succeeds', async () => {
    const getOrCreateDeviceId = await freshGetOrCreateDeviceId()
    const id = getOrCreateDeviceId()
    expect(localStorage.getItem(STORAGE_KEY)).toBe(id)
  })

  it('still returns an id, instead of throwing, when localStorage.getItem throws', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('storage blocked', 'SecurityError')
    })
    const getOrCreateDeviceId = await freshGetOrCreateDeviceId()
    let id = ''
    expect(() => {
      id = getOrCreateDeviceId()
    }).not.toThrow()
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
  })

  it('still returns a stable id, from the in-memory fallback, when localStorage.setItem throws', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError')
    })
    const getOrCreateDeviceId = await freshGetOrCreateDeviceId()
    const first = getOrCreateDeviceId()
    const second = getOrCreateDeviceId()
    // Same id across both calls within this module's lifetime: the point of
    // the module-scoped fallback is that a session does not mint a new id on
    // every call just because storage refuses every write.
    expect(second).toBe(first)
    // The write always throws, so this can only be true if the stability
    // above came from the in-memory fallback, never from a successful
    // localStorage read-back.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
