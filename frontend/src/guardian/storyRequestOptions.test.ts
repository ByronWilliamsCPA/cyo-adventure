import { describe, expect, it } from 'vitest'
import {
  AGE_BAND_LABELS,
  ageBandLabel,
  lengthLabel,
  narrativeStyleLabel,
} from './storyRequestOptions'

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

describe('lengthLabel', () => {
  it('humanizes known lengths and falls back to the raw token', () => {
    expect(lengthLabel('short')).toMatch(/short/i)
    expect(lengthLabel('long')).toMatch(/long/i)
    expect(lengthLabel('whatever')).toBe('whatever')
  })
})

describe('narrativeStyleLabel', () => {
  it('humanizes known styles and falls back to the raw token', () => {
    expect(narrativeStyleLabel('prose')).toMatch(/prose/i)
    expect(narrativeStyleLabel('gamebook')).toMatch(/pick-a-path/i)
    expect(narrativeStyleLabel('mystery')).toBe('mystery')
  })
})
