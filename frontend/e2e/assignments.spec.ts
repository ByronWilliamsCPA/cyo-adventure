import { expect, test } from '@playwright/test'

/**
 * C4a-6 guardian assign flow (route-mocked): open the Assign-more dialog from an
 * approved request row, tick a sibling, and confirm the POST body carries only
 * the newly selected profile id.
 *
 * Unlike the kid-surface specs (library.spec.ts, reader.spec.ts), the guardian
 * surface mounts GuardianAuthLayout -> AuthProvider, which resolves the
 * principal from a real Supabase (GoTrueClient) session before ProtectedRoute
 * will render IntakePage. A plain `auth_token` localStorage entry is not enough
 * (that only feeds useApi's bearer interceptor). So this spec seeds a
 * far-future GoTrueClient session under the SDK's storage key and mocks
 * GET /v1/me to resolve a guardian principal. The storage key is
 * `sb-<ref>-auth-token`, where <ref> is the first label of the Supabase URL
 * hostname; playwright.config.ts builds with VITE_SUPABASE_URL
 * https://example.supabase.co, so the ref is `example`. getSession() returns a
 * non-expired session from storage without any network call, so no live
 * Supabase backend is required. API traffic is still page.route-mocked.
 */

const SUPABASE_SESSION_KEY = 'sb-example-auth-token'

// A GoTrueClient session shape: getSession's _isValidSession only requires
// access_token / refresh_token / expires_at, and a far-future expires_at skips
// the auto-refresh network path. The frontend never inspects the token itself
// (AuthContext treats it as opaque and reads role/family from /v1/me).
const GUARDIAN_SESSION = {
  access_token: 'e2e-guardian-access-token',
  refresh_token: 'e2e-guardian-refresh-token',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: 4102444800, // 2100-01-01, comfortably non-expired
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

// One approved (published) generation job so IntakePage renders an "Assign more"
// row. statusPill maps storybook_status 'published' to the "Approved" pill.
const JOBS = {
  jobs: [
    {
      id: 'job-1',
      status: 'passed',
      storybook_id: 'story-1',
      storybook_status: 'published',
      version: 1,
      error: null,
      title: 'The Brave Little Fox',
      premise_snippet: 'A fox learns to be brave',
      age_band: '10-13',
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(
    ([key, session]) => {
      window.localStorage.setItem('auth_token', 'guardian-a')
      window.localStorage.setItem(key as string, session as string)
    },
    [SUPABASE_SESSION_KEY, JSON.stringify(GUARDIAN_SESSION)] as const
  )
})

test('assigning a sibling posts only the new profile id', async ({ page }) => {
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: ME }))
  await page.route('**/api/v1/generation-jobs', (route) =>
    route.fulfill({ json: JOBS })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: PROFILES })
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

  await page.goto('/guardian/intake')
  await page.getByRole('button', { name: /assign more/i }).first().click()
  await page.getByRole('checkbox', { name: /Reader A2/ }).click()
  await page.getByRole('button', { name: /^Assign$/ }).click()
  await expect.poll(() => body).toEqual({ profile_ids: ['p2'] })
})
