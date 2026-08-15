/**
 * Pricing tiers for the landing page's funnel section.
 *
 * Subscriptions are NOT configured yet: R1 is a free early-access release, and
 * the paid Family tier arrives with Track 2 Phase 8 (PROJECT-PLAN.md, ADR-008:
 * tiered family subscription behind Apple In-App Purchase, price decided
 * pre-launch). This module exists so the homepage is subscription-READY
 * without pretending to sell anything today.
 *
 * The tier type is a discriminated union on `available` so the Phase 8 flip
 * really is a safe data change: an available tier MUST carry a price and a
 * CTA, an unavailable one MUST NOT, and the chip text and card styling are
 * derived from the same discriminant in LandingPage.tsx. (The first version
 * of this file encoded availability three times, `available`/`status`/`cta`,
 * with nothing keeping them in sync; a partial flip would have shipped a
 * contradictory card while every test stayed green.)
 *
 * #CRITICAL: payment/financial: nothing in this file may imply a charge exists
 * today. There is no billing backend, so a CTA that looks like a purchase
 * would be a dark pattern aimed at parents. Free-tier CTAs route to guardian
 * sign-in (the self-signup path); an unavailable tier renders no actionable
 * control at all (type-enforced: `cta: null`). Feature copy must also match
 * enforced backend limits: the free tier's story-request line states the real
 * default quota (10/month per family, `core/config.py::
 * default_monthly_story_quota`) rather than hiding a cap a parent would
 * discover on day 11.
 * #VERIFY: LandingPage.test.tsx "pricing" cases assert the Family card
 * renders no link/button, the Explorer CTA points at guardian login, and the
 * quota line is present; pricing.test.ts pins formatMonthlyPrice (so a future
 * fractional price renders "$7.50", never "$7.5") and the tier-data
 * invariants.
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
 * USD currency-formatted (so 7.5 renders "$7.50", never "$7.5"). Currency
 * display will need revisiting when Phase 8 lands, since Apple IAP prices
 * per storefront; keeping the formatting here means that change stays in
 * this module too.
 */
export function formatMonthlyPrice(priceMonthlyUsd: number): string {
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
      'Read-aloud narration',
    ],
    available: false,
    cta: null,
  },
]
