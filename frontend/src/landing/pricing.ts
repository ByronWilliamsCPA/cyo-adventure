/**
 * Pricing tiers for the landing page's funnel section.
 *
 * Subscriptions are NOT configured yet: R1 is a free early-access release, and
 * the paid Family tier arrives with Track 2 Phase 8 (PROJECT-PLAN.md, ADR-008:
 * tiered family subscription behind Apple In-App Purchase, price decided
 * pre-launch). This module exists so the homepage is subscription-READY
 * without pretending to sell anything today: LandingPage renders a card per
 * AVAILABLE tier and folds unavailable tiers into a one-line futures note, so
 * flipping `available` (plus a price and CTA) makes the paid card appear with
 * no layout work.
 *
 * The tier type is a discriminated union on `available` so that flip really
 * is a safe data change: an available tier MUST carry a price and a CTA, an
 * unavailable one MUST NOT, and the chip text and card styling derive from
 * the same discriminant. (The first version of this file encoded
 * availability three times with nothing keeping the copies in sync.)
 *
 * #CRITICAL: payment/financial: nothing in this file may imply a charge exists
 * today. There is no billing backend, so a CTA that looks like a purchase
 * would be a dark pattern aimed at parents. Free-tier CTAs route to guardian
 * sign-in (the self-signup path); an unavailable tier renders no actionable
 * control at all (type-enforced: `cta: null`). Feature copy must also match
 * the shipped product: the free tier states the real request quota (10/month
 * per family, `core/config.py::default_monthly_story_quota`) and lists
 * read-aloud, which shipped free in Phase 4b and must never be advertised as
 * a future paid feature while families already have it.
 * #VERIFY: LandingPage.test.tsx "pricing" cases assert the funnel renders no
 * purchase control, the Explorer CTA points at guardian login, and the quota
 * line is present; pricing.test.ts pins formatMonthlyPrice (invalid input
 * throws; a fractional price renders "$7.50", never "$7.5") and the
 * no-billing-yet data invariants (every available tier is free and routes to
 * guardian login).
 */
import { GUARDIAN_LOGIN_PATH } from '../routes'

interface PricingTierBase {
  id: 'explorer' | 'family'
  name: string
  /** Short line under the price (billing cadence, launch note). */
  priceNote: string
  /** One-sentence positioning for the tier. */
  tagline: string
  features: string[]
}

export type PricingTier = PricingTierBase &
  (
    | {
        /** Actable today: must carry a real price and a CTA. */
        available: true
        /** Monthly USD price; 0 renders as "Free". */
        priceMonthlyUsd: number
        cta: { label: string; to: string }
      }
    | {
        /** Not sold yet: no price, and no actionable control at all. */
        available: false
        priceMonthlyUsd: null
        cta: null
      }
  )

/**
 * Render a monthly price for a tier card. 0 is "Free"; anything else is
 * USD currency-formatted (so 7.5 renders "$7.50", never "$7.5"). Invalid
 * money (NaN, Infinity, negatives) throws instead of rendering "$NaN" on a
 * public pricing card. Currency display will need revisiting when Phase 8
 * lands, since Apple IAP prices per storefront; keeping the formatting here
 * means that change stays in this module too.
 */
export function formatMonthlyPrice(priceMonthlyUsd: number): string {
  if (!Number.isFinite(priceMonthlyUsd) || priceMonthlyUsd < 0) {
    throw new Error(`formatMonthlyPrice: not a renderable price: ${priceMonthlyUsd}`)
  }
  if (priceMonthlyUsd === 0) return 'Free'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: Number.isInteger(priceMonthlyUsd) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(priceMonthlyUsd)
}

export const PRICING_TIERS: readonly PricingTier[] = [
  {
    id: 'explorer',
    name: 'Explorer',
    priceMonthlyUsd: 0,
    priceNote: 'free during early access',
    tagline: 'Everything a family needs, from your first approved story on.',
    features: [
      'Up to 10 new story requests a month',
      'A profile and shelf for each reader',
      'Read-aloud narration',
      'Offline reading on your devices',
      'Grown-up approval on every book',
      'Every safety feature, always',
    ],
    available: true,
    cta: { label: 'Start free', to: GUARDIAN_LOGIN_PATH },
  },
  {
    id: 'family',
    name: 'Family',
    priceMonthlyUsd: null,
    priceNote: 'pricing announced before launch',
    tagline: 'The full library and the works, when subscriptions open.',
    features: [
      'Everything in Explorer',
      'The full story catalog as it grows',
      'Unlimited story requests',
    ],
    available: false,
    cta: null,
  },
]
