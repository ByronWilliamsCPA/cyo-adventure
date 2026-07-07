import { expect, test } from '@playwright/test'

/**
 * Task 2.2 guardian browse-and-assign flow (route-mocked): sign in as a
 * guardian, open the Books page from the nav, see a published family book with
 * its content badge, open the Assign dialog, tick a sibling, and confirm the
 * POST body carries only the newly selected profile id.
 *
 * Auth is seeded the same way as assignments.spec.ts: a far-future GoTrueClient
 * session under the SDK storage key plus a mocked GET /v1/me, so the guardian
 * subtree's AuthProvider resolves a principal with no live Supabase backend.
 */

const SUPABASE_SESSION_KEY = 'sb-example-auth-token'

const GUARDIAN_SESSION = {
  access_token: 'e2e-guardian-access-token',
  refresh_token: 'e2e-guardian-refresh-token',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: 4102444800,
  user: {
    id: 'guardian-a',
    aud: 'authenticated',
    role: 'authenticated',
    app_metadata: {},
    user_metadata: {},
    created_at: '2026-07-02T00:00:00Z',
  },
}

const ME = {
  subject: 'guardian-a',
  role: 'guardian',
  family_id: 'fam-a',
  profile_ids: ['p1', 'p2'],
}

const PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '10-13',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
    {
      id: 'p2',
      display_name: 'Reader A2',
      age_band: '8-11',
      reading_level_cap: 99,
      avatar: 'owl',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

const BOOKS = {
  books: [
    {
      storybook_id: 'story-1',
      title: 'The Brave Little Fox',
      version: 1,
      age_band: '10-13',
      screened: true,
      flagged_count: 0,
      assigned_profile_ids: ['p1'],
    },
  ],
}

const CONTENT_SUMMARY = {
  storybook_id: 'story-1',
  version: 1,
  screened: true,
  summary: null,
  flagged_count: 0,
  findings: [],
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(
    ([key, session]) => {
      window.localStorage.setItem('auth_token', 'guardian-a')
      window.localStorage.setItem(key, session)
    },
    [SUPABASE_SESSION_KEY, JSON.stringify(GUARDIAN_SESSION)] as const
  )
})

test('guardian browses published books and assigns a sibling', async ({ page }) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))
  await page.route('**/api/v1/guardian/books', (route) =>
    route.fulfill({ json: BOOKS })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: PROFILES })
  )
  await page.route('**/api/v1/storybooks/story-1/content-summary', (route) =>
    route.fulfill({ json: CONTENT_SUMMARY })
  )
  let body: unknown = null
  await page.route('**/api/v1/storybooks/story-1/assignments', (route) => {
    if (route.request().method() === 'POST') {
      body = route.request().postDataJSON()
      return route.fulfill({
        json: { storybook_id: 'story-1', profile_ids: ['p1', 'p2'] },
      })
    }
    return route.fulfill({
      json: { storybook_id: 'story-1', profile_ids: ['p1'] },
    })
  })

  await page.goto('/guardian/books')
  await expect(page.getByText('The Brave Little Fox')).toBeVisible()
  await expect(page.getByText(/Assigned to: Reader A$/)).toBeVisible()

  await page.getByRole('button', { name: /^Assign The Brave Little Fox$/ }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox', { name: /Reader A2/ }).click()
  await dialog.getByRole('button', { name: /^Assign$/ }).click()
  await expect.poll(() => body).toEqual({ profile_ids: ['p2'] })
})

test('the Books nav link reaches the page', async ({ page }) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))
  await page.route('**/api/v1/guardian/books', (route) =>
    route.fulfill({ json: BOOKS })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: PROFILES })
  )
  await page.route('**/api/v1/generation-jobs', (route) =>
    route.fulfill({ json: { jobs: [] } })
  )
  await page.route('**/api/v1/review-queue', (route) =>
    route.fulfill({ json: { items: [] } })
  )
  await page.goto('/guardian')
  await page.getByRole('link', { name: 'Books' }).click()
  await expect(page).toHaveURL(/\/guardian\/books$/)
  await expect(page.getByText('The Brave Little Fox')).toBeVisible()
})
