import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin } from './support/auth'

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
  test.beforeEach(async ({ page }) => {
    await signInAsProdTestAdmin(page)
  })

  for (const [path, heading] of [
    ['/guardian', 'Family console'],
    ['/guardian/intake', 'Request a story'],
    ['/guardian/requests', 'Story requests'],
    ['/guardian/profiles', 'Profiles'],
  ] as const) {
    test(`${path} renders without the error boundary`, async ({ page }) => {
      await page.goto(path)
      await expect(
        page.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})
