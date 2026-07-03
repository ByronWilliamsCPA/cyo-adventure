import { expect, test } from '@playwright/test'

/**
 * Coverage for the C4a-2 profile-management flows: the kid-surface Profile
 * Picker (`/`) and its two states (populated, empty). Both mock
 * GET /api/v1/profiles the same way reader.spec.ts mocks the reader
 * endpoints: `page.route`, no live backend.
 *
 * Guardian scenario (ProfilesPage at /guardian/profiles) is intentionally
 * NOT covered here. That route tree mounts GuardianAuthLayout, which loads
 * AuthProvider -> supabaseClient.ts as a lazy chunk. supabaseClient throws at
 * module-evaluation time unless VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
 * are set (neither is set anywhere in this repo or CI; only a placeholder
 * lives in frontend/.env.example), so `npm run build` for this e2e run bakes
 * in `undefined` and the guardian subtree renders its errorElement instead
 * of ProfilesPage. Getting a real guardian page to render would additionally
 * require faking the Supabase JS SDK's own session/localStorage handling
 * (GoTrueClient), not a two-endpoint page.route mock like the kid surface
 * uses, so it is not cheap the way the reader/picker mocks are. The guardian
 * ProfilesPage and ProfileFormDialog have thorough Vitest coverage instead
 * (src/guardian/ProfilesPage.test.tsx).
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
  await expect(page.getByRole('heading', { name: 'My Books' })).toBeVisible()
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
