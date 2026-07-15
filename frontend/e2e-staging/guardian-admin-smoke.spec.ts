import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsStagingTestUser, unlockParentalGateIfPresent } from './support/auth'

/**
 * Read-only render smoke for both adult consoles against the shared STAGING
 * Supabase project, using the two separate accounts scripts/seed_staging.py
 * creates (a guardian and an admin, not dual-role, unlike the prod tier's
 * single test account). Every listed page does only GETs on mount, so this
 * is non-destructive and safe to run unattended on a schedule.
 */
test.describe('guardian console renders on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsStagingTestUser(sharedPage, 'guardian')
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
  ] as const) {
    test(`${path} renders without the error boundary`, async () => {
      await sharedPage.goto(path)
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
    sharedPage = await browser.newPage()
    await signInAsStagingTestUser(sharedPage, 'admin')
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
      await sharedPage.goto(path)
      await unlockParentalGateIfPresent(sharedPage, 'admin')
      await expect(
        sharedPage.getByRole('heading', { name: 'Something went wrong', level: 1 })
      ).not.toBeVisible()
      await expect(sharedPage.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    })
  }
})
