import { expect, test } from '@playwright/test'

/**
 * Coverage for the C4a-2 profile-management flows: the kid-surface Profile
 * Picker (`/`) and its two states (populated, empty). Both mock
 * GET /api/v1/profiles the same way reader.spec.ts mocks the reader
 * endpoints: `page.route`, no live backend.
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

  await page.goto('/')

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

  await page.goto('/')

  await expect(page.getByText('No profiles yet')).toBeVisible()
  const grownUpLink = page.getByRole('link', { name: 'I am a grown-up' })
  await expect(grownUpLink).toBeVisible()
  await expect(grownUpLink).toHaveAttribute('href', '/guardian/profiles')
})
