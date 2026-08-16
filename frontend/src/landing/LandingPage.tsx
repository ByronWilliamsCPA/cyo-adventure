import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { SkipLink } from '@ds/components/SkipLink'
import {
  clearDeviceGrant,
  hasValidDeviceGrant,
  hydrateDeviceGrant,
  isDeviceGrantRevocation,
} from '../auth/deviceGrant'
import type { DeviceGrant } from '../auth/deviceGrant'
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
import { LANDING_HEADLINE } from './headline'
import { formatMonthlyPrice, PRICING_TIERS } from './pricing'
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
 * RETURNING readers and guardians get the same two doors as before: the
 * device-state-aware Kids door and the Grown-ups door into the guardian
 * console. On a device that already holds a valid device grant (a family
 * device, checked once at mount) the doors render ABOVE the hero, so a child
 * handed the tablet sees their door on the first screenful; on an unknown
 * device the funnel leads and the doors sit directly under the hero. The
 * door behavior itself is unchanged either way.
 *
 * NEW adults (the funnel's target) get what the old page never gave them:
 * what the product is (hero + live demo), how it works (pipeline steps),
 * why to trust it (the safety section), and what it costs (subscription-
 * ready pricing, see pricing.ts). Every CTA lands on guardian login, whose
 * "Continue with Google" IS the self-signup path (P-6e). Note the funnel's
 * honesty constraint: a fresh self-signup lands in AuthStatus
 * 'awaiting-approval' (api/onboarding.py approves new families by hand), so
 * the copy here and in the FAQ sets that expectation up front instead of
 * promising instant access the deployment does not provide.
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
  const navigate = useNavigate()

  // Device-state-aware Kids door (ADR-014 section 5): an authorized device
  // sends a child straight to the profile picker; an unauthorized one routes
  // through guardian login carrying the authorize-device intent so the
  // guardian mints a grant for this device before handing it back. The
  // synchronous localStorage check covers the common case with no loading
  // flicker; hydrateDeviceGrant's IndexedDB-mirror fallback (the same
  // sync-then-hydrate pattern DeviceAuthorizedRoute uses) runs once after
  // mount and upgrades the door target if it finds a valid grant localStorage
  // lost (private-mode eviction, a fresh clear).
  // ONE mount-time read feeds both the door target and the section order.
  // They were two separate useState initializers calling hasValidDeviceGrant()
  // independently, which is a latent inconsistency rather than a live bug:
  // nothing guarantees two reads of an expiry-checked value inside the same
  // render agree, and a grant expiring between them would render doors-first
  // ordering around a door pointing at the authorize flow. Reading once makes
  // that state unrepresentable.
  // #ASSUME: timing dependencies: a device whose grant changes WHILE the
  // landing page is already mounted (e.g. a second tab authorizes it, or the
  // guardian console in another window removes it) is picked up by the
  // 'storage' listener below; the grant is device-local, so connectivity
  // changes never affect the door and no 'online' listener is needed. Either
  // way DeviceAuthorizedRoute re-checks when the door is followed.
  // #VERIFY: LandingPage.test.tsx "device-state-aware Kids door" sync +
  // post-hydrate + storage-event cases; the storage-event case asserts the
  // href updates while the section ORDER does not.
  const [grantAtMount] = useState(() => hasValidDeviceGrant())

  const [kidsDoorPath, setKidsDoorPath] = useState(() =>
    grantAtMount ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH
  )

  // Section ORDER is decided once, from the synchronous mount-time check
  // only: a family device leads with the doors, an unknown one with the
  // funnel. Deliberately NOT re-derived by the hydrate/storage upgrades
  // below; reshuffling whole sections under a visitor mid-read would be a
  // jarring layout shift for no benefit, and the next visit picks up the
  // new order.
  // #ASSUME: timing dependencies: this snapshot goes stale the moment the
  // grant changes, and that staleness is the intended behavior, not an
  // oversight. The door's HREF keeps upgrading live underneath it.
  const doorsFirst = grantAtMount

  // DEFERRED to first contact with the Kids door, and resolved BEFORE the
  // navigation completes.
  //
  // Not on mount, for two reasons. hydrateDeviceGrant reaches offline/db.ts,
  // which OPENS (and therefore creates) the reader's IndexedDB database: a
  // marketing visit by someone who never touches the Kids door left a
  // `cyo-reader` database behind, on a page that sells "No ads, ever" and
  // whose privacy notice is registered with KWS. And when this was an effect
  // keyed on [kidsDoorPath], a cross-tab REVOKE re-armed it: the storage
  // listener downgraded the href, that flipped kidsDoorPath, the effect
  // re-fired, found the IndexedDB mirror the revoke had not finished deleting,
  // and wrote the revoked grant back into localStorage, silently restoring the
  // door it had just taken away. clearDeviceGrant's mirror delete is
  // fire-and-forget (deviceGrant.ts:81-85, whose own comment allows the mirror
  // to outlive the localStorage clear), so that was a race the delete usually
  // won and sometimes lost.
  //
  // But prefetching on pointer-enter/focus ALONE is not enough, and assuming
  // otherwise was a real bug: a touch user taps with no pointer-enter and no
  // focus, so the stale authorize-device href is followed immediately. That
  // destination is the guardian LOGIN page, which never hydrates (only
  // DeviceAuthorizedRoute does, and the authorize href does not route through
  // it), so a family whose localStorage was evicted got sent through device
  // authorization again while a perfectly good mirrored grant sat unread.
  //
  // So: pointer-enter and focus PREWARM the read for mouse and keyboard users,
  // and the click handler AWAITS it before navigating. The promise is memoised,
  // so a prewarmed read is already settled by click time and the handler adds
  // nothing; an unwarmed one costs a single IndexedDB open on a tap the visitor
  // has already committed to.
  // #ASSUME: timing dependencies: modified and non-primary clicks are left
  // alone so the browser's own open-in-new-tab still works; those follow the
  // href as it currently stands, which is the pre-hydrate value at worst.
  // #VERIFY: LandingPage.test.tsx "kids door" post-hydrate case, "recovers a
  // mirrored grant on a touch tap with no hover or focus", and "downgrades the
  // door href ... durably".
  // Once this device's grant has been revoked while the page is open, the
  // IndexedDB mirror must never be trusted again for the rest of this page's
  // life. A monotonic flag, not a generation counter: a counter only tells a
  // hydrate whether a revoke landed DURING its own read, which leaves three
  // other orderings open.
  //
  //   revoke during the read  -> the .then below discards its result and
  //     undoes the write hydrateDeviceGrant already performed.
  //   revoke after the read   -> the memoised promise is already resolved
  //     holding the old grant, and a later click would reuse it and navigate
  //     to /kids. The flag makes hydrateOnce short-circuit to null instead,
  //     and the listener drops the stale promise.
  //   revoke before any read  -> nothing to hydrate from; the flag keeps it
  //     that way.
  //
  // Re-authorization still works: another tab minting a grant fires a
  // non-removal storage event, which sets kidsDoorPath to the picker, and the
  // click handler returns early on that without consulting the promise.
  // #CRITICAL: security: a revoked device must not re-acquire a usable grant
  // from a stale mirror, by any ordering. clearDeviceGrantMirror is
  // fire-and-forget, so the mirror can outlive the revoke and a fresh read
  // would happily restore it; refusing to read at all is what closes that.
  // #VERIFY: LandingPage.test.tsx "discards a hydrate that a revoke overtook",
  // "de-authorizes when the revoke event arrives after the hydrate", and
  // "does not reuse a cached grant after a revoke".
  const revokedSinceMountRef = useRef(false)

  const hydratePromiseRef = useRef<Promise<DeviceGrant | null> | null>(null)
  const hydrateOnce = useCallback(() => {
    // Short-circuit: once revoked, do not bother opening IndexedDB for an
    // answer that the .then guard below would discard anyway. Correctness does
    // NOT rest on this line (removing it keeps every test green); it just
    // avoids a pointless read on a device we already know is unauthorized.
    if (revokedSinceMountRef.current) return Promise.resolve(null)
    hydratePromiseRef.current ??= hydrateDeviceGrant()
      .then((grant) => {
        if (revokedSinceMountRef.current) {
          // A revoke overtook this read. hydrateDeviceGrant has already
          // written the mirrored grant back into localStorage, so undo it
          // (this also clears the mirror the revoke was racing to delete).
          clearDeviceGrant()
          setKidsDoorPath(AUTHORIZE_DEVICE_PATH)
          return null
        }
        if (grant) setKidsDoorPath(KID_PICKER_PATH)
        return grant
      })
      .catch(() => {
        // #EDGE: external resources: hydrateDeviceGrant handles the storage
        // failures it expects, so reaching here means something unforeseen.
        // The memoised promise MUST NOT stay rejected: the click handler has
        // already called preventDefault by the time it awaits this, so a
        // rejection with no handler leaves the Kids door doing nothing at all,
        // permanently, for the rest of the page's life. Clearing the ref lets
        // a second attempt retry, and resolving null sends this attempt down
        // the authorize path, which is the correct answer when the grant
        // cannot be read.
        hydratePromiseRef.current = null
        return null
      })
    return hydratePromiseRef.current
  }, [])

  // Prewarm wrapper: hydrateOnce returns the memoised promise so the click
  // handler can await it, but an event handler must return void.
  const prewarmKidsDoor = useCallback(() => {
    void hydrateOnce()
  }, [hydrateOnce])

  const handleKidsDoorClick = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      // Already resolved to the picker: nothing to wait for.
      if (kidsDoorPath === KID_PICKER_PATH) return
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return
      }
      event.preventDefault()
      void hydrateOnce().then((grant) => {
        void navigate(grant ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH)
      })
    },
    [kidsDoorPath, hydrateOnce, navigate]
  )

  // The topnav puts "/#pricing" and friends in the address bar, so those URLs
  // get bookmarked and shared. But this route is lazy: by the time the chunk
  // mounts, the browser has already tried and failed to resolve the fragment
  // against an empty document, leaving the visitor at the top of the page with
  // no indication anything was meant to happen. Re-run the jump once on mount.
  // Honors reduced motion explicitly: 'smooth' here would animate even though
  // the stylesheet disables scroll-behavior, because scrollIntoView's own
  // behavior option wins over CSS.
  // #ASSUME: timing dependencies: the element is in the DOM by the time this
  // effect runs, since the whole page renders synchronously; no data gates any
  // section. A stale or unknown fragment simply finds nothing and is ignored.
  // #VERIFY: landing.spec.ts "a bookmarked section link cold-loads at that
  // section".
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (!id) return
    const target = document.getElementById(id)
    if (!target) return
    // Guarded, matching theme.ts's readOsPreference: matchMedia is absent in
    // jsdom and in older embedded webviews, and an unguarded call here would
    // throw inside a mount effect and take the whole page down. Treating an
    // absent matchMedia as "no stated preference" matches the CSS default.
    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' })
  }, [])

  // Cross-tab freshness: 'storage' fires in THIS tab when ANOTHER tab or
  // window changes localStorage (minting a grant via the authorize-device
  // flow, or removing one from the guardian console), so re-derive the door
  // target. A REMOVAL is identified by isDeviceGrantRevocation reading the
  // event payload (the key stays private to deviceGrant.ts); anything else
  // re-derives from hasValidDeviceGrant, a cheap synchronous read where
  // setState with an unchanged value is a no-op.
  useEffect(() => {
    function rederiveKidsDoor(event: StorageEvent) {
      // The revoke is detected from the EVENT, not by re-reading storage, and
      // that closes the second ordering. Both are possible:
      //
      //   event first, hydrate second -> the generation bump below makes the
      //     hydrate discard its own result (see revokedSinceMountRef above).
      //   hydrate first, event second -> the hydrate has ALREADY written the
      //     stale grant back, so hasValidDeviceGrant() would read the restored
      //     value, report "still valid", and leave a revoked device sitting on
      //     /kids. The event's own newValue is the only evidence that survives
      //     the overwrite.
      //
      // clearDeviceGrant() here undoes exactly that restore; it is a no-op
      // when the hydrate has not landed yet.
      if (isDeviceGrantRevocation(event)) {
        revokedSinceMountRef.current = true
        // Drop any promise resolved BEFORE the revoke: a later click would
        // otherwise reuse its grant and navigate to /kids.
        hydratePromiseRef.current = null
        clearDeviceGrant()
        setKidsDoorPath(AUTHORIZE_DEVICE_PATH)
        return
      }
      setKidsDoorPath(hasValidDeviceGrant() ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH)
    }
    window.addEventListener('storage', rederiveKidsDoor)
    return () => {
      window.removeEventListener('storage', rederiveKidsDoor)
    }
  }, [])

  /* ── Funnel stage 1: attention. Value proposition + primary CTA. ── */
  const hero = (
    <section className="landing-hero" aria-labelledby="landing-hero-heading">
      <div className="landing-hero__copy">
        <h1 className="landing-hero__heading" id="landing-hero-heading">
          {LANDING_HEADLINE}
        </h1>
        <p className="landing-hero__lede">
          CYO Adventure turns your child&apos;s ideas into branching storybooks, written for their
          reading level and screened by strict safety checks.
        </p>
        <div className="landing-hero__actions">
          <Link
            className="landing-cta landing-cta--primary landing-cta--lg"
            to={GUARDIAN_LOGIN_PATH}
          >
            Get started free
          </Link>
          <a className="landing-cta landing-cta--ghost landing-cta--lg" href="#demo">
            Try a sample story
          </a>
        </div>
        {/* Carries the hand-approval promise for the whole page: the final
            band used to repeat it almost verbatim two screens later, which
            read as padding rather than reassurance. */}
        <p className="landing-hero__reassure">
          Free while in early access. No ads, ever. We approve each family by hand, so kids never
          share the space with strangers.
        </p>
      </div>
      {/* Decorative sample shelf: fake spines drawn with the same --cover-*
          gradients the real library uses, so the art direction matches the
          product a family actually receives.
          All three spines carry titles, anchored to the TOP of each cover.
          The original build bottom-anchored them, where the fan overlap and
          the mascot both occluded the text, so they were cut back to the one
          unobstructed front cover. Top anchoring dodges both, which is what
          lets all three carry a title: a shelf of blank rectangles reads as
          placeholder art rather than as books. Decorative either way, hence
          the aria-hidden wrapper. */}
      <div className="landing-hero__art" aria-hidden="true">
        <div className="landing-cover landing-cover--lagoon">
          <span className="landing-cover__title">The Sunken Signal</span>
        </div>
        <div className="landing-cover landing-cover--plum">
          <span className="landing-cover__title">The Lantern Cave</span>
        </div>
        <div className="landing-cover landing-cover--forest">
          <span className="landing-cover__title">The Lost Mitten</span>
        </div>
        <Mascot size={92} className="landing-hero__mascot" />
      </div>
    </section>
  )

  /* ── Returning users: the two doors, unchanged behavior. Rendered above
      the hero on a granted (family) device, below it otherwise; see the
      doorsFirst note near the top.

      UX-7 (a COMPACT variant of this band when it renders funnel-first, so
      returning-user furniture intrudes less on a new visitor) was considered
      and DECLINED. One band, one size: the doors are the contractual entry
      points for both audiences (ADR-014), and a second visual treatment of
      them means two sets of geometry, focus order, and touch targets to keep
      correct for a purely cosmetic gain. The band is already a single row of
      two cards under a short heading, and on an unknown device it sits below
      the fold, where it costs the funnel nothing. Revisit only with evidence
      that it actually diverts new visitors. ── */
  const doorsBand = (
    <section className="landing-doors-band" aria-labelledby="landing-doors-heading">
      <h2 className="landing-doors-band__heading" id="landing-doors-heading">
        {doorsFirst ? 'Pick up where you left off' : 'Already reading with us?'}
      </h2>
      <nav className="landing__doors" aria-label="Pick who you are">
        <Link
          className="landing-door landing-door--kids"
          to={kidsDoorPath}
          onPointerEnter={prewarmKidsDoor}
          onFocus={prewarmKidsDoor}
          onClick={handleKidsDoorClick}
        >
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
              <path fill="currentColor" d="M12 12 L15.5 8.5 L13 12 Z M12 12 L8.5 15.5 L11 12 Z" />
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
  )

  return (
    <div className="landing">
      <SkipLink targetId="landing-main" />

      {/* Slim persistent header: wordmark for identity, section anchors for
          the funnel's long-page navigation, the primary CTA (sticky, so the
          action stays reachable through the whole scroll), and a quiet
          sign-in path for a returning guardian. The anchors are plain
          fragment hrefs on purpose: same-document jumps that never involve
          the data router. The router does not observe hash changes, and the
          lazy landing chunk mounts AFTER the browser has resolved the
          fragment, so a bookmarked "/#pricing" used to cold-load at the top
          of the page with nothing to scroll to; the mount effect above
          repairs that once. Nothing else should build on location.hash. */}
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
          <Link
            className="landing-cta landing-cta--primary landing-cta--compact"
            to={GUARDIAN_LOGIN_PATH}
          >
            Get started free
          </Link>
          <ThemeToggle />
        </span>
      </header>

      <main id="landing-main" tabIndex={-1}>
        {doorsFirst ? (
          <>
            {doorsBand}
            {hero}
          </>
        ) : (
          <>
            {hero}
            {doorsBand}
          </>
        )}

        {/* ── Funnel stage 2: interest. Show, don't tell: a working sample
            of the core mechanic, built from the reader's own primitive. The
            hero's secondary CTA targets this section: the demo converts
            better than any explainer, so the "not convinced yet" path lands
            here first. ── */}
        <section
          className="landing-section landing-section--demo"
          id="demo"
          aria-labelledby="landing-demo-heading"
        >
          {/* Eyebrow + heading, matching every other funnel section. The
              heading also matches the hero's ghost CTA verbatim ("Try a
              sample story"): a visitor who clicks that CTA must land on a
              heading that confirms they arrived, and "ten-second adventure"
              made them check. */}
          {/* The rail wrapper exists for the wide-viewport two-column frame
              (see .landing-section--demo): copy on the left, the playable
              demo on the right. Below 56rem it collapses to plain stacked
              blocks and the wrapper is inert. */}
          <div className="landing-section__rail">
            <p className="landing-section__eyebrow">Sample</p>
            <h2 className="landing-section__heading" id="landing-demo-heading">
              Try a sample story
            </h2>
            <p className="landing-section__lede">
              A tiny taste of how choices work. The real books are longer, personalized, and yours
              to approve.
            </p>
          </div>
          <DemoAdventure />
        </section>

        {/* ── Funnel stage 2, continued: how a story is made. The pipeline
            (request -> generation -> validation gate -> human approval) is
            the product; each step below maps to a real subsystem. Section
            eyebrows echo the topnav labels ("How it works", "Safety",
            "Pricing") so an anchor click lands on a heading that confirms
            where you are, while the h2s keep their own voice. ── */}
        <section
          className="landing-section"
          id="how-it-works"
          aria-labelledby="landing-how-heading"
        >
          <p className="landing-section__eyebrow">How it works</p>
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
              {/* #CRITICAL: security: this step used to read "You approve, then they read" and
                  "you always have the final word", which describes an authority a guardian does
                  not hold. Publication approval is admin-only and cross-family: every mutating
                  handler in api/approval.py requires the admin role, and api/node_edit.py's
                  module docstring says so outright ("approval itself stays admin-only
                  regardless"). It read as true only because this deployment's one family is
                  dual-role; it becomes false for exactly the new families this funnel exists to
                  attract, which is the worst possible time for a safety claim to turn out
                  overstated. The two controls a guardian really holds are named instead, both
                  real: passage editing (G6, /guardian/review/:storybookId) and per-child
                  assignment (G16, POST /v1/storybooks/{id}/assignments), with G8 unassign behind
                  it.
                  #VERIFY: LandingPage.test.tsx "does not claim the guardian approves stories". */}
              <h3 className="landing-step__title">A reviewer approves, you choose who reads it</h3>
              <p className="landing-step__body">
                Nothing reaches a child until a person has read it and approved it. You can edit any
                passage first, and you decide which of your children it goes to.
              </p>
            </li>
          </ol>
          {/* "on any device" contradicted both the trust card and the FAQ,
              which correctly scope kid access to devices the guardian has
              authorized (ADR-014). Offline reading is the part that really is
              device-agnostic once a device is set up, so the sentence now
              draws that line instead of blurring it. */}
          {/* #CRITICAL: security: "Once you approve a book it lands on their shelf right away"
              was wrong twice over. The guardian does not approve (see the step above), and
              approval does not put a book on any shelf: api/library.py's list_library requires an
              EXISTS on storybook_assignment for that exact profile, and api/assignments.py's
              assign_storybook is the only writer of that row. publishing/service.py::approve
              creates no assignment, so a guardian who believed this sentence would hand over a
              tablet and find an empty library. That gap is registered as UW-J01 (auto-assign on
              publish); this sentence is deliberately worded to stay true either way, since "you
              choose which child" describes the request-time choice as accurately as the
              assign-time one.
              #VERIFY: LandingPage.test.tsx "does not promise a book reaches a shelf on approval". */}
          <p className="landing-section__footnote">
            You choose which child each approved book goes to, and it reads offline on any device
            you have set up.
          </p>
        </section>

        {/* ── Funnel stage 3: trust. For a kids' product this section IS the
            conversion driver, so every card must stay inside what the
            product enforces today: parent verification/consent (ADR-018) is
            built but flag-off in production (core/config.py::
            kws_verification_required defaults False) and verified only
            against KWS's Test environment, so that card names what DOES gate
            a new family today (hand approval) and dates the COPPA control to
            public launch rather than describing it in the present tense.
            Reading-level tuning and offline reading
            are real but are features, not trust claims; they live in the
            how-it-works steps and pricing list instead of diluting this
            section. ── */}
        <section
          className="landing-section landing-section--safety"
          id="safety"
          aria-labelledby="landing-safety-heading"
        >
          <p className="landing-section__eyebrow">Safety</p>
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
              {/* "A grown-up approves every story" was literally true and still misled: sitting
                  beside a step that said "You approve", a new parent read it as themselves. The
                  approver is a platform-side safety reviewer with cross-family authority
                  (api/approval.py), so the card names them rather than leaving "a grown-up" to be
                  filled in with the reader. Note the possessive that is deliberately absent:
                  "our safety reviewer", never "your family's", which is the same misattribution
                  UW-J28 corrects in ConsolePage.tsx. */}
              <h3 className="landing-trust__title">A person approves every story</h3>
              <p className="landing-trust__body">
                Machine checks come first, but a human decision comes last. Nothing is published to
                your family until our safety reviewer has read it and approved it.
              </p>
            </li>
            <li className="landing-trust__card">
              <span className="landing-trust__icon" aria-hidden="true">
                <ShieldIcon />
              </span>
              <h3 className="landing-trust__title">Grown-ups only, by design</h3>
              <p className="landing-trust__body">
                Kids never get accounts of their own. A grown-up signs in with their own account,
                and a real person reviews every new family before it is switched on. Verified-parent
                consent (COPPA) is built in and turns on with our public launch.
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
                <KeyIcon />
              </span>
              <h3 className="landing-trust__title">You hold the keys</h3>
              <p className="landing-trust__body">
                Approve devices, assign books per child, and see what they have started, finished,
                and discovered from your family console. Access you grant, you can revoke.
              </p>
            </li>
          </ul>
          {/* The reader who just finished the trust section is the page's
              most-convinced visitor; give them the action here instead of
              two screens later. */}
          <div className="landing-section__cta">
            <Link
              className="landing-cta landing-cta--primary landing-cta--lg"
              to={GUARDIAN_LOGIN_PATH}
            >
              Get started free
            </Link>
          </div>
        </section>

        {/* ── Funnel stage 4: pricing. Subscription-ready but honest about
            today: see pricing.ts for the Phase 8 wiring contract. ── */}
        <section className="landing-section" id="pricing" aria-labelledby="landing-pricing-heading">
          <p className="landing-section__eyebrow">Pricing</p>
          <h2 className="landing-section__heading" id="landing-pricing-heading">
            Simple family pricing
          </h2>
          <p className="landing-section__lede">
            CYO Adventure is in early access: everything below is free while we grow the library
            together.
          </p>
          {/* Only AVAILABLE tiers get a card. Two independent cold reviewers
              converged on the unbuyable "Family / Coming soon" card being a
              de-conversion element: it invites a comparison the visitor
              cannot act on, and it puts a price-shaped void next to the
              thing they should be clicking. Subscription-readiness lives in
              the data model plus this filter, not in a visible card, so the
              Phase 8 flip is still the one-line data change pricing.ts
              documents. Unavailable tiers collapse into the futures line
              below, which promises exactly what ADR-008 commits to. */}
          <div className="landing-pricing landing-pricing--single">
            {PRICING_TIERS.filter((tier) => tier.available).map((tier) => (
              <article
                key={tier.id}
                className="landing-tier landing-tier--available"
                aria-labelledby={`landing-tier-${tier.id}`}
              >
                <p className="landing-tier__status landing-tier__status--available">
                  Available now
                </p>
                <h3 className="landing-tier__name" id={`landing-tier-${tier.id}`}>
                  {tier.name}
                </h3>
                <p className="landing-tier__price">
                  <span className="landing-tier__price-amount">
                    {formatMonthlyPrice(tier.priceMonthlyUsd)}
                  </span>
                  {tier.priceMonthlyUsd > 0 ? (
                    <span className="landing-tier__price-cadence">/month</span>
                  ) : null}
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
                <Link className="landing-cta landing-cta--primary" to={tier.cta.to}>
                  {tier.cta.label}
                </Link>
              </article>
            ))}
          </div>
          {PRICING_TIERS.some((tier) => !tier.available) ? (
            <p className="landing-pricing__futures">
              A paid Family plan comes later: we will announce pricing here before anything changes,
              and books already on your shelf stay yours.
            </p>
          ) : null}
          <p className="landing-section__footnote">
            No payment details today. Safety features are never paywalled.
          </p>
        </section>

        {/* ── Objection handling. Native disclosures: keyboard- and
            screen-reader-friendly with zero script. Answers stay inside the
            privacy policy's enforced claims (legal/PrivacyPolicyPage.tsx):
            no selling, no ads, prompts to named AI providers behind a
            reject-not-edit PII gate, and no training claim we cannot back. ── */}
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
                What happens to my child&apos;s story ideas?
              </summary>
              <p className="landing-faq__answer">
                The idea becomes the prompt that writes the book, sent to the AI provider that
                drafts it. A check rejects any request containing a child&apos;s name, email, phone
                number, or address before it leaves our servers. We do not sell information and
                there are no ads; our <Link to={PRIVACY_PATH}>privacy page</Link> lists exactly
                which providers receive what.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">
                How is my child&apos;s privacy protected?
              </summary>
              <p className="landing-faq__answer">
                Kids never get accounts, emails, or public profiles. Reading happens only on devices
                you authorize, and there are no ads and no chat. Every new family is reviewed by a
                person before it is switched on, and verified-parent consent under
                children&apos;s-privacy rules like COPPA turns on with our public launch. The full
                policy is on our <Link to={PRIVACY_PATH}>privacy page</Link>.
              </p>
            </details>
            {/* UX-12: deletion and training are the two questions a privacy-minded
                parent arrives with, and both were answerable only by opening the
                policy. Deletion mirrors PrivacyPolicyPage's split exactly (profile
                deletion is an in-app control, family-account deletion is by email)
                because promising a button that does not exist is the failure mode
                this section is supposed to prevent. The training answer deliberately
                claims nothing about any provider's behavior and points at the page
                that names them. */}
            <details className="landing-faq__item">
              <summary className="landing-faq__question">Can I delete our data?</summary>
              <p className="landing-faq__answer">
                Yes. You can delete a single child&apos;s profile in your console. Deleting your
                whole family account is done by email today rather than by a button, and deletion is
                permanent either way. Our <Link to={PRIVACY_PATH}>privacy page</Link> lists every
                right and which ones are in-app.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">
                Is my family&apos;s data used to train AI?
              </summary>
              <p className="landing-faq__answer">
                We do not sell your information or use it for advertising. Whether a provider may
                train on inputs is governed by that provider&apos;s terms; our{' '}
                <Link to={PRIVACY_PATH}>privacy page</Link> names each provider and exactly what it
                receives.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">What happens after I sign up?</summary>
              <p className="landing-faq__answer">
                Creating your account takes about a minute. We then approve each new family by hand;
                it is part of how we keep the space safe, and your console unlocks as soon as we do.
                After that you add readers and request your first story.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">How much does it cost?</summary>
              <p className="landing-faq__answer">
                Nothing right now: early access is free. A Family subscription with the full catalog
                is planned, and we&apos;ll announce pricing before it launches. Books already on
                your shelf stay readable, and safety features will never be behind a paywall.
              </p>
            </details>
            <details className="landing-faq__item">
              <summary className="landing-faq__question">How long is a book?</summary>
              <p className="landing-faq__answer">
                A first read-through takes roughly five to twelve minutes depending on age and
                length. Finding every ending in a bigger book can fill an hour, which is rather the
                point: they come back and choose differently.
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
          {/* Short, but not at the expense of the approval expectation: this
              is the last thing a scrolled visitor reads before clicking, and
              "a minute, then Pip" quietly promised the instant access the
              rest of the page is careful not to. */}
          <p className="landing-final__lede">
            Create your account in about a minute. We approve each family by hand, then Pip is
            waiting.
          </p>
          <Link
            className="landing-cta landing-cta--primary landing-cta--lg"
            to={GUARDIAN_LOGIN_PATH}
          >
            Get started free
          </Link>
        </section>
      </main>

      {/* The public privacy and support pages, linked from the one page every
          visitor lands on. Both are registered with Epic's Kids Web Services
          (ADR-018 D1), so they must be discoverable from the site itself and
          not only by anyone holding the direct URL: a policy reachable only
          through a third party's consent screen is not published in any sense
          a parent would recognise. A true top-level <footer> (contentinfo
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
          <Link className="landing__footer-link" to={GUARDIAN_CONSOLE_PATH}>
            Sign in
          </Link>
        </nav>
      </footer>
    </div>
  )
}

/* Inline glyphs for the trust cards and the pricing-feature bullets, in the
   door icons' visual language: 24-viewBox, 2px round-capped strokes,
   currentColor. Local to this page on purpose, matching the repo's idiom
   (ThemeToggle and the door SVGs are inline too); if a second surface ever
   needs them they graduate to the design system. All are decorative
   (wrapped in aria-hidden spans above). */

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
