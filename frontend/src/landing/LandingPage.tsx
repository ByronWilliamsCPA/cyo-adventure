import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { SkipLink } from '@ds/components/SkipLink'
import { hasValidDeviceGrant, hydrateDeviceGrant } from '../auth/deviceGrant'
import { usePageTitle } from '../hooks/usePageTitle'
import { Mascot } from '../kid/Mascot'
import {
  AUTHORIZE_DEVICE_INTENT_PARAM,
  AUTHORIZE_DEVICE_INTENT_VALUE,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  KID_PICKER_PATH,
  PRIVACY_PATH,
  SUPPORT_PATH,
} from '../routes'
import { ThemeToggle } from '../theme/ThemeToggle'

import { DemoAdventure } from './DemoAdventure'
import { PRICING_TIERS } from './pricing'
import './landing.css'

/**
 * Guardian login, carrying the authorize-device intent marker (ADR-014
 * section 5): the destination for the Kids door on a device with no valid
 * device grant yet. A guardian who signs in from here is authorizing THIS
 * device, not just visiting their console; DeviceAuthorizedRoute reads the
 * same intent constants (auth/DeviceAuthorizedRoute.tsx, routes.ts).
 */
const AUTHORIZE_DEVICE_PATH = `${GUARDIAN_LOGIN_PATH}?${AUTHORIZE_DEVICE_INTENT_PARAM}=${AUTHORIZE_DEVICE_INTENT_VALUE}`

/**
 * Root landing page, redesigned as the product's sales funnel (2026-08):
 * one page that serves two audiences without shortchanging either.
 *
 * RETURNING readers and guardians get the same two doors as before, kept
 * above the marketing content: the device-state-aware Kids door and the
 * Grown-ups door into the guardian console. That flow is unchanged.
 *
 * NEW adults (the funnel's target) get what the old page never gave them:
 * what the product is (hero + live demo), how it works (pipeline steps),
 * why to trust it (the safety section: mandatory grown-up approval, ADR-003;
 * verification/consent design, ADR-018; no ads or strangers, ADR-016), and
 * what it costs (subscription-ready pricing, see pricing.ts). Every CTA
 * lands on guardian login, whose "Continue with Google" IS the self-signup
 * path (P-6e); when Track 2 Phase 8 ships real subscriptions, the pricing
 * data flips without this page's structure changing.
 *
 * Still static by design (no data fetching, no auth) so it imports neither
 * the guardian/Supabase chunk nor any kid data hooks: only presentational
 * pieces (Mascot, ChoiceButton via DemoAdventure, SkipLink) are shared,
 * which keeps the router's per-audience chunk split intact.
 * `auth/deviceGrant.ts` is Supabase-free by design (same contract the kid
 * chunk relies on), so reading the device grant here does not pull Supabase
 * into this page either.
 */
