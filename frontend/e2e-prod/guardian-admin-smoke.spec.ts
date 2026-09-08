import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin, unlockAdultGateIfPresent } from './support/auth'
import { expectConsoleHeading } from './support/diagnostics'
import { gotoResilient } from '../e2e-support/rate-limit'

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
 * small because every run authenticates a real account against a live system,
 * and this tier is no longer manual-only: it also runs unattended on a daily
 * cron (see playwright.e2e-prod.config.ts and .github/workflows/e2e-prod.yml),
 * so each page added here is paid for once a day, forever.
 */
test.describe('dual-role account across both adult consoles', () => {
  // Serial (also enforced by fullyParallel:false/workers:1 in
  // playwright.e2e-prod.config.ts, made explicit here): the tests share one
  // authenticated page rather than each logging into production separately, so
  // this suite performs one real login instead of many. One login plus a
  // shared page is necessary but NOT sufficient against the prod backend's
  // 60 rpm/IP limit (disabled only in ENVIRONMENT=local): each goto reloads
  // the SPA and every mount fans out into several GETs, so nine back-to-back
  // navigations can still burst past 60 in the rolling minute. gotoResilient
  // paces navigations under that ceiling and backs off/retries on any residual
  // 429, so a rate-limit blip never fails an otherwise-green run.
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsProdTestAdmin(sharedPage)
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  // Expected <h1> per path. /guardian/requests and /admin/requests render the
  // same StoryRequestQueue component but with different headings on purpose:
  // P-6b gave the guardian surface an explicit "Requests from your kids" to
  // disambiguate it from the sibling IntakePage, which previously shared the
  // exact "Story requests" wording; the admin cross-family queue keeps the
  // component's neutral default. Keep these two rows distinct. See
  // src/guardian/RequestsPage.tsx and src/admin/AdminRequestsPage.tsx.
  for (const [path, heading] of [
    ['/guardian', 'Family console'],
    ['/guardian/intake', 'Request a story'],
    ['/guardian/requests', 'Requests from your kids'],
    ['/guardian/books', 'Books'],
    ['/guardian/profiles', 'Profiles'],
    ['/admin', 'Review queue'],
    ['/admin/requests', 'Story requests'],
    ['/admin/moderation-thresholds', 'Moderation thresholds'],
    ['/admin/moderation-dashboard', 'Moderation dashboard'],
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await gotoResilient(sharedPage, path)
      // ADR-014: the adult subtree sits behind a single AdultGate. The real
      // sign-in in beforeAll warms it (sessionStorage, 5-min TTL) and that
      // warmth persists across these same-tab navigations, so this is usually
      // a no-op; it stays as a defensive unlock in case a navigation lands cold
      // (see unlockAdultGateIfPresent's doc comment).
      await unlockAdultGateIfPresent(sharedPage)
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expectConsoleHeading(sharedPage, heading)
    })
  }
})
