import { expect, test } from '@playwright/test'

import { makeGuardianSession, mockMe, mockOnboarding, seedGuardianSession } from './support/auth'

/**
 * Console e2e (C4a-4): unauthenticated-redirect smoke plus the signed-in
 * admin review-queue ordering and navigation matrix, now on the parallel
 * /admin surface (the review queue moved out of /guardian when admin
 * functions gained their own console).
 *
 * support/auth.ts now seeds a GoTrue session directly into localStorage
 * (the pattern proven in assignments.spec.ts), so the signed-in surface below
 * mounts without driving the real login form. The full behavioral matrix
 * (severity pills, forbidden/error states, empty state) still lives in
 * Vitest (src/admin/AdminConsolePage.test.tsx, src/admin/ReviewDetailPage.test.tsx);
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

test('an unauthenticated visit to an admin review detail URL also redirects to login', async ({
  page,
}) => {
  await page.goto('/admin/review/some-story')
  await expect(page).toHaveURL(/\/guardian\/login$/)
})

test('signing in after an unauthenticated deep link returns to that deep link, not the console default', async ({
  page,
}) => {
  // S-7(a): ProtectedRoute hands the login route `state={{ from: location }}`
  // (ProtectedRoute.tsx:67); LoginPage is supposed to honor it post-login
  // instead of always landing on the role-based console home. Drive the real
  // login form (like guardian-auth.spec.ts) so LoginPage's own `from`
  // resolution runs, not a seeded session that skips the login page entirely.
  await page.goto('/admin/review/some-story')
  await expect(page).toHaveURL(/\/guardian\/login$/)

  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({ json: makeGuardianSession('e2e-admin-deep-link-token') })
  )
  await mockOnboarding(page, { role: 'admin' })
  await mockMe(page, { role: 'admin' })
  // The review surface fetch is incidental to this test (only the post-login
  // destination is under test); fail it the same way the signed-in admin
  // console spec below does, and assert the resulting error state to prove
  // the app actually mounted ReviewDetailPage at the deep-linked URL rather
  // than merely matching the URL by coincidence.
  await page.route('**/api/v1/storybooks/some-story/review*', (route) =>
    route.fulfill({ status: 500, json: { detail: 'not under test here' } })
  )

  await page.getByLabel('Email').fill('admin@example.com')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/admin\/review\/some-story$/)
  await expect(
    page.getByText('We could not load this story for review. Please reload.')
  ).toBeVisible()
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

test.describe('signed-in admin console', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
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
    await page.goto('/admin')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText([
      'Flagged (review carefully)',
      'Ready to review',
      'Still processing',
    ])
    // 'flagged occurrences', not 'flags': this fixture carries no tiered
    // block/flag/advisory fields, so the row falls back to flagged_count, which
    // counts OCCURRENCES rather than findings (one merged finding spanning 380
    // nodes counted 380 times). RS-A3 renamed it so the row stops reporting a
    // number under a label that means something else.
    await expect(page.getByText('2 flagged occurrences')).toBeVisible()
    await expect(page.getByText('Clean')).toBeVisible()
    await expect(page.getByText('Processing…')).toBeVisible()
    await expect(page.getByText('Brewing a Tale')).toBeVisible()
  })

  test('opening a story navigates to its review detail', async ({ page }) => {
    await page.route('**/api/v1/storybooks/flag-1/review*', (route) =>
      route.fulfill({ status: 500, json: { detail: 'not under test here' } })
    )
    await page.goto('/admin')
    await page.getByRole('link', { name: /Scary Tale/ }).click()
    await expect(page).toHaveURL(/\/admin\/review\/flag-1$/)
  })

  test('a dual-role adult can switch between the guardian and admin consoles', async ({ page }) => {
    await mockMe(page, { role: 'guardian', is_admin: true })
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
    )
    await page.goto('/guardian')
    // exact: the family-console body also has an "Open the admin console" link
    // for dual-role adults; target the top-nav switcher specifically.
    await page.getByRole('link', { name: 'Admin console', exact: true }).click()
    await expect(page).toHaveURL(/\/admin$/)
    await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
    await page.getByRole('link', { name: 'Guardian console' }).click()
    await expect(page).toHaveURL(/\/guardian$/)
    await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  })

  test('a plain guardian visiting /admin is sent back to the guardian console', async ({
    page,
  }) => {
    await mockMe(page, { role: 'guardian' })
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
    )
    await page.goto('/admin')
    await expect(page).toHaveURL(/\/guardian$/)
    await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  })
})
