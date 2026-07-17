import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getReadAloudPreference, setReadAloudPreference } from './readAloudPreference'

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('readAloudPreference', () => {
  it('returns false for a profile with nothing stored', () => {
    expect(getReadAloudPreference('p1')).toBe(false)
  })

  it('round-trips a true value for the matching profile', () => {
    setReadAloudPreference('p1', true)
    expect(getReadAloudPreference('p1')).toBe(true)
  })

  it('round-trips a false value for the matching profile', () => {
    setReadAloudPreference('p1', true)
    setReadAloudPreference('p1', false)
    expect(getReadAloudPreference('p1')).toBe(false)
  })

  it('returns false for a DIFFERENT profile than the one stored', () => {
    setReadAloudPreference('p1', true)
    expect(getReadAloudPreference('p2')).toBe(false)
  })

  it('overwrites the previous profile on a new pick, not merging', () => {
    setReadAloudPreference('p1', true)
    setReadAloudPreference('p2', false)
    expect(getReadAloudPreference('p1')).toBe(false)
    expect(getReadAloudPreference('p2')).toBe(false)
  })

  it('treats a corrupt stored blob as no preference', () => {
    localStorage.setItem('child_session_read_aloud', '{not json')
    expect(getReadAloudPreference('p1')).toBe(false)
  })

  it('treats a well-formed but wrong-shaped stored value as no preference', () => {
    localStorage.setItem('child_session_read_aloud', JSON.stringify({ foo: 'bar' }))
    expect(getReadAloudPreference('p1')).toBe(false)
  })

  it('does not throw when localStorage.setItem throws (private/locked-down browsing)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    expect(() => setReadAloudPreference('p1', true)).not.toThrow()
  })

  it('does not throw and returns false when localStorage.getItem throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    expect(() => getReadAloudPreference('p1')).not.toThrow()
    expect(getReadAloudPreference('p1')).toBe(false)
  })
})
