import { expect, test } from '@playwright/test'
import { mockMe, seedGuardianSession } from './support/auth'

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
 * far-future GoTrueClient session under the SDK's storage key (via
 * seedGuardianSession, see support/auth.ts) and mocks GET /v1/me to resolve a
 * guardian principal. getSession() returns a non-expired session from storage
 * without any network call, so no live Supabase backend is required. API
 * traffic is still page.route-mocked.
 */

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

// Two jobs. job-1 is approved (published) so IntakePage renders an "Assign more"
// row (statusPill maps storybook_status 'published' -> "Approved"). job-2 is a
// NEGATIVE CONTROL: needs_review with a non-null storybook_id but
// storybook_status 'in_review', so statusPill yields "Waiting for review". It
// passes the `storybook_id !== null` guard yet must be excluded by the
// `pill === 'Approved'` gate. Asserting exactly one "Assign more" button
// therefore makes that gate deletion-sensitive: dropping `pill === 'Approved'`
// would render the button on job-2 too and fail the count assertion.
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
    {
      id: 'job-2',
      status: 'needs_review',
      storybook_id: 'story-2',
      storybook_status: 'in_review',
      version: 1,
      error: null,
      title: 'A Story Awaiting Review',
      premise_snippet: 'Still with the safety reviewer',
      age_band: '10-13',
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('assigning a sibling posts only the new profile id', async ({ page }) => {
  await mockMe(page, {
    subject: 'guardian-a',
    family_id: 'fam-a',
    profile_ids: ['p1', 'p2'],
  })
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
  // Exactly one "Assign more" button: only the Approved job-1, never the
  // needs_review negative control job-2. Pins the pill gate (see JOBS comment).
  await expect(page.getByRole('button', { name: /assign more/i })).toHaveCount(1)
  await page.getByRole('button', { name: /assign more/i }).first().click()
  await page.getByRole('checkbox', { name: /Reader A2/ }).click()
  await page.getByRole('button', { name: /^Assign$/ }).click()
  await expect.poll(() => body).toEqual({ profile_ids: ['p2'] })
})
