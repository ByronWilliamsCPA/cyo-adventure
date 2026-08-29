import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { stagingStorageStatePath } from './support/auth-storage'
import { unlockParentalGateIfPresent } from './support/auth'
import { gotoResilient } from '../e2e-support/rate-limit'

/**
 * Read-only render smoke for both adult consoles against the shared STAGING
 * Supabase project, using the two separate accounts scripts/seed_staging.py
 * creates (a guardian and an admin, not dual-role, unlike the prod tier's
 * single test account). Every listed page does only GETs on mount, so this
 * is non-destructive and safe to run unattended on a schedule.
 *
 * Non-destructive is not the same as cheap. Staging enforces the same
 * 60 rpm/IP limit as production (`app.py` turns the limiter on for every
 * `ENVIRONMENT != "local"` deployment), each goto reloads the SPA, and every
 * mount fans out into several GETs, so nine back-to-back navigations from one
 * runner IP can burst past the ceiling. gotoResilient paces them under it and
 * backs off on any residual 429; see e2e-support/rate-limit.ts.
 *
 * Each `beforeAll` below restores a pre-authenticated session from disk
 * (`stagingStorageStatePath`) rather than signing in through the login form.
 * The sign-in itself, and the one write this tier performs (clearing the
 * ADR-018 consent interstitial the first time the seeded guardian signs in;
 * see `acceptGuardianConsentIfPresent` in `./support/auth`), now happen once
 * each, up front, in `e2e-staging/auth.setup.ts`. That write's effect is
 * server-tracked and read fresh from `/v1/me` on every session
 * (`src/auth/AuthContext.tsx`'s `syncPrincipal`), so a session restored here
 * still resolves past `ProtectedRoute` without re-consenting.
 */
test.describe('guardian console renders on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage({ storageState: stagingStorageStatePath('guardian') })
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  for (const [path, heading] of [
    ['/guardian', 'Family console'],
    ['/guardian/intake', 'Request a story'],
    ['/guardian/requests', 'Requests from your kids'],
    ['/guardian/books', 'Books'],
    ['/guardian/profiles', 'Profiles'],
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await gotoResilient(sharedPage, path)
      await unlockParentalGateIfPresent(sharedPage, 'guardian')
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(sharedPage.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})

test.describe('admin console renders on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage({ storageState: stagingStorageStatePath('admin') })
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  for (const [path, heading] of [
    ['/admin', 'Review queue'],
    ['/admin/requests', 'Story requests'],
    ['/admin/moderation-thresholds', 'Moderation thresholds'],
    ['/admin/moderation-dashboard', 'Moderation dashboard'],
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await gotoResilient(sharedPage, path)
      await unlockParentalGateIfPresent(sharedPage, 'admin')
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(sharedPage.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})
