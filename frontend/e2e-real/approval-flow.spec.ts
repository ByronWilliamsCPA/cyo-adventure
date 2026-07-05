import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { requireBackend } from './real-stack'

/**
 * The real ADR-005 write path. The GoTrue session is storage-seeded with an
 * access_token equal to a seeded authn_subject; in ENVIRONMENT=local the
 * backend trusts it as the subject, so /me, the queue, and approve are all
 * REAL responses; unlike tier 1, no mockMe/route mocks appear anywhere here.
 * Serial: approve mutates the database and the next test observes it.
 *
 * Deviation from the original plan: GET /api/v1/review-queue and
 * GET /api/v1/storybooks/{id}/review are admin-only on the real backend (a
 * guardian token gets a 403; see src/cyo_adventure/api/approval.py). A plain
 * guardian can never see the real queue, so the first test below asserts the
 * ConsolePage 403 branch (the reviewer notice) instead, and a second test
 * covers the admin's real queue view before the shared admin-approve test.
 */

test.describe.configure({ mode: 'serial' })

test.beforeEach(async () => {
  await requireBackend()
})

test('a guardian visiting the console sees the reviewer notice, not the queue', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByText(/safety reviewer/i)).toBeVisible()
  await expect(page.getByText('The Bridge Builder')).not.toBeVisible()
})

test('the admin sees the seeded in-review story in the real queue', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto('/guardian')
  await expect(page.getByRole('link', { name: /The Bridge Builder/ })).toBeVisible()
  await expect(page.getByText('1 flagged')).toBeVisible()
})

test('the admin approves the story through the real API', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto('/guardian/review/s_bridge_builder')
  await expect(page.getByRole('heading', { name: 'The Bridge Builder' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Flagged passages' })).toBeVisible()

  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/guardian$/)

  // Persisted, not optimistic: after reload the story is out of the queue.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByRole('link', { name: /The Bridge Builder/ })).toHaveCount(0)
})

test('the approved story reaches the child library', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
  await page.goto('/')
  await page.getByText('Dev Reader').click()
  await expect(page.getByText('The Bridge Builder')).toBeVisible()
})
