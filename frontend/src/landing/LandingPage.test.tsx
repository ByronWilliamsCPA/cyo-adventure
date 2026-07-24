import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { setDeviceGrant } from '../auth/deviceGrant'
import { _resetDbHandle } from '../offline/db'
import { ThemeProvider } from '../theme/ThemeProvider'
import { LandingPage } from './LandingPage'

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

  it('names the app', () => {
    renderLanding()
    expect(screen.getByRole('heading', { level: 1, name: 'CYO Adventure' })).toBeInTheDocument()
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
