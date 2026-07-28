import { describe, expect, it } from 'vitest'
import { wordRangeAtIndex } from './readAloudHighlight'

describe('wordRangeAtIndex', () => {
  it('returns the first word when charIndex is 0', () => {
    expect(wordRangeAtIndex('Once upon a time.', 0)).toEqual({ start: 0, end: 4 })
  })

  it('returns the word starting at a mid-string charIndex', () => {
    const text = 'Once upon a time.'
    expect(wordRangeAtIndex(text, 5)).toEqual({ start: 5, end: 9 }) // "upon"
    expect(wordRangeAtIndex(text, 12)).toEqual({ start: 12, end: 17 }) // "time."
  })

  it('walks forward past whitespace when charIndex lands inside it', () => {
    // Some engines report the boundary a character early, landing on the
    // space before the word rather than its first letter.
    expect(wordRangeAtIndex('Once upon a time.', 4)).toEqual({ start: 5, end: 9 })
  })

  it('returns null when charIndex is negative', () => {
    expect(wordRangeAtIndex('Once upon a time.', -1)).toBeNull()
  })

  it('returns null when charIndex is at or past the text length', () => {
    const text = 'Once upon a time.'
    expect(wordRangeAtIndex(text, text.length)).toBeNull()
    expect(wordRangeAtIndex(text, text.length + 10)).toBeNull()
  })

  it('returns null when charIndex lands in trailing whitespace with no word after it', () => {
    expect(wordRangeAtIndex('Once upon a time.   ', 18)).toBeNull()
  })

  it('returns null for a non-finite charIndex', () => {
    expect(wordRangeAtIndex('Once upon a time.', Number.NaN)).toBeNull()
  })

  it('handles a single-word text', () => {
    expect(wordRangeAtIndex('Hello', 0)).toEqual({ start: 0, end: 5 })
  })

  it('handles multi-paragraph text, finding a word past a blank line', () => {
    const text = 'First paragraph.\n\nSecond paragraph.'
    const secondWordStart = text.indexOf('Second')
    expect(wordRangeAtIndex(text, secondWordStart)).toEqual({
      start: secondWordStart,
      end: secondWordStart + 'Second'.length,
    })
  })
})
