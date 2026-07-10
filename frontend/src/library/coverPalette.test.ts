import { describe, expect, it } from 'vitest'

import { coverGradient } from './coverPalette'

// coverPalette.ts does not export COVER_TOKENS, only the coverGradient
// function and the CoverToken type, so the token list is duplicated here
// (test-only) to assert membership without touching production source.
const COVER_TOKENS = [
  'var(--cover-forest)',
  'var(--cover-lagoon)',
  'var(--cover-berry)',
  'var(--cover-plum)',
  'var(--cover-sunset)',
  'var(--cover-teal)',
]

describe('coverGradient', () => {
  it('returns the same token for the same title on repeated calls', () => {
    const first = coverGradient('The Lantern Cave')
    const second = coverGradient('The Lantern Cave')
    expect(first).toBe(second)
  })

  it('returns a known, fixed token for a known title (pins the hash algorithm)', () => {
    expect(coverGradient('The Lantern Cave')).toBe('var(--cover-berry)')
  })

  it('returns a member of COVER_TOKENS for a variety of titles', () => {
    const titles = [
      'Zephyr',
      '🐉 Dragon Quest',
      'A',
      '',
      'x'.repeat(500),
      "The Bramblewood Mystery: A Very Long Subtitle That Keeps On Going",
    ]
    for (const title of titles) {
      expect(COVER_TOKENS).toContain(coverGradient(title))
    }
  })

  it('does not throw for an empty string', () => {
    expect(() => coverGradient('')).not.toThrow()
  })
})
