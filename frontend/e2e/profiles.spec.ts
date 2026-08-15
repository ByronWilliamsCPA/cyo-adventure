import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

/**
 * Coverage for the C4a-2 profile-management flows: the kid-surface Profile
 * Picker (`/kids`) and its two states (populated, empty). Both mock
 * GET /api/v1/profiles the same way reader.spec.ts mocks the reader
 * endpoints: `page.route`, no live backend.
 *
 * The Profile Picker now lives at `/kids`, not `/`; the landing page at `/`
 * is covered separately by landing.spec.ts.
 *
 * Guardian-surface e2e (ProfilesPage at /guardian/profiles) now lives in
 * guardian-*.spec.ts, seeded via support/auth.ts's seedGuardianSession and
 * mockMe helpers instead of driving the Supabase JS SDK's real session
 * handling. This file covers only the kid-surface picker.
 */

const TWO_PROFILES = {
  profiles: [
    {
      id: 'child-fox',
      display_name: 'Remy',
      age_band: '5-8',
      reading_level_cap: 3,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'child-noavatar',
      display_name: 'Zoe',
      age_band: '8-11',
      reading_level_cap: 5,
      avatar: null,
      tts_enabled: true,
      created_at: '2026-01-02T00:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /kids redirects to guardian login.
  await seedDeviceGrant(context)
})

test('picker renders both profile tiles and links to the guardian surface (US: profile picker)', async ({
  page,
}) => {
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  // Clicking a profile navigates into the real LibraryPage (C4a-3), which
  // fetches the library on mount. Mock it (empty) so the page renders its
  // deterministic no-books state instead of falling through to the vite proxy
  // and rendering the error state.
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

  await page.goto('/kids')

  await expect(page.getByText('Remy')).toBeVisible()
  await expect(page.getByText('Zoe')).toBeVisible()

  // The avatar-less profile falls back to its name's initial. Scope to
  // Zoe's tile: the "Add Child" tile also renders a fallback circle.
  const zoeTile = page.locator('li', { hasText: 'Zoe' })
  await expect(zoeTile.locator('.avatar-circle--fallback')).toHaveText('Z')

  const addChildLink = page.getByRole('link', { name: 'Add Child' })
  await expect(addChildLink).toHaveAttribute('href', '/guardian/profiles')

  await page.getByRole('link', { name: 'Remy' }).click()
  await expect(page).toHaveURL('/library/child-fox')
  // The real LibraryPage rendered its empty-library state, confirming the
  // picker links a profile into its own library.
  await expect(page.getByText('No books yet')).toBeVisible()
})

test('picker shows the empty state and grown-up link when there are no profiles', async ({
  page,
}) => {
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))

  await page.goto('/kids')

  await expect(page.getByText('No profiles yet')).toBeVisible()
  const grownUpLink = page.getByRole('link', { name: 'I am a grown-up' })
  await expect(grownUpLink).toBeVisible()
  await expect(grownUpLink).toHaveAttribute('href', '/guardian/profiles')
})

// P6-07 PIN gate: a PIN-protected profile detours through the padlock prompt
// (ProfilePickerPage.tsx). No other spec sets has_pin, so this surface (padlock
// tile, "Type your secret PIN", gentle wrong-PIN retry, and the
// PIN_ATTEMPTS_BEFORE_HELP=3 "Ask a grown-up" escape) is otherwise untested.
const PIN_PROFILE = {
  profiles: [
    {
      id: 'child-locked',
      display_name: 'Pip',
      age_band: '5-8',
      reading_level_cap: 3,
      avatar: 'fox',
      tts_enabled: false,
      has_pin: true,
      created_at: '2026-01-03T00:00:00Z',
    },
  ],
}

// The mint endpoint answers a wrong PIN with a 403 carrying the distinct
// PIN_MISMATCH code (api/child_sessions.py); the correct PIN mints a session.
const CORRECT_PIN = '1234'
const WRONG_PIN = '0000'

test('a PIN-protected profile shows the padlock, gently retries a wrong PIN, offers the grown-up escape after several tries, then unlocks with the correct PIN', async ({
  page,
}) => {
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PIN_PROFILE }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
  await page.route('**/api/v1/child-sessions', (route) => {
    const body = route.request().postDataJSON() as { pin?: string }
    if (body.pin === CORRECT_PIN) {
      return route.fulfill({
        status: 201,
        json: {
          token: 'child-token',
          expires_at: '2099-01-01T00:00:00Z',
          profile_id: 'child-locked',
        },
      })
    }
    return route.fulfill({ status: 403, json: { code: 'PIN_MISMATCH', detail: 'PIN did not match' } })
  })

  await page.goto('/kids')

  // The tile advertises the lock up front (aria-label carries the hint; the
  // padlock glyph itself is aria-hidden).
  const lockedTile = page.getByRole('link', { name: 'Pip needs a PIN' })
  await expect(lockedTile).toBeVisible()

  // Picking it detours to the PIN prompt instead of minting straight away.
  await lockedTile.click()
  const pinInput = page.getByLabel('Type your secret PIN')
  await expect(pinInput).toBeVisible()

  // A wrong PIN gets the gentle, non-scary retry copy and no grown-up escape yet.
  await pinInput.fill(WRONG_PIN)
  await page.getByRole('button', { name: "Let's read!" }).click()
  await expect(page.getByText(/Give it another try/i)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Ask a grown-up' })).toHaveCount(0)
  await expect(page).toHaveURL('/kids')

  // Two more wrong tries (three total) surface the "Ask a grown-up" way out so a
  // child who forgot the PIN is not stuck retrying forever (UX-K6).
  await page.getByLabel('Type your secret PIN').fill(WRONG_PIN)
  await page.getByRole('button', { name: "Let's read!" }).click()
  await expect(page.getByRole('link', { name: 'Ask a grown-up' })).toHaveCount(0)

  await page.getByLabel('Type your secret PIN').fill(WRONG_PIN)
  await page.getByRole('button', { name: "Let's read!" }).click()
  const escapeLink = page.getByRole('link', { name: 'Ask a grown-up' })
  await expect(escapeLink).toBeVisible()
  await expect(escapeLink).toHaveAttribute('href', '/guardian/login')

  // The correct PIN mints the child session and unlocks the child's library.
  await page.getByLabel('Type your secret PIN').fill(CORRECT_PIN)
  await page.getByRole('button', { name: "Let's read!" }).click()
  await expect(page).toHaveURL('/library/child-locked')
  await expect(page.getByText('No books yet')).toBeVisible()
})
