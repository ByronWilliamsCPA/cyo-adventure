import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { setDeviceGrant } from '../auth/deviceGrant'
import { _resetDbHandle } from '../offline/db'
import { ThemeProvider } from '../theme/ThemeProvider'
import { LandingPage } from './LandingPage'
import { PRICING_TIERS } from './pricing'

function renderLanding() {
  return render(
    // ThemeProvider: the page's ThemeToggle calls useTheme(), which throws
    // outside one; every real route already sits under it (App.tsx).
    <ThemeProvider>
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    </ThemeProvider>
  )
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
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'They pick the path. You approve every page.',
      })
    ).toBeInTheDocument()
    // The brand moved from the <h1> to the topbar wordmark (and the document
    // title): the heading now carries the pitch, the wordmark the identity.
    expect(document.title).toBe('CYO Adventure')
  })

  // The funnel's primary action: the hero CTA goes straight to guardian
  // login, whose "Continue with Google/Apple" IS the self-signup path (P-6e:
  // there is no separate signup route).
  it('sends the hero "Get started free" CTA straight to guardian login', () => {
    renderLanding()
    const cta = screen.getByRole('link', { name: /get started free/i })
    expect(cta).toHaveAttribute('href', '/guardian/login')
    expect(screen.getByText(/free while in early access/i)).toBeInTheDocument()
  })

  it('offers a returning adult a topbar sign-in into the guardian console', () => {
    renderLanding()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/guardian')
  })

  it('renders the funnel sections in order: demo, how it works, safety, pricing, FAQ', () => {
    renderLanding()
    const headings = [
      'Try a ten-second adventure',
      'How a story gets made',
      'Built so you can say yes',
      'Made for young readers',
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

  describe('pricing (subscription-ready, nothing sold today)', () => {
    it('renders every tier from the pricing data', () => {
      renderLanding()
      for (const tier of PRICING_TIERS) {
        expect(screen.getByRole('article', { name: tier.name })).toBeInTheDocument()
      }
    })

    it('routes the available free tier to guardian login', () => {
      renderLanding()
      const explorer = screen.getByRole('article', { name: 'Explorer' })
      expect(within(explorer).getByText('Available now')).toBeInTheDocument()
      expect(within(explorer).getByText('Free')).toBeInTheDocument()
      expect(within(explorer).getByRole('link', { name: 'Start free' })).toHaveAttribute(
        'href',
        '/guardian/login'
      )
    })

    // #VERIFY (pricing.ts #CRITICAL): with no billing backend, the unpriced
    // tier must render NO actionable control at all; a purchase-looking
    // button that cannot purchase would be a dark pattern aimed at parents.
    it('renders the coming-soon tier with no actionable control', () => {
      renderLanding()
      const family = screen.getByRole('article', { name: 'Family' })
      expect(within(family).getAllByText('Coming soon').length).toBeGreaterThan(0)
      expect(within(family).queryByRole('link')).toBeNull()
      expect(within(family).queryByRole('button')).toBeNull()
    })
  })

  describe('device-state-aware Kids door (ADR-014 section 5)', () => {
    it('routes the Kids door through guardian login with the authorize-device intent when no grant exists', () => {
      renderLanding()
      const kidDoor = screen.getByRole('link', { name: /kids/i })
      expect(kidDoor).toHaveAttribute('href', '/guardian/login?intent=authorize-device')
    })

    it('routes the Kids door straight to the profile picker when a valid device grant exists (sync check)', () => {
      setDeviceGrant({
        token: 'tok-1',
        expiresAt: '2099-01-01T00:00:00Z',
        familyId: 'fam-1',
        id: 'grant-1',
      })
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
      setDeviceGrant({
        token: 'tok-1',
        expiresAt: '2099-01-01T00:00:00Z',
        familyId: 'fam-1',
        id: 'grant-1',
      })
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

      // Post-hydrate: the mirror is found, valid, and the door target upgrades.
      await waitFor(() =>
        expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute('href', '/kids')
      )
    })
  })
})
