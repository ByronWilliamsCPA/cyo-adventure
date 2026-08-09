import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getOrCreateDeviceId } from './deviceId'

describe('getOrCreateDeviceId', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('mints and persists a fresh id on first call', () => {
    const id = getOrCreateDeviceId()
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    expect(localStorage.getItem('cyo_device_id')).toBe(id)
  })

  it('returns the same id on every subsequent call', () => {
    const first = getOrCreateDeviceId()
    const second = getOrCreateDeviceId()
    expect(second).toBe(first)
  })

  it('reuses an id already in localStorage rather than minting a new one', () => {
    localStorage.setItem('cyo_device_id', 'existing-id')
    expect(getOrCreateDeviceId()).toBe('existing-id')
  })

  it('falls back to an ephemeral id when localStorage throws', () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError')
    })
    try {
      expect(() => getOrCreateDeviceId()).not.toThrow()
      expect(getOrCreateDeviceId()).toMatch(/^[0-9a-f-]{36}$/i)
    } finally {
      getItemSpy.mockRestore()
    }
  })
})
