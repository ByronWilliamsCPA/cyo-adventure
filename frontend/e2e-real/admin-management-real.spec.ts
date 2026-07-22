import { expect, test, type Page } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { requireBackend } from './real-stack'

/**
 * Real-API WS-J admin user-management (Phase 3.1 write-path backfill): the
 * Kids tab's real create/edit/deactivate round-trip through
 * /api/v1/admin/profiles, no route mocks (unlike admin-user-management.spec.ts
 * in the mocked tier, which covers the Users tab). Kids was chosen over the
 * other three tabs as the highest-value real write within WS-J's scope: it
 * is the one console-only path (there is no guardian-facing equivalent for
 * creating a profile in a family other than your own) and its deactivate
 * toggle gates whether a profile can still mint a reading session at all
 * (api/child_sessions.py), so a stale client-only "success" would mask a
 * real safety-relevant regression. Kept to this one tab per the work order's
 * "keep it focused" guidance; Users/Families/Connections are not covered
 * here.
 *
 * The tab state (`UserManagementPage`'s `useState<TabKey>`) is
 * component-local, not URL-derived, so a full page reload always lands back
 * on the "Users" tab; every persistence check below re-clicks "Kids" after
 * navigating.
 *
 * #ASSUME: data-integrity: a timestamp-suffixed display name keeps the
 * create idempotent across the two consecutive runs the validation step
 * requires, the same rationale as guardian-profile-crud-real.spec.ts.
 * #VERIFY: the profile this test creates is left deactivated, not deleted
 * (admin/profiles.py has no delete route), so a reused dev stack accumulates
 * one harmless deactivated row per run rather than a stale active one.
 */

test.beforeEach(async () => {
  await requireBackend()
})

async function openKidsTab(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Kids' }).click()
}

test('an admin creates, edits, and deactivates a real kid profile in another family, all persisting across reload', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-admin')
  const originalName = `E2E Admin Kid ${Date.now()}`
  const editedName = `${originalName} Edited`

  await page.goto('/admin/users')
  await expect(page.getByRole('heading', { name: 'User management' })).toBeVisible()
  await openKidsTab(page)

  await page.getByLabel('Family').selectOption({ label: 'Dev Family' })
  await page.getByLabel('Name').fill(originalName)
  await page.getByLabel('Age band').selectOption('8-11')
  await page.getByRole('button', { name: 'Create profile' }).click()

  let row = page.locator('tbody tr', { hasText: originalName })
  await expect(row).toBeVisible()
  await expect(row.getByText('Dev Family')).toBeVisible()
  await expect(row.getByText('active', { exact: true })).toBeVisible()

  // Persisted, not optimistic: after reload (and re-selecting the tab) the
  // real POST's row is still there.
  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: originalName })
  await expect(row).toBeVisible()

  // Edit: rename the profile and change its age band through the real PATCH.
  // Once in edit mode the Name cell is an <input>, not text, so `row`'s
  // hasText-based locator can no longer find it (an input's value is not
  // part of its element's text content); the aria-labels below are unique
  // page-wide (built from the timestamped originalName), so address them
  // directly instead of re-scoping through `row`.
  await row.getByRole('button', { name: 'Edit' }).click()
  await page.getByLabel(`Name for ${originalName}`).fill(editedName)
  await page.getByLabel(`Age band for ${originalName}`).selectOption('13-16')
  await page.getByRole('button', { name: 'Save' }).click()

  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row).toBeVisible()
  await expect(row.getByText('13-16', { exact: true })).toBeVisible()

  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row).toBeVisible()
  await expect(row.getByText('13-16', { exact: true })).toBeVisible()

  // Deactivate: toggles the same real status field the child-session mint
  // gate reads (api/child_sessions.py).
  await row.getByRole('button', { name: 'Deactivate' }).click()
  await expect(row.getByText('deactivated', { exact: true })).toBeVisible()

  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row.getByText('deactivated', { exact: true })).toBeVisible()
})

test('a plain guardian visiting the admin user-management console is sent back to the guardian console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
})
