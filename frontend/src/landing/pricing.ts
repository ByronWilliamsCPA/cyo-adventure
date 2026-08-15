/**
 * Pricing tiers for the landing page's funnel section.
 *
 * Subscriptions are NOT configured yet: R1 is a free early-access release, and
 * the paid Family tier arrives with Track 2 Phase 8 (PROJECT-PLAN.md, ADR-008:
 * tiered family subscription behind Apple In-App Purchase, price decided
 * pre-launch). This module exists so the homepage is subscription-READY
 * without pretending to sell anything today:
 *
 * - A tier with `priceMonthlyUsd: null` renders "Coming soon" and MUST NOT
 *   render an actionable purchase control; its card carries a status chip and
 *   an invitation line instead.
 * - When Phase 8 lands, flipping `available` and filling `priceMonthlyUsd`
 *   (and pointing `cta.to` at the real checkout/paywall route, which sits
 *   behind the parental gate per P8-06) is a data change here, not a layout
 *   change in LandingPage.tsx.
 *
 * #CRITICAL: payment/financial: nothing in this file may imply a charge exists
 * today. There is no billing backend, so a CTA that looks like a purchase
 * would be a dark pattern aimed at parents. Free-tier CTAs route to guardian
 * sign-in (the self-signup path); the unpriced tier renders no CTA at all.
 * #VERIFY: LandingPage.test.tsx "pricing" cases assert the Family card renders
 * no link/button and the Explorer CTA points at guardian login.
 */
import { GUARDIAN_LOGIN_PATH } from '../routes'

export interface PricingTier {
  id: 'explorer' | 'family'
  name: string
  /** Monthly USD price; null = not yet priced (rendered as "Coming soon"). */
  priceMonthlyUsd: number | null
  /** Short line under the price (billing cadence, launch note). */
  priceNote: string
  /** One-sentence positioning for the tier. */
  tagline: string
  features: string[]
  /** Whether the tier can be acted on today. */
  available: boolean
  /** Action for an available tier; null renders no control at all. */
  cta: { label: string; to: string } | null
  /** Status chip text ("Available now" / "Coming soon"). */
  status: 'available' | 'coming-soon'
}

export const PRICING_TIERS: readonly PricingTier[] = [
  {
    id: 'explorer',
    name: 'Explorer',
    priceMonthlyUsd: 0,
    priceNote: 'free during early access',
    tagline: 'Everything a family needs to start reading tonight.',
    features: [
      'Personalized story requests',
      'A profile and shelf for each reader',
      'Offline reading on your devices',
      'Grown-up approval on every book',
      'Every safety feature, always',
    ],
    available: true,
    cta: { label: 'Start free', to: GUARDIAN_LOGIN_PATH },
    status: 'available',
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
      'Read-aloud narration (planned)',
      'First access to new features',
    ],
    available: false,
    cta: null,
    status: 'coming-soon',
  },
]
