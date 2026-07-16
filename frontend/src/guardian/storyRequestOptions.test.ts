import { describe, expect, it } from 'vitest'
import { AGE_BAND_LABELS, ageBandLabel } from './storyRequestOptions'

describe('ageBandLabel', () => {
  it('returns the human-readable label for a known band', () => {
    for (const [band, label] of Object.entries(AGE_BAND_LABELS)) {
      expect(ageBandLabel(band)).toBe(label)
    }
  })

  it('falls back to "Ages <value>" for an unknown band', () => {
    expect(ageBandLabel('99+')).toBe('Ages 99+')
  })
})
