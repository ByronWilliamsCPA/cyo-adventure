import { expect, test } from '@playwright/test'

import { requireBackend } from './real-stack'

/**
 * Real-API cross-family authorization: the mocked tier cannot exercise this
 * at all, since authorize_profile(principal, parsed) (library.py:262) is
 * server-side authorization, not frontend behavior a route mock stands in
 * for. Seeded by scripts/seed_dev_data.py's second, unrelated family.
 */

const UNRELATED_PROFILE_ID = '22222222-2222-2222-2222-222222222222'

test.beforeEach(async ({ context }) => {
  await requireBackend()
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test("a hand-edited URL into another family's profile is rejected, not served", async ({
  page,
}) => {
  // #ASSUME: timing dependencies: LibraryPage fires its /api/v1/library
  // fetch during the initial render, which can complete before a listener
  // registered after navigation ever attaches (waitForLoadState('networkidle')
  // resolves only once that request has already settled).
  // #VERIFY: registering waitForResponse before goto() catches the request
  // as it happens, matching the standard Playwright wait-then-navigate order.
  const apiResponsePromise = page.waitForResponse(
    (res) => res.url().includes(`/api/v1/library`) && res.url().includes(UNRELATED_PROFILE_ID),
    { timeout: 5_000 }
  )
  // #ASSUME: data integrity: page.goto()'s own response is the SPA's static
  // document (client-side routing under Vite preview), which is 200 for any
  // path regardless of API authorization outcome, so it cannot stand in for
  // "was the other family's content served."
  // #VERIFY: assert on the structural signals LibraryPage renders only in
  // its ready state (kid-reads.spec.ts uses the same "Continue Reading"
  // region and .library__shelf selectors for a successful library), not on
  // unverified error-state copy.
  await page.goto(`/library/${UNRELATED_PROFILE_ID}`)
  const apiResponse = await apiResponsePromise

  // No waitForLoadState('networkidle') here: the specific /api/v1/library
  // response is already awaited above, and the toHaveCount(0) assertions below
  // auto-retry, so the networkidle wait (which Playwright discourages as
  // flake-prone) adds nothing.
  expect(apiResponse.status()).toBe(403)
  await expect(page.getByRole('region', { name: 'Continue Reading' })).toHaveCount(0)
  await expect(page.locator('.library__shelf > li')).toHaveCount(0)
})
