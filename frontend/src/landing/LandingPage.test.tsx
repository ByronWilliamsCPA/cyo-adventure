import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import type { Mock } from 'vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setDeviceGrant } from '../auth/deviceGrant'
import { _resetDbHandle } from '../offline/db'
import { ThemeProvider } from '../theme/ThemeProvider'
import { LANDING_HEADLINE } from './headline'
import { LandingPage } from './LandingPage'
import { PRICING_TIERS } from './pricing'

function renderLanding() {
  return render(
    // ThemeProvider: the page's ThemeToggle calls useTheme(), which throws
    // outside one; every real route already sits under it (App.tsx).
    // Stand-in targets so a programmatic navigation is observable: the Kids
    // door's click handler resolves the device grant before navigating, so
    // asserting the href alone would miss where a tap actually lands.
    <ThemeProvider>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/kids" element={<div>kid picker landing</div>} />
          <Route path="/guardian/login" element={<div>guardian login landing</div>} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>
  )
}

function seedValidGrant() {
  setDeviceGrant({
    token: 'tok-1',
    expiresAt: '2099-01-01T00:00:00Z',
    familyId: 'fam-1',
    id: 'grant-1',
  })
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  localStorage.clear()
})

describe('LandingPage', () => {
  it('shows the grown-up door linking to the guardian console with the admin note', () => {
    renderLanding()
    const guardianDoor = screen.getByRole('link', { name: /grown-ups/i })
    expect(guardianDoor).toHaveAttribute('href', '/guardian')
    expect(guardianDoor).toHaveTextContent('Admins sign in here too')
  })

  it('leads with the funnel value proposition and keeps the app name as the page title', () => {
    renderLanding()
    expect(screen.getByRole('heading', { level: 1, name: LANDING_HEADLINE })).toBeInTheDocument()
    // The brand moved from the <h1> to the topbar wordmark (and the document
    // title): the heading now carries the pitch, the wordmark the identity.
    expect(document.title).toBe('CYO Adventure')
  })

  // The funnel's primary action appears at every stage (topbar, hero, after
  // the safety section, final band) under ONE consistent label, and every
  // instance goes to guardian login, whose "Continue with Google/Apple" IS
  // the self-signup path (P-6e: there is no separate signup route).
  it('points every "Get started free" CTA at guardian login', () => {
    renderLanding()
    const ctas = screen.getAllByRole('link', { name: 'Get started free' })
    expect(ctas).toHaveLength(4)
    for (const cta of ctas) {
      expect(cta).toHaveAttribute('href', '/guardian/login')
    }
  })

  // The deployment approves each self-signup by hand (api/onboarding.py's
  // awaiting-approval default), so the page must set that expectation
  // instead of promising instant access.
  it('sets the hand-approval expectation up front', () => {
    renderLanding()
    // The hero carries it for the whole page; the final band used to repeat
    // it nearly verbatim and no longer does.
    const hero = screen.getByRole('region', { name: LANDING_HEADLINE })
    expect(within(hero).getByText(/we approve each family by hand/i)).toBeInTheDocument()
    expect(
      within(hero).getByText(/free while in early access\. no ads, ever\./i)
    ).toBeInTheDocument()
    // Still answered in the FAQ for anyone who scrolled past the hero.
    expect(screen.getByText(/we then approve each new family by hand/i)).toBeInTheDocument()
  })

  // Two "Sign in" links by design (topbar and footer), one label and one
  // destination between them: the footer used to say "Guardian sign-in" and
  // point at the login route while the topbar said "Sign in" and pointed at
  // the console, which is two names for the same errand.
  it('offers a returning adult a sign-in into the guardian console from the bar and the footer', () => {
    renderLanding()
    const signIns = screen.getAllByRole('link', { name: 'Sign in' })
    expect(signIns).toHaveLength(2)
    for (const link of signIns) {
      expect(link).toHaveAttribute('href', '/guardian')
    }
  })

  it('sends the hero secondary CTA to the sample-story demo', () => {
    renderLanding()
    expect(screen.getByRole('link', { name: 'Try a sample story' })).toHaveAttribute(
      'href',
      '#demo'
    )
  })

  it('renders the funnel sections: demo, how it works, safety, pricing, FAQ, final CTA', () => {
    renderLanding()
    const headings = [
      'Try a sample story',
      'How a story gets made',
      'Built so you can say yes',
      'Simple family pricing',
      'Questions grown-ups ask',
      'Ready for their next favorite story?',
    ]
    for (const name of headings) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
  })

  // The KWS-registered public pages must stay reachable from the page every
  // visitor lands on (ADR-018 D1); routeElements.test.tsx checks the route
  // side, this checks the links exist at all.
  it('keeps the footer links to the public privacy and support pages', () => {
    renderLanding()
    const footerNav = screen.getByRole('navigation', { name: 'About this app' })
    expect(within(footerNav).getByRole('link', { name: 'Privacy' })).toHaveAttribute(
      'href',
      '/privacy'
    )
    expect(within(footerNav).getByRole('link', { name: 'Support' })).toHaveAttribute(
      'href',
      '/support'
    )
  })

  // Both completed review cycles caught exactly one claim that outran the
  // product, so these pin the two that were wrong rather than trusting prose
  // review to catch the third. The rule: a safety claim must describe
  // something enforced today, or be explicitly dated to launch.
  describe('claims discipline', () => {
    it('dates verified-parent consent to launch instead of claiming it is live', () => {
      renderLanding()
      const safety = screen.getByRole('region', { name: 'Built so you can say yes' })
      // KWS parent verification is built but flag-off in production
      // (core/config.py::kws_verification_required defaults False, ADR-018),
      // so the present-tense claim would be false for every family today.
      expect(
        within(safety).queryByText(/verification and consent are built into sign-up/i)
      ).toBeNull()
      expect(within(safety).getByText(/turns on with our public launch/i)).toBeInTheDocument()
      // What DOES gate a new family today is the hand approval.
      expect(
        within(safety).getByText(/a real person reviews every new family/i)
      ).toBeInTheDocument()
    })

    it('scopes kid reading to authorized devices everywhere it mentions devices', () => {
      renderLanding()
      // The how-it-works footnote used to promise "on any device" while the
      // trust card and FAQ both scope access to devices the guardian
      // authorized (ADR-014). Offline reading is the device-agnostic part,
      // and only once a device is set up.
      expect(screen.getByText(/reads offline on any device you have set up/i)).toBeInTheDocument()
      expect(screen.queryByText(/work offline, on any device\./i)).toBeNull()
    })

    it('answers deletion and training questions without overclaiming', () => {
      renderLanding()
      // Mirrors PrivacyPolicyPage exactly: profile deletion is an in-app
      // control, whole-account deletion is by email. Promising a button that
      // does not exist is the failure this section prevents.
      expect(
        screen.getByText(/deleting your whole family account is done by email/i)
      ).toBeInTheDocument()
      // Claims nothing about any provider's training behavior.
      expect(screen.getByText(/governed by that provider's terms/i)).toBeInTheDocument()
    })
  })

  describe('pricing (subscription-ready, nothing sold today)', () => {
    it('renders a card for every available tier and none for the rest', () => {
      renderLanding()
      for (const tier of PRICING_TIERS) {
        const card = screen.queryByRole('article', { name: tier.name })
        if (tier.available) {
          expect(card).toBeInTheDocument()
        } else {
          // An unbuyable card invites a comparison the visitor cannot act on
          // and puts a price-shaped void beside the tier they should take.
          expect(card).toBeNull()
        }
      }
    })

    // The Phase 8 flip must stay a data change: this asserts the RENDER is
    // derived from `available`, so adding a priced tier to pricing.ts makes
    // its card appear with no JSX edit. Guards against someone hardcoding
    // "Explorer" once the filter made a single card the visible truth.
    it('derives the rendered cards from the data, not a hardcoded tier', () => {
      renderLanding()
      const availableNames = PRICING_TIERS.filter((tier) => tier.available).map((tier) => tier.name)
      // Compare the NAMES, not just the count: a length check is 1 === 1
      // today whether the JSX maps over PRICING_TIERS or hardcodes an
      // Explorer card, so it could not catch the hardcoding it is named for
      // until the Phase 8 flip made a second card appear.
      const rendered = screen
        .getAllByRole('article')
        .map((article) => article.getAttribute('aria-labelledby'))
        .map((id) => (id ? (document.getElementById(id)?.textContent ?? '') : ''))
      expect(rendered).toEqual(availableNames)
    })

    it('states the paid plan as a future commitment instead of a card', () => {
      renderLanding()
      const pricing = screen.getByRole('region', { name: 'Simple family pricing' })
      expect(within(pricing).getByText(/a paid family plan comes later/i)).toBeInTheDocument()
      expect(
        within(pricing).getByText(/books already on your shelf stay yours/i)
      ).toBeInTheDocument()
      // The whole section offers exactly one action, the free tier's CTA.
      expect(within(pricing).getAllByRole('link')).toHaveLength(1)
    })

    it('routes the available free tier to guardian login and discloses the real quota', () => {
      renderLanding()
      const explorer = screen.getByRole('article', { name: 'Explorer' })
      expect(within(explorer).getByText('Available now')).toBeInTheDocument()
      expect(within(explorer).getByText('Free')).toBeInTheDocument()
      // The free tier states the enforced backend default
      // (core/config.py::default_monthly_story_quota) instead of hiding a
      // cap a family would discover on day 11.
      expect(within(explorer).getByText('Up to 10 new story requests a month')).toBeInTheDocument()
      expect(within(explorer).getByRole('link', { name: 'Start free' })).toHaveAttribute(
        'href',
        '/guardian/login'
      )
    })

    // #VERIFY (pricing.ts #CRITICAL): with no billing backend, the section
    // must offer nothing that looks like a purchase. A control that cannot
    // charge would be a dark pattern aimed at parents.
    it('offers no purchase-looking control anywhere in the section', () => {
      renderLanding()
      const pricing = screen.getByRole('region', { name: 'Simple family pricing' })
      expect(within(pricing).queryByRole('button')).toBeNull()
      // Every link in the section routes to sign-in, never to a checkout.
      for (const link of within(pricing).getAllByRole('link')) {
        expect(link).toHaveAttribute('href', '/guardian/login')
      }
      // No currency figure survives anywhere: the only price today is "Free",
      // so a "$" on this page would mean an unbuyable amount got rendered.
      expect(pricing.textContent).not.toMatch(/\$/)
    })
  })

  describe('audience-aware section order', () => {
    it('leads with the funnel on a device without a grant', () => {
      renderLanding()
      const hero = screen.getByRole('heading', { level: 1 })
      const doors = screen.getByRole('navigation', { name: 'Pick who you are' })
      // DOCUMENT_POSITION_FOLLOWING: the doors come after the hero heading.
      expect(hero.compareDocumentPosition(doors) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it('leads with the doors on a family device (valid grant at mount)', () => {
      seedValidGrant()
      renderLanding()
      const hero = screen.getByRole('heading', { level: 1 })
      const doors = screen.getByRole('navigation', { name: 'Pick who you are' })
      expect(doors.compareDocumentPosition(hero) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })

  // S6: the topnav puts "/#pricing" and friends in the address bar, so they
  // get bookmarked and shared, but the landing route is lazy: the browser
  // resolves the fragment against an empty document and the visitor lands at
  // the top with no sign anything was meant to happen. The mount effect
  // re-runs the jump once.
  describe('bookmarked section links', () => {
    let scrollIntoView: Mock<(arg?: boolean | ScrollIntoViewOptions) => void>

    beforeEach(() => {
      // jsdom does not implement scrollIntoView.
      scrollIntoView = vi.fn<(arg?: boolean | ScrollIntoViewOptions) => void>()
      Element.prototype.scrollIntoView = scrollIntoView
      window.location.hash = ''
    })

    afterEach(() => {
      window.location.hash = ''
    })

    it('scrolls to the fragment the browser could not resolve', () => {
      // No matchMedia in jsdom, so this also covers the guard's absent leg:
      // no stated preference behaves like no reduced-motion request.
      window.location.hash = '#pricing'
      renderLanding()
      expect(scrollIntoView).toHaveBeenCalledTimes(1)
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth' })
    })

    it('jumps without animation for a reduced-motion visitor', () => {
      // scrollIntoView's own behavior option wins over the stylesheet, so the
      // preference has to be honored here explicitly.
      // jsdom implements no matchMedia at all, which is exactly why the
      // component guards the call; stub one that reports the preference.
      vi.stubGlobal('matchMedia', (query: string) => ({
        matches: query.includes('reduce'),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }))
      try {
        window.location.hash = '#pricing'
        renderLanding()
        expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto' })
      } finally {
        vi.unstubAllGlobals()
      }
    })

    it('does nothing without a fragment', () => {
      renderLanding()
      expect(scrollIntoView).not.toHaveBeenCalled()
    })

    it('ignores a fragment that matches no section', () => {
      window.location.hash = '#not-a-section'
      renderLanding()
      expect(scrollIntoView).not.toHaveBeenCalled()
    })
  })

  describe('device-state-aware Kids door (ADR-014 section 5)', () => {
    it('routes the Kids door through guardian login with the authorize-device intent when no grant exists', () => {
      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/guardian/login?intent=authorize-device')
    })

    it('routes the Kids door straight to the profile picker when a valid device grant exists (sync check)', () => {
      seedValidGrant()
      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/kids')
    })

    it('treats an expired stored grant the same as no grant', () => {
      setDeviceGrant({
        token: 'tok-1',
        expiresAt: '2020-01-01T00:00:00Z',
        familyId: 'fam-1',
        id: 'grant-1',
      })
      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/guardian/login?intent=authorize-device')
    })

    it('upgrades the Kids door to the profile picker after the async IndexedDB-mirror hydrate finds a valid grant', async () => {
      seedValidGrant()
      // Simulate a localStorage clear that leaves the IndexedDB mirror intact
      // (the mirror write is async; give it a tick before clearing).
      await new Promise((resolve) => setTimeout(resolve, 0))
      localStorage.removeItem('device_grant')

      renderLanding()
      // Sync first paint: nothing valid in localStorage, so the intent-carrying
      // login link is used.
      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute(
        'href',
        '/guardian/login?intent=authorize-device'
      )

      // The hydrate is DEFERRED to first interest in the door, so that a
      // visitor who never goes near it leaves no IndexedDB database behind.
      // Nothing should have opened one yet.
      expect(await indexedDB.databases()).toEqual([])

      fireEvent.focus(screen.getByRole('link', { name: /kids/i }))

      // Post-hydrate: the mirror is found, valid, and the door target upgrades.
      await waitFor(() =>
        expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute('href', '/kids')
      )
    })

    // A touch tap fires neither pointerenter nor focus, so the prewarm never
    // runs and the door still carries the stale authorize-device href. The
    // destination is the guardian LOGIN page, which never hydrates (only
    // DeviceAuthorizedRoute does, and this href does not route through it), so
    // without the click handler awaiting the read, a family whose localStorage
    // was evicted is sent through device authorization again while a valid
    // mirrored grant sits unread.
    it('recovers a mirrored grant on a touch tap with no hover or focus', async () => {
      seedValidGrant()
      await new Promise((resolve) => setTimeout(resolve, 50))
      localStorage.removeItem('device_grant')

      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/guardian/login?intent=authorize-device')

      // No pointerEnter, no focus: straight to the activation a tap produces.
      fireEvent.click(kidDoor, { button: 0 })

      await waitFor(() => expect(screen.getByText('kid picker landing')).toBeInTheDocument())
    })

    // The interception exists only to resolve an UNRESOLVED door. On a device
    // that already holds a grant the handler must get out of the way and let
    // the Link navigate normally.
    it('does not intercept the click when the grant is already resolved', async () => {
      seedValidGrant()
      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/kids')

      fireEvent.click(kidDoor, { button: 0 })
      await waitFor(() => expect(screen.getByText('kid picker landing')).toBeInTheDocument())
    })

    // preventDefault on a modified click would break the browser's own
    // open-in-new-tab, so the handler leaves those alone and they follow the
    // href as it stands. Asserted because the comment claims it.
    it('leaves modified clicks to the browser so open-in-new-tab still works', async () => {
      seedValidGrant()
      await new Promise((resolve) => setTimeout(resolve, 50))
      localStorage.removeItem('device_grant')

      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      fireEvent.click(kidDoor, { button: 0, metaKey: true })

      // No in-app navigation happened: the landing page is still mounted, and
      // the visitor was NOT pulled to the picker behind a new-tab gesture.
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(screen.queryByText('kid picker landing')).toBeNull()
      expect(screen.getByRole('link', { name: /kids/i })).toBeInTheDocument()
    })

    // The same path with nothing to recover must still reach the authorize
    // flow rather than stranding the visitor on the landing page.
    it('falls through to device authorization when no mirrored grant exists', async () => {
      renderLanding()
      fireEvent.click(screen.getByRole('link', { name: /kids/i }), { button: 0 })
      await waitFor(() => expect(screen.getByText('guardian login landing')).toBeInTheDocument())
    })

    // S5: hydrateDeviceGrant reaches offline/db.ts, which OPENS (and so
    // creates) the reader's IndexedDB database. Running it on mount meant
    // every anonymous marketing visit provisioned one.
    it('leaves no client-side database behind for a visitor who ignores the Kids door', async () => {
      renderLanding()
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(await indexedDB.databases()).toEqual([])
    })

    // The case LandingPage's #VERIFY names. It asserts the deliberate SPLIT:
    // a grant minted in another tab upgrades the door href live, because a
    // stale href would send a child through an authorize flow they no longer
    // need, while the section ORDER stays put, because reshuffling whole
    // sections under someone mid-read is a hostile layout shift. Both halves
    // matter: an implementation that re-derived order from the same event
    // would pass a href-only assertion.
    it('upgrades the door href on a cross-tab storage event without reordering sections', () => {
      renderLanding()
      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute(
        'href',
        '/guardian/login?intent=authorize-device'
      )
      const heroBefore = screen.getByRole('heading', { level: 1 })
      const doorsBefore = screen.getByRole('navigation', { name: 'Pick who you are' })
      // Funnel-first: the hero precedes the doors on an unknown device.
      expect(
        heroBefore.compareDocumentPosition(doorsBefore) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()

      // Another tab authorizes this device. 'storage' does not fire in the
      // tab that wrote the value, so dispatch it the way the browser would.
      act(() => {
        seedValidGrant()
        window.dispatchEvent(new StorageEvent('storage', { key: 'device_grant' }))
      })

      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute('href', '/kids')
      const hero = screen.getByRole('heading', { level: 1 })
      const doors = screen.getByRole('navigation', { name: 'Pick who you are' })
      expect(hero.compareDocumentPosition(doors) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    // The mirror of the above: a revoke elsewhere must downgrade the href, or
    // the door keeps pointing at /kids and DeviceAuthorizedRoute bounces the
    // child back with no explanation.
    it('downgrades the door href when another tab revokes the grant, durably', async () => {
      seedValidGrant()
      // Let the IndexedDB mirror write land, so this exercises the real
      // situation: a revoke that clears localStorage while the mirror is
      // still present. clearDeviceGrant's mirror delete is fire-and-forget,
      // so that window genuinely exists in production.
      await new Promise((resolve) => setTimeout(resolve, 0))
      renderLanding()
      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute('href', '/kids')

      act(() => {
        localStorage.removeItem('device_grant')
        window.dispatchEvent(new StorageEvent('storage', { key: 'device_grant' }))
      })

      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute(
        'href',
        '/guardian/login?intent=authorize-device'
      )

      // The assertion that matters, and the one a synchronous-only test
      // missed: the downgrade must SURVIVE. When the hydrate effect was keyed
      // on [kidsDoorPath], this downgrade re-armed it, the mirror was found,
      // and hydrateDeviceGrant wrote the revoked grant back into localStorage,
      // restoring the /kids href.
      //
      // The settle is a real timer, not a microtask flush: an IndexedDB read
      // through fake-indexeddb takes milliseconds, and a single await tick is
      // NOT enough to observe the resurrection. Verified by reverting the
      // effect's dep array to [kidsDoorPath]: with a 0ms settle this test
      // still passes (it measures nothing), with this one it fails on both
      // assertions below.
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50))
      })
      expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute(
        'href',
        '/guardian/login?intent=authorize-device'
      )
      expect(localStorage.getItem('device_grant')).toBeNull()
    })
  })
})
