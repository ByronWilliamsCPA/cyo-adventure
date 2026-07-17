import { beforeEach, describe, expect, it, vi } from 'vitest'

import { hasToasted, markSeen, readSeenRecord, recordToasted } from './notificationSeenStore'

beforeEach(() => {
  localStorage.clear()
})

describe('readSeenRecord', () => {
  it('returns the empty record when nothing is stored', () => {
    expect(readSeenRecord('guardian-1')).toEqual({ lastSeenAt: null, toastedIds: [] })
  })

  it('returns the empty record for a corrupted value instead of throwing', () => {
    localStorage.setItem('cyo:notifications:seen:guardian-1', 'not json{{{')
    expect(readSeenRecord('guardian-1')).toEqual({ lastSeenAt: null, toastedIds: [] })
  })

  it('returns the empty record for a value missing the expected shape', () => {
    localStorage.setItem('cyo:notifications:seen:guardian-1', JSON.stringify({ foo: 'bar' }))
    expect(readSeenRecord('guardian-1')).toEqual({ lastSeenAt: null, toastedIds: [] })
  })

  it('degrades to the empty record when localStorage.getItem throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    expect(readSeenRecord('guardian-1')).toEqual({ lastSeenAt: null, toastedIds: [] })
    spy.mockRestore()
  })

  it('keeps separate records per principal', () => {
    markSeen('guardian-1', '2026-07-15T00:00:00Z')
    expect(readSeenRecord('guardian-2')).toEqual({ lastSeenAt: null, toastedIds: [] })
    expect(readSeenRecord('guardian-1').lastSeenAt).toBe('2026-07-15T00:00:00Z')
  })
})

describe('markSeen', () => {
  it('stores the newest occurred_at as lastSeenAt', () => {
    const record = markSeen('guardian-1', '2026-07-15T12:00:00Z')
    expect(record.lastSeenAt).toBe('2026-07-15T12:00:00Z')
    expect(readSeenRecord('guardian-1').lastSeenAt).toBe('2026-07-15T12:00:00Z')
  })

  it('leaves lastSeenAt unchanged when the newest value is null (an empty panel)', () => {
    markSeen('guardian-1', '2026-07-15T12:00:00Z')
    const record = markSeen('guardian-1', null)
    expect(record.lastSeenAt).toBe('2026-07-15T12:00:00Z')
  })

  it('preserves toastedIds already recorded', () => {
    recordToasted('guardian-1', 'evt-1')
    const record = markSeen('guardian-1', '2026-07-15T12:00:00Z')
    expect(record.toastedIds).toEqual(['evt-1'])
  })
})

describe('hasToasted / recordToasted', () => {
  it('reports false before an id is recorded, true after', () => {
    expect(hasToasted('guardian-1', 'evt-1')).toBe(false)
    recordToasted('guardian-1', 'evt-1')
    expect(hasToasted('guardian-1', 'evt-1')).toBe(true)
  })

  it('does not duplicate an id already recorded', () => {
    recordToasted('guardian-1', 'evt-1')
    const record = recordToasted('guardian-1', 'evt-1')
    expect(record.toastedIds).toEqual(['evt-1'])
  })

  it('caps the stored id list so it cannot grow without bound', () => {
    for (let i = 0; i < 105; i += 1) {
      recordToasted('guardian-1', `evt-${i}`)
    }
    const record = readSeenRecord('guardian-1')
    expect(record.toastedIds).toHaveLength(100)
    // The oldest ids fall off the front; the most recent survive.
    expect(record.toastedIds).toContain('evt-104')
    expect(record.toastedIds).not.toContain('evt-0')
  })
})
