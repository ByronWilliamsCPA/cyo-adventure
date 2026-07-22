import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { requireBackend } from './real-stack'

/**
 * Real-API provider-allowlist CRUD (Phase 3.1 write-path backfill): an admin
 * adds, disables, and removes a (provider, model_id) entry through the real
 * POST/PUT/DELETE /api/v1/admin/provider-allowlist endpoints, no route
 * mocks (unlike provider-allowlist.spec.ts in the mocked tier). This is a
 * billing/cost-control gate (WS-C PR #170): only allowlisted pairs may be
 * chosen on the authoring queue, so a real add/remove here is a genuine
 * money-relevant write, not just a UI affordance.
 *
 * The second test asserts the REAL authorization gate rather than just the
 * write path: a plain guardian is denied this admin-only settings page by
 * the real /v1/me role, mirroring approval-flow.spec.ts's plain-guardian
 * check for the parallel /admin console gate.
 */

// #EDGE: data-integrity: a timestamp-suffixed model id keeps this idempotent
// across the two consecutive runs the validation step requires; the seeded
// default allowlist rows (scripts/seed_dev_data.py's DEFAULT_ALLOWLIST) are
// never touched by this spec, and the add/remove pair below leaves no extra
// row behind on a normal (non-failing) run either way.
// #VERIFY: the test removes the row it creates before finishing.

test.beforeEach(async () => {
  await requireBackend()
})

test('an admin adds, disables, and removes a real provider-allowlist entry, all persisting across reload', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-admin')
  const modelId = `e2e-real-check-${Date.now()}`

  await page.goto('/admin/provider-allowlist')
  await expect(page.getByRole('heading', { name: 'Provider allowlist' })).toBeVisible()

  await page.getByLabel('Provider').selectOption('ollama')
  await page.getByLabel('Model id').fill(modelId)
  await page.getByRole('button', { name: 'Add to allowlist' }).click()

  // exact: true, else this also matches the row's own "Disable/Remove
  // <modelId>" button cell (substring match on role name).
  await expect(page.getByRole('cell', { name: modelId, exact: true })).toBeVisible()
  // Scoped to this test's own row: a bare page-wide "Enabled" cell match
  // (via .first()) would pass even if some OTHER pre-seeded row were
  // enabled and this one were not, so it would not actually prove the real
  // POST enabled the row this test created.
  const row = page.locator('tr', { hasText: modelId })
  await expect(row.getByText('Enabled', { exact: true })).toBeVisible()

  // Persisted, not optimistic: after reload the real POST's row is still there.
  await page.reload()
  await expect(page.getByRole('cell', { name: modelId, exact: true })).toBeVisible()

  await page.getByRole('button', { name: `Disable ${modelId}` }).click()
  await expect(row.getByText('Disabled', { exact: true })).toBeVisible()

  await page.reload()
  await expect(
    page.locator('tr', { hasText: modelId }).getByText('Disabled', { exact: true })
  ).toBeVisible()

  await page.getByRole('button', { name: `Remove ${modelId}` }).click()
  await expect(page.getByRole('cell', { name: modelId, exact: true })).toHaveCount(0)

  await page.reload()
  await expect(page.getByRole('cell', { name: modelId, exact: true })).toHaveCount(0)
})

test('a plain guardian visiting the provider allowlist page is sent back to the guardian console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/admin/provider-allowlist')
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
})
