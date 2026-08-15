import { describe, expect, it } from 'vitest'

import { GUARDIAN_LOGIN_PATH } from '../routes'
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

  // #VERIFY (pricing.ts #CRITICAL): invalid money must throw, never render.
  // Without the guard, NaN rendered "$NaN" and -5 rendered "-$5" on a public
  // pricing card.
  it('throws on money that must never reach a pricing card', () => {
    expect(() => formatMonthlyPrice(Number.NaN)).toThrow(/not a renderable price/)
    expect(() => formatMonthlyPrice(Number.POSITIVE_INFINITY)).toThrow(/not a renderable price/)
    expect(() => formatMonthlyPrice(-5)).toThrow(/not a renderable price/)
  })

  it('rounds sub-cent input to a whole cent (Intl behavior, pinned on purpose)', () => {
    expect(formatMonthlyPrice(0.005)).toBe('$0.01')
  })
})

describe('PRICING_TIERS data invariants', () => {
  // The safety property the module's #CRITICAL protects: while no billing
  // backend exists, nothing in this data may charge or look like it charges.
  // Stronger than a tier count: it fails if ANY available tier gains a
  // non-zero price or a CTA that leaves the self-signup path, not just if a
  // second tier appears.
  it('sells nothing while billing does not exist', () => {
    expect(PRICING_TIERS.some((tier) => tier.available)).toBe(true)
    for (const tier of PRICING_TIERS) {
      if (tier.available) {
        expect(tier.priceMonthlyUsd).toBe(0)
        expect(tier.cta.to).toBe(GUARDIAN_LOGIN_PATH)
      }
    }
  })

  it('gives every tier a non-empty feature list and unique features', () => {
    for (const tier of PRICING_TIERS) {
      expect(tier.features.length).toBeGreaterThan(0)
      expect(new Set(tier.features).size).toBe(tier.features.length)
    }
  })
})
