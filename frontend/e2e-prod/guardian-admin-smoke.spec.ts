import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin, unlockParentalGateIfPresent } from './support/auth'

/**
 * Read-only render smoke for both adult consoles on LIVE production, driven by
 * the dual-role test account (role='guardian' + is_admin=true), provisioned in
 * its own isolated "E2E Test Family" so no real family data is touched. It
 * began as the PR #236 regression guard for the admin-only-account
 * crash (an admin with no family-scoped profiles threw the error boundary on
 * every /guardian/* subpage); since the account is now dual-role it instead
 * asserts the broader PR #236 promise: a single adult holding both capabilities
 * reaches every page of BOTH consoles without hitting the error boundary.
 *
 * Every listed page does only GETs on mount, so navigating and asserting a
 * heading is non-destructive. /admin/review/:id is deliberately excluded (it
 * needs a real storybook id and its heading is the dynamic story title). Kept
 * small and manual-trigger-only, never wired into CI, since every run
 * authenticates a real account against a live system.
 */
test.describe('dual-role account across both adult consoles', () => {
  // Serial (also enforced by fullyParallel:false/workers:1 in
  // playwright.e2e-prod.config.ts, made explicit here): the tests share one
  // authenticated page rather than each logging into production separately, so
  // this suite performs one real login instead of many. Keeping the page count
  // modest also stays comfortably under the prod backend's 60 rpm/IP limit
  // (that limiter is disabled only in ENVIRONMENT=local).
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsProdTestAdmin(sharedPage)
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  for (const [path, heading] of [
    ['/guardian', 'Family console'],
    ['/guardian/intake', 'Request a story'],
    ['/guardian/requests', 'Story requests'],
    ['/guardian/books', 'Books'],
    ['/guardian/profiles', 'Profiles'],
    ['/admin', 'Review queue'],
    ['/admin/requests', 'Story requests'],
    ['/admin/moderation-thresholds', 'Moderation thresholds'],
    ['/admin/moderation-dashboard', 'Moderation dashboard'],
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await sharedPage.goto(path)
      // ADR-014: the adult subtree sits behind a single AdultGate. The real
      // sign-in in beforeAll warms it (sessionStorage, 5-min TTL) and that
      // warmth persists across these same-tab navigations, so this is usually
      // a no-op; it stays as a defensive unlock in case a navigation lands cold
      // (see unlockParentalGateIfPresent's doc comment).
      await unlockParentalGateIfPresent(sharedPage)
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(sharedPage.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})