export function LandingPage() {
  // Bare: this IS the app's root page, so its title is the app name itself,
  // matching index.html's static default rather than getting a redundant
  // "Home - CYO Adventure" suffix.
  usePageTitle('CYO Adventure', { bare: true })

  // Device-state-aware Kids door (ADR-014 section 5): an authorized device
  // sends a child straight to the profile picker; an unauthorized one routes
  // through guardian login carrying the authorize-device intent so the
  // guardian mints a grant for this device before handing it back. The
  // synchronous localStorage check covers the common case with no loading
  // flicker; hydrateDeviceGrant's IndexedDB-mirror fallback (the same
  // sync-then-hydrate pattern DeviceAuthorizedRoute uses) runs once after
  // mount and upgrades the door target if it finds a valid grant localStorage
  // lost (private-mode eviction, a fresh clear).
  // #ASSUME: timing dependencies: a device whose grant changes WHILE the
  // landing page is already mounted (e.g. a second tab authorizes it, or the
  // guardian console in another window removes it) is picked up by the
  // 'storage' listener below; the grant is device-local, so connectivity
  // changes never affect the door and no 'online' listener is needed. Either
  // way DeviceAuthorizedRoute re-checks when the door is followed.
  // #VERIFY: LandingPage.test.tsx "kids door" sync + post-hydrate +
  // storage-event cases.
  const [kidsDoorPath, setKidsDoorPath] = useState(() =>
    hasValidDeviceGrant() ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH
  )

  useEffect(() => {
    if (kidsDoorPath === KID_PICKER_PATH) return
    let cancelled = false
    void hydrateDeviceGrant().then((grant) => {
      if (cancelled) return
      if (grant) setKidsDoorPath(KID_PICKER_PATH)
    })
    return () => {
      cancelled = true
    }
  }, [kidsDoorPath])

  // Cross-tab freshness: 'storage' fires in THIS tab when ANOTHER tab or
  // window changes localStorage (minting a grant via the authorize-device
  // flow, or removing one from the guardian console), so re-derive the door
  // target from the same reader the mount-time state used. The grant's
  // storage key is private to deviceGrant.ts, so rather than duplicating it
  // here we re-derive on every storage event: hasValidDeviceGrant is a cheap
  // synchronous read, and setState with an unchanged value is a no-op.
  useEffect(() => {
    function rederiveKidsDoor() {
      setKidsDoorPath(hasValidDeviceGrant() ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH)
    }
    window.addEventListener('storage', rederiveKidsDoor)
    return () => {
      window.removeEventListener('storage', rederiveKidsDoor)
    }
  }, [])

  return (
    <div className="landing">
      <SkipLink targetId="landing-main" />

      {/* Slim persistent header: wordmark for identity, section anchors for
          the funnel's long-page navigation, and a quiet sign-in path for a
          returning guardian who scrolled past the doors. */}
      <header className="landing__topbar">
        <span className="landing__wordmark">
          <Mascot size={30} />
          <span className="landing__wordmark-name">CYO Adventure</span>
        </span>
        <nav className="landing__topnav" aria-label="Page sections">
          <a className="landing__topnav-link" href="#how-it-works">
            How it works
          </a>
          <a className="landing__topnav-link" href="#safety">
            Safety
          </a>
          <a className="landing__topnav-link" href="#pricing">
            Pricing
          </a>
        </nav>
        <span className="landing__topbar-actions">
          <Link className="landing__signin" to={GUARDIAN_CONSOLE_PATH}>
            Sign in
          </Link>
          <ThemeToggle className="landing__theme-toggle" />
        </span>
      </header>

      <main id="landing-main" tabIndex={-1}>
        {/* ── Funnel stage 1: attention. Value proposition + primary CTA. ── */}
        <section className="landing-hero" aria-labelledby="landing-hero-heading">
          <div className="landing-hero__copy">
            <p className="landing-hero__eyebrow">Choose-your-own adventures for young readers</p>
            <h1 className="landing-hero__heading" id="landing-hero-heading">
              They pick the path. You approve every page.
            </h1>
            <p className="landing-hero__lede">
              CYO Adventure turns your child&apos;s ideas into branching storybooks written for
              their reading level, screened by strict safety checks, and published only when you say
              yes.
            </p>
            <div className="landing-hero__actions">
              <Link
                className="landing-cta landing-cta--primary landing-cta--lg"
                to={GUARDIAN_LOGIN_PATH}
              >
                Get started free
              </Link>
              <a className="landing-cta landing-cta--ghost landing-cta--lg" href="#how-it-works">
                See how it works
              </a>
            </div>
            <p className="landing-hero__reassure">
              Free while in early access. No ads, no in-app chat, ever.
            </p>
          </div>
          {/* Decorative sample shelf: fake spines drawn with the same
              --cover-* gradients the real library uses, so the art direction
              matches the product a family actually receives. Only the front
              cover carries a title: the fanned back covers overlap (and Pip
              stands in front), so labels there would render half-hidden.
              Purely illustrative, so it is hidden from assistive tech. */}
          <div className="landing-hero__art" aria-hidden="true">
            <div className="landing-cover landing-cover--lagoon" />
            <div className="landing-cover landing-cover--plum">
              <span className="landing-cover__title">The Lantern Cave</span>
            </div>
            <div className="landing-cover landing-cover--forest" />
            <Mascot size={92} className="landing-hero__mascot" />
          </div>
        </section>

        {/* ── Returning users: the two doors, unchanged behavior, kept high
            on the page so a family that already reads here never scrolls
            through marketing to get in. ── */}
        <section className="landing-doors-band" aria-labelledby="landing-doors-heading">
          <h2 className="landing-doors-band__heading" id="landing-doors-heading">
            Already reading with us?
          </h2>
          <nav className="landing__doors" aria-label="Pick who you are">
            <Link className="landing-door landing-door--kids" to={kidsDoorPath}>
              <span className="landing-door__icon" aria-hidden="true">
                <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
                  <path
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 5 C7 3 10 3 12 5 C14 3 17 3 20 5 V19 C17 17 14 17 12 19 C10 17 7 17 4 19 Z M12 5 V19"
                  />
                </svg>
              </span>
              <span className="landing-door__text">
                <span className="landing-door__heading">Kids</span>
                <span className="landing-door__sub">Start reading</span>
              </span>
            </Link>
            <Link className="landing-door landing-door--guardian" to={GUARDIAN_CONSOLE_PATH}>
              <span className="landing-door__icon" aria-hidden="true">
                <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
                  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
                  <path
                    fill="currentColor"
                    d="M12 12 L15.5 8.5 L13 12 Z M12 12 L8.5 15.5 L11 12 Z"
                  />
                </svg>
              </span>
              <span className="landing-door__text">
                <span className="landing-door__heading">Grown-ups</span>
                <span className="landing-door__sub">Guardian console</span>
                <span className="landing-door__note">Admins sign in here too</span>
              </span>
            </Link>
          </nav>
        </section>

        {/* ── Funnel stage 2: interest. Show, don't tell: a working sample
            of the core mechanic, built from the reader's own primitive. ── */}
        <section
          className="landing-section landing-section--demo"
          aria-labelledby="landing-demo-heading"
        >
          <h2 className="landing-section__heading" id="landing-demo-heading">
            Try a ten-second adventure
          </h2>
          <p className="landing-section__lede">
            A tiny taste of how choices work. The real books are longer, personalized, and yours to
            approve.
          </p>
          <DemoAdventure />
        </section>

        {/* ── Funnel stage 2, continued: how a story is made. The pipeline
            (request -> generation -> validation gate -> human approval) is
            the product; each step below maps to a real subsystem. ── */}
        <section
          className="landing-section"
          id="how-it-works"
          aria-labelledby="landing-how-heading"
        >
          <h2 className="landing-section__heading" id="landing-how-heading">
            How a story gets made
          </h2>
          <ol className="landing-steps">
            <li className="landing-step">
              <span className="landing-step__number" aria-hidden="true">
                1
              </span>
              <h3 className="landing-step__title">Tell us about your reader</h3>
              <p className="landing-step__body">
                Pick an age band from 4 to 13, add interests, favorite characters, and a spark of an
                idea. Kids can ask for stories too; requests wait for your OK.
              </p>
            </li>
            <li className="landing-step">
              <span className="landing-step__number" aria-hidden="true">
                2
              </span>
              <h3 className="landing-step__title">The story engine drafts an adventure</h3>
              <p className="landing-step__body">
                A branching storybook is written to your child&apos;s reading level, with real
                choices, many endings, and characters who can return in sequels.
              </p>
            </li>
            <li className="landing-step">
              <span className="landing-step__number" aria-hidden="true">
                3
              </span>
              <h3 className="landing-step__title">Safety gates check every path</h3>
              <p className="landing-step__body">
                Automated validation walks every branch for age fit, tone, and content before any
                person even reads it. Anything questionable is flagged or rejected.
              </p>
            </li>
            <li className="landing-step">
              <span className="landing-step__number" aria-hidden="true">
                4
              </span>
              <h3 className="landing-step__title">You approve, then they read</h3>
              <p className="landing-step__body">
                Nothing reaches a child until a grown-up reads it and approves it. Edit any passage
                first if you like; you always have the final word.
              </p>
            </li>
          </ol>
          <p className="landing-section__footnote">
            Approved books land on their shelf in minutes and work offline, on any device.
          </p>
        </section>

        {/* ── Funnel stage 3: trust. For a kids' product this section IS the
            conversion driver; every card states a real, shipped guarantee. ── */}
        <section
          className="landing-section landing-section--safety"
          id="safety"
          aria-labelledby="landing-safety-heading"
        >
          <h2 className="landing-section__heading" id="landing-safety-heading">
            Built so you can say yes
          </h2>
          <p className="landing-section__lede">
            We built the safety rails first and the product around them.
          </p>
          <ul className="landing-trust">
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <CheckSealIcon />
              </span>
              <h3 className="landing-trust__title">A grown-up approves every story</h3>
              <p className="landing-trust__body">
                Machine checks come first, but a human decision comes last. Nothing is published to
                your family until an adult reads and approves it.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <ShieldIcon />
              </span>
              <h3 className="landing-trust__title">Verified grown-ups only</h3>
              <p className="landing-trust__body">
                Parent verification and consent flows are built in, designed around
                children&apos;s-privacy rules like COPPA. Kids never get accounts of their own.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <NoMegaphoneIcon />
              </span>
              <h3 className="landing-trust__title">No ads. No chat. No strangers.</h3>
              <p className="landing-trust__body">
                Kids see their bookshelf and their stories. There is nothing to buy, nobody to talk
                to, and nowhere to wander.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <RulerIcon />
              </span>
              <h3 className="landing-trust__title">Tuned to their reading level</h3>
              <p className="landing-trust__body">
                Age bands from 4 to 13 shape vocabulary, sentence length, and themes, and you set a
                level cap per reader.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <CloudOffIcon />
              </span>
              <h3 className="landing-trust__title">Reads offline</h3>
              <p className="landing-trust__body">
                Download books to a tablet for road trips and quiet time. Progress syncs when
                you&apos;re back online.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <KeyIcon />
              </span>
              <h3 className="landing-trust__title">You hold the keys</h3>
              <p className="landing-trust__body">
                Approve devices, assign books per child, and follow reading time from your family
                console. Access you grant, you can revoke.
              </p>
            </li>
          </ul>
        </section>

        {/* ── Funnel stage 4a: desire (the kid's side of the pitch). ── */}
        <section className="landing-section" aria-labelledby="landing-kids-heading">
          <h2 className="landing-section__heading" id="landing-kids-heading">
            Made for young readers
          </h2>
          <ul className="landing-perks">
            <li className="landing-perks__card">
              <h3 className="landing-perks__title">Stories that fit them</h3>
              <p className="landing-perks__body">
                Heroes, sidekicks, and worlds shaped by what your kid loves, and favorite characters
                can come back for sequels.
              </p>
            </li>
            <li className="landing-perks__card">
              <h3 className="landing-perks__title">Endings to collect</h3>
              <p className="landing-perks__body">
                Every book hides several endings. Finding them all earns badges worth bragging about
                at dinner.
              </p>
            </li>
            <li className="landing-perks__card">
              <h3 className="landing-perks__title">A shelf of their own</h3>
              <p className="landing-perks__body">
                Each reader gets their own profile, their own books, and a big friendly reading view
                with no clutter.
              </p>
            </li>
          </ul>
        </section>

        {/* ── Funnel stage 4b: pricing. Subscription-ready but honest about
            today: see pricing.ts for the Phase 8 wiring contract. ── */}
        <section
          className="landing-section landing-section--pricing"
          id="pricing"
          aria-labelledby="landing-pricing-heading"
        >
          <h2 className="landing-section__heading" id="landing-pricing-heading">
            Simple family pricing
          </h2>
          <p className="landing-section__lede">
            CYO Adventure is in early access: everything below is free while we grow the library
            together.
          </p>
          <div className="landing-pricing">
            {PRICING_TIERS.map((tier) => (
              <article
                key={tier.id}
                className={`landing-tier ${tier.available ? 'landing-tier--available' : 'landing-tier--soon'}`}
                aria-labelledby={`landing-tier-${tier.id}`}
              >
                <p className={`landing-tier__status landing-tier__status--${tier.status}`}>
                  {tier.available ? 'Available now' : 'Coming soon'}
                </p>
                <h3 className="landing-tier__name" id={`landing-tier-${tier.id}`}>
                  {tier.name}
                </h3>
                <p className="landing-tier__price">
                  {tier.priceMonthlyUsd === null ? (
                    <span className="landing-tier__price-soon">Coming soon</span>
                  ) : tier.priceMonthlyUsd === 0 ? (
                    <span className="landing-tier__price-amount">Free</span>
                  ) : (
                    <>
                      <span className="landing-tier__price-amount">${tier.priceMonthlyUsd}</span>
                      <span className="landing-tier__price-cadence">/month</span>
                    </>
                  )}
                </p>
                <p className="landing-tier__price-note">{tier.priceNote}</p>
                <p className="landing-tier__tagline">{tier.tagline}</p>
                <ul className="landing-tier__features">
                  {tier.features.map((feature) => (
                    <li key={feature} className="landing-tier__feature">
                      <span className="landing-tier__feature-mark" aria-hidden="true">
                        <CheckIcon />
                      </span>
                      {feature}
                    </li>
                  ))}
                </ul>
                {tier.cta ? (
                  <Link className="landing-cta landing-cta--primary" to={tier.cta.to}>
                    {tier.cta.label}
                  </Link>
                ) : (
                  <p className="landing-tier__waitnote">
                    Join free today and we&apos;ll invite you first.
                  </p>
                )}
              </article>
            ))}
          </div>
          <p className="landing-section__footnote">
            No payment details today. Safety features are never paywalled.
          </p>
        </section>

        {/* ── Objection handling. Native disclosures: keyboard- and
            screen-reader-friendly with zero script. ── */}
        <section className="landing-section" aria-labelledby="landing-faq-heading">
          <h2 className="landing-section__heading" id="landing-faq-heading">
            Questions grown-ups ask
          </h2>
          <div className="landing-faq">
            <details className="landing-faq__item">
              <summary className="landing-faq__question">What ages is it for?</summary>
              <p className="landing-faq__answer">
                Readers roughly 4 to 13. Stories are written to age bands, and each child&apos;s
                profile carries a reading-level cap you control.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">Are the stories written by AI?</summary>
              <p className="landing-faq__answer">
                Drafted by our story engine, yes; published by people. Every book must pass a
                deterministic safety and reading-level gate, and then a grown-up reads and approves
                it before any child can open it. Nothing auto-publishes.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">
                How is my child&apos;s privacy protected?
              </summary>
              <p className="landing-faq__answer">
                Kids never get accounts, emails, or public profiles. Grown-ups verify and consent up
                front, reading happens on devices you authorize, and there are no ads and no chat.
                The full policy is on our <Link to={PRIVACY_PATH}>privacy page</Link>.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">How much does it cost?</summary>
              <p className="landing-faq__answer">
                Nothing right now: early access is free. A Family subscription with the full catalog
                is planned, and we&apos;ll announce pricing before it launches. Safety features will
                never be behind a paywall.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">Does it work offline?</summary>
              <p className="landing-faq__answer">
                Yes. Books can be downloaded to a device and read without internet; reading progress
                catches up when you reconnect.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">Can kids use it on their own?</summary>
              <p className="landing-faq__answer">
                Kid mode is separate and simple: no sign-in, no settings, just their shelf. A
                grown-up authorizes each device once, and can revoke it any time.
              </p>
            </details>
          </div>
        </section>

        {/* ── Funnel stage 5: action. ── */}
        <section className="landing-final" aria-labelledby="landing-final-heading">
          <Mascot size={72} />
          <h2 className="landing-final__heading" id="landing-final-heading">
            Ready for their next favorite story?
          </h2>
          <p className="landing-final__lede">
            Set up your family in about a minute. Grown-ups only; kids join from your console.
          </p>
          <Link
            className="landing-cta landing-cta--primary landing-cta--lg"
            to={GUARDIAN_LOGIN_PATH}
          >
            Create your free account
          </Link>
        </section>
      </main>

      {/* The public privacy and support pages, linked from the one page every
          visitor lands on. Both are registered with Epic's Kids Web Services
          (ADR-018 D1), so they must be discoverable from the site itself and
          not only by anyone holding the direct URL: a policy reachable only
          through a third party's consent screen is not published in any sense
          a parent would recognise. Now a true top-level <footer> (contentinfo
          landmark): the redesigned page is normal document flow, so the old
          inside-<main> compromise (a 100vh flex hero) no longer applies. */}
      <footer className="landing__footer">
        <span className="landing__footer-brand">
          <Mascot size={24} />
          <span>CYO Adventure</span>
        </span>
        <nav aria-label="About this app">
          <Link className="landing__footer-link" to={PRIVACY_PATH}>
            Privacy
          </Link>
          <Link className="landing__footer-link" to={SUPPORT_PATH}>
            Support
          </Link>
          <Link className="landing__footer-link" to={GUARDIAN_LOGIN_PATH}>
            Guardian sign-in
          </Link>
        </nav>
      </footer>
    </div>
  )
}

