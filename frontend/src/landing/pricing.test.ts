import { describe, expect, it } from 'vitest'

import { formatMonthlyPrice, PRICING_TIERS } from './pricing'

describe('formatMonthlyPrice', () => {
  it('renders zero as Free', () => {
    expect(formatMonthlyPrice(0)).toBe('Free')
  })

  it('renders whole-dollar prices without cents', () => {
    expect(formatMonthlyPrice(5)).toBe('$5')
    expect(formatMonthlyPrice(8)).toBe('$8')
  })

  // The Phase 8 flip hazard this formatter exists for: a fractional price
  // rendered via bare string interpolation would ship "$7.5".
  it('renders fractional prices with two decimal places', () => {
    expect(formatMonthlyPrice(7.5)).toBe('$7.50')
    expect(formatMonthlyPrice(5.99)).toBe('$5.99')
  })
})

describe('PRICING_TIERS data invariants', () => {
  // The discriminated union enforces price/cta pairing at compile time;
  // these pin the runtime content contracts copy edits could still break.
  it('keeps exactly one available tier while billing does not exist', () => {
    expect(PRICING_TIERS.filter((tier) => tier.available)).toHaveLength(1)
  })

  it('gives every tier a non-empty feature list and unique features', () => {
    for (const tier of PRICING_TIERS) {
      expect(tier.features.length).toBeGreaterThan(0)
      expect(new Set(tier.features).size).toBe(tier.features.length)
    }
  })

  it('routes every available CTA inside the app', () => {
    for (const tier of PRICING_TIERS) {
      if (tier.available) {
        expect(tier.cta.to.startsWith('/')).toBe(true)
      }
    }
  })
})
