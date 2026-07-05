import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian console (C4a-4) e2e: unauthenticated-redirect smoke plus the
 * signed-in queue-ordering and navigation matrix.
 *
 * support/auth.ts now seeds a GoTrue session directly into localStorage
 * (the pattern proven in assignments.spec.ts), so the signed-in surface below
 * mounts without driving the real login form. The full behavioral matrix
 * (severity pills, forbidden/error states, empty state) still lives in
 * Vitest (src/guardian/ConsolePage.test.tsx, src/guardian/ReviewDetailPage.test.tsx);
 * this spec covers only what Vitest cannot: real routing and navigation.
 *
 * The placeholder VITE_SUPABASE_* values in playwright.config.ts exist so the
 * guardian lazy chunk loads (supabaseClient.ts throws without them) and the
 * real ProtectedRoute redirect can run; getSession() finds no persisted
 * session and resolves null without any network call.
 */

test('an unauthenticated visit to /guardian redirects to the guardian login', async ({ page }) => {
  await page.goto('/guardian')
  await expect(page).toHaveURL(/\/guardian\/login$/)
  // The login page rendered (not the RouteError boundary), proving the
  // guardian chunk loaded and the redirect came from ProtectedRoute.
  await expect(page.getByText(/sign in/i).first()).toBeVisible()
})

test('an unauthenticated visit to a review detail URL also redirects to login', async ({
  page,
}) => {
  await page.goto('/guardian/review/some-story')
  await expect(page).toHaveURL(/\/guardian\/login$/)
})

const FLAGGED = {
  storybook_id: 'flag-1',
  title: 'Scary Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 2,
  summary: {
    count: 2,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
}
const READY = {
  storybook_id: 'ready-1',
  title: 'Gentle Tale',
  status: 'in_review',
  version: 1,
  screened: true,
  flagged_count: 0,
  summary: {
    count: 0,
    hard_block: false,
    soft_flag: false,
    repaired: false,
    reviewer_independent: false,
  },
}
const RUNNING_JOB = { id: 'j1', status: 'running', title: 'Brewing a Tale', premise_snippet: 'x' }

test.describe('signed-in console', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page)
    // READY intentionally listed before FLAGGED: ordering must come from the
    // UI's grouping, not from response order.
    await page.route('**/api/v1/review-queue', (route) =>
      route.fulfill({ json: { items: [READY, FLAGGED] } })
    )
    await page.route('**/api/v1/generation-jobs', (route) =>
      route.fulfill({ json: { jobs: [RUNNING_JOB] } })
    )
  })

  test('groups the queue Flagged, then Ready, then Still processing', async ({ page }) => {
    await page.goto('/guardian')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText([
      'Flagged (review carefully)',
      'Ready to review',
      'Still processing',
    ])
    await expect(page.getByText('2 flagged')).toBeVisible()
    await expect(page.getByText('Clean')).toBeVisible()
    await expect(page.getByText('Processing…')).toBeVisible()
    await expect(page.getByText('Brewing a Tale')).toBeVisible()
  })

  test('opening a story navigates to its review detail', async ({ page }) => {
    await page.route('**/api/v1/storybooks/flag-1/review*', (route) =>
      route.fulfill({ status: 500, json: { detail: 'not under test here' } })
    )
    await page.goto('/guardian')
    await page.getByRole('link', { name: /Scary Tale/ }).click()
    await expect(page).toHaveURL(/\/guardian\/review\/flag-1$/)
  })
})