/* Inline glyphs for the trust cards, in the door icons' visual language:
   24-viewBox, 2px round-capped strokes, currentColor. Local to this page on
   purpose; if a second surface ever needs them they graduate to the design
   system. All are decorative (wrapped in aria-hidden spans above). */

function CheckSealIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 2.8l2.2 2 3-.4 1 2.9 2.8 1.2-.6 3 1.8 2.5-1.8 2.5.6 3-2.8 1.2-1 2.9-3-.4-2.2 2-2.2-2-3 .4-1-2.9-2.8-1.2.6-3L1.8 14l1.8-2.5-.6-3L5.8 7.3l1-2.9 3 .4z"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8.4 12.2l2.4 2.4 4.8-5"
      />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3l7 3v5c0 4.6-3 8.4-7 10-4-1.6-7-5.4-7-10V6z"
      />
      <circle cx="12" cy="10" r="2.4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M8.6 16.2c.8-1.6 2-2.4 3.4-2.4s2.6.8 3.4 2.4"
      />
    </svg>
  )
}

function NoMegaphoneIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 10v4h3l6 4V6l-6 4z"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M20.5 3.5l-17 17"
      />
    </svg>
  )
}

function RulerIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <rect
        x="3"
        y="9"
        width="18"
        height="6"
        rx="1.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M7.5 9v3M12 9v3M16.5 9v3"
      />
    </svg>
  )
}

function CloudOffIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7 17h10a4 4 0 0 0 .8-7.9A5.5 5.5 0 0 0 7.3 7.6 4.5 4.5 0 0 0 7 17z"
      />
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M9 20h6" />
    </svg>
  )
}

function KeyIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="8" cy="14" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M11 11l8.5-8.5M16 6l3 3M13.5 8.5l2.5 2.5"
      />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4.5 12.5l5 5 10-11"
      />
    </svg>
  )
}
