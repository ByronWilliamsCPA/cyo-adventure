import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin, unlockParentalGateIfPresent } from './support/auth'

/**
 * Regression guard for the admin-only-account crash fixed by PR #236: an
 * account with role='admin' and no family-scoped profiles used to throw the
 * app's generic error boundary on every /guardian/* subpage except the
 * console itself. Runs against LIVE production (see frontend/README.md's
 * "Real-backend e2e" section for the local-only tiers this is NOT); keep
 * this suite small and manual-trigger-only, never wired into CI, since every
 * run authenticates as a real account against a live system.
 */
test.describe('admin-only account on the guardian surfaces', () => {
  // Serial (also enforced by fullyParallel:false/workers:1 in
  // playwright.e2e-prod.config.ts, made explicit here): the 4 tests share
  // one authenticated page rather than each logging into production
  // separately, so this suite performs one real login instead of four.
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
    ['/guardian/profiles', 'Profiles'],
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await sharedPage.goto(path)
      // ADR-014: all four of these adult paths (including intake and requests,
      // which pre-dated the change as ungated) now sit behind the single
      // AdultGate. In practice the real sign-in in beforeAll already warmed the
      // gate, and that warmth persists across these same-tab navigations in
      // sessionStorage, so this call is usually a no-op; it stays as a
      // defensive unlock in case a navigation lands cold (see
      // unlockParentalGateIfPresent's doc comment).
      await unlockParentalGateIfPresent(sharedPage)
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(sharedPage.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})
