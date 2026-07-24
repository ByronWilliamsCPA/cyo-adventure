import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestPersistentStorage } from './db'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('requestPersistentStorage', () => {
  it('returns false when the Storage API is unavailable', async () => {
    vi.stubGlobal('navigator', {})
    await expect(requestPersistentStorage()).resolves.toBe(false)
  })

  it('does not re-request when already persisted', async () => {
    const persist = vi.fn()
    vi.stubGlobal('navigator', {
      storage: { persisted: vi.fn().mockResolvedValue(true), persist },
    })
    await expect(requestPersistentStorage()).resolves.toBe(true)
    expect(persist).not.toHaveBeenCalled()
  })

  it('requests persistence when not yet persisted', async () => {
    vi.stubGlobal('navigator', {
      storage: {
        persisted: vi.fn().mockResolvedValue(false),
        persist: vi.fn().mockResolvedValue(true),
      },
    })
    await expect(requestPersistentStorage()).resolves.toBe(true)
  })
})
