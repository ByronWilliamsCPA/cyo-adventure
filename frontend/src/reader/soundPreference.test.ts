import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEVICE_PREFERENCE_KEY,
  getSoundMutedPreference,
  setSoundMutedPreference,
} from './soundPreference'

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('soundPreference', () => {
  it('returns undefined for a key with nothing stored, distinct from an explicit false', () => {
    expect(getSoundMutedPreference('p1')).toBeUndefined()
  })

  it('round-trips a true value for the matching key', () => {
    setSoundMutedPreference('p1', true)
    expect(getSoundMutedPreference('p1')).toBe(true)
  })

  it('round-trips a false value for the matching key', () => {
    setSoundMutedPreference('p1', true)
    setSoundMutedPreference('p1', false)
    expect(getSoundMutedPreference('p1')).toBe(false)
  })

  it('returns undefined for a DIFFERENT key than the one stored', () => {
    setSoundMutedPreference('p1', true)
    expect(getSoundMutedPreference('p2')).toBeUndefined()
  })

  it('overwrites the previous key on a new choice, not merging', () => {
    setSoundMutedPreference('p1', true)
    setSoundMutedPreference(DEVICE_PREFERENCE_KEY, false)
    expect(getSoundMutedPreference('p1')).toBeUndefined()
    expect(getSoundMutedPreference(DEVICE_PREFERENCE_KEY)).toBe(false)
  })

  it('treats a corrupt stored blob as no preference', () => {
    localStorage.setItem('reader_sound_muted', '{not json')
    expect(getSoundMutedPreference('p1')).toBeUndefined()
  })

  it('treats a well-formed but wrong-shaped stored value as no preference', () => {
    localStorage.setItem('reader_sound_muted', JSON.stringify({ foo: 'bar' }))
    expect(getSoundMutedPreference('p1')).toBeUndefined()
  })

  it('does not throw when localStorage.setItem throws (private/locked-down browsing)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    expect(() => setSoundMutedPreference('p1', true)).not.toThrow()
  })

  it('does not throw and returns undefined when localStorage.getItem throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    expect(() => getSoundMutedPreference('p1')).not.toThrow()
    expect(getSoundMutedPreference('p1')).toBeUndefined()
  })
})
