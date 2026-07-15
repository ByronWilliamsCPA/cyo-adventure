import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { authorizeDevice, requireBackend } from './real-stack'

/**
 * The real ADR-005 write path. The GoTrue session is storage-seeded with an
 * access_token equal to a seeded authn_subject; in ENVIRONMENT=local the
 * backend trusts it as the subject, so /me, the queue, and approve are all
 * REAL responses; unlike tier 1, no mockMe/route mocks appear anywhere here.
 * Serial: approve mutates the database and the next test observes it.
 *
 * The review queue and per-story review are admin-capability-only on the real
 * backend (a plain guardian token gets a 403; see
 * src/cyo_adventure/api/approval.py) and now live on the parallel /admin
 * console. So the first test asserts a plain guardian is bounced off /admin
 * back to the family console, and the admin tests drive the real /admin queue
 * before the shared admin-approve test. dev-admin is an admin-only adult;
 * dev-dual is a guardian who also holds the is_admin capability.
 */

test.describe.configure({ mode: 'serial' })

test.beforeEach(async () => {
  await requireBackend()
})

test('a plain guardian is denied the admin console and lands on the family console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  await expect(page.getByText(/safety reviewer/i)).toBeVisible()
})

test('the admin sees the seeded in-review story in the real queue', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto('/admin')
  await expect(page.getByRole('link', { name: /The Bridge Builder/ })).toBeVisible()
  await expect(page.getByText('1 flagged')).toBeVisible()
})

test('a dual-role adult can reach the admin queue from the guardian console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-dual')
  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  await page.getByRole('link', { name: 'Admin console', exact: true }).click()
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('link', { name: /The Bridge Builder/ })).toBeVisible()
})

test('the admin approves the story through the real API', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto('/admin/review/s_bridge_builder')
  await expect(page.getByRole('heading', { name: 'The Bridge Builder' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Flagged passages' })).toBeVisible()

  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/admin$/)

  // Persisted, not optimistic: after reload the story is out of the queue.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByRole('link', { name: /The Bridge Builder/ })).toHaveCount(0)
})

test('the approved story reaches the child library', async ({ page, context }) => {
  // The kid surface is gated by DeviceAuthorizedRoute (ADR-014); mint and inject
  // a real grant before the child bearer so /kids is reachable.
  await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page.getByText('The Bridge Builder')).toBeVisible()
})
