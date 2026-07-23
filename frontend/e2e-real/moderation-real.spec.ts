import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

/**
 * Real-API moderation thresholds/dashboard workflow: add and remove a
 * threshold override, update the noise floor, and confirm the dashboard/
 * suggestions endpoints return real (empty) data, all against the real
 * backend rather than route mocks. Closes part of the coverage-matrix gap
 * for e2e-real coverage of this journey.
 *
 * The "a suggestion actually appears" path is NOT covered here: per
 * src/cyo_adventure/moderation/insights.py, a suggestion needs at least 5
 * decided (released/sent-back) versions with an overridable finding in the
 * same (age_band, category), and neither scripts/seed_dev_data.py nor
 * seed_staging.py create that corpus. Building it would mean seeding 5+
 * storybook versions with moderation reports and pipeline events purely for
 * this test, which is a bigger, separate addition; tracked as a follow-up
 * rather than done here.
 */

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context, 'dev-admin')
})

test('an admin adds and removes a real threshold override', async ({ page }) => {
  await page.goto('/admin/moderation-thresholds')
  await expect(page.getByRole('heading', { name: 'Moderation thresholds' })).toBeVisible()

  // #EDGE: data-integrity: this test creates and then removes a real row so
  // a reused dev stack is not left with an extra override after the run;
  // the category name is unlikely to collide with anything a developer
  // added by hand, but isn't guaranteed unique across parallel runs.
  const category = `e2e-real-check-${Date.now()}`
  await page.getByLabel('Category').fill(category)
  await page.getByLabel('Surfaces at').selectOption('block')
  await page.getByRole('button', { name: 'Save override' }).click()

  // P4-3: this dynamic category is not in known_categories, so the create is
  // gated by a confirmation dialog (the "never matches a typo" warning). The
  // stale version of this test clicked Save and asserted the row, but the POST
  // never fired without confirming, so it was not exercising the real create
  // at all. Click through the dialog so the override is actually persisted.
  await expect(page.getByRole('dialog')).toContainText(
    `Create override for new category '${category}'?`
  )
  await page.getByRole('button', { name: 'Create new-category override' }).click()

  const bandCell = page.getByRole('cell', { name: category, exact: true })
  await expect(bandCell).toBeVisible()

  // Removal is likewise gated by a confirm dialog naming the default the band
  // reverts to; click through it so the DELETE actually fires (same stale gap).
  await page.getByRole('button', { name: new RegExp(`^Remove ${category} override for`) }).click()
  await page.getByRole('button', { name: 'Confirm remove' }).click()
  await expect(bandCell).not.toBeVisible()
})

test('an admin updates the real noise floor and it persists across reload', async ({ page }) => {
  await page.goto('/admin/moderation-thresholds')
  const floorInput = page.getByLabel('Noise floor (0-1)')
  await expect(floorInput).toBeVisible()

  await floorInput.fill('0.3')
  await page.getByRole('button', { name: 'Save noise floor' }).click()

  // P4-3: the noise-floor save now routes through a confirmation dialog that
  // spells out the consequence before the PUT fires. The stale test clicked
  // Save and asserted the value, but nothing persisted without confirming, so
  // the reload assertion below was passing on the pre-fill value. Confirm so
  // the PUT actually lands and the reload proves real persistence.
  await page.getByRole('button', { name: 'Confirm noise floor' }).click()
  await expect(floorInput).toHaveValue('0.3')

  await page.reload()
  await expect(page.getByLabel('Noise floor (0-1)')).toHaveValue('0.3')
})

test('the real moderation dashboard renders with no qualifying suggestions yet', async ({
  page,
}) => {
  await page.goto('/admin/moderation-dashboard')
  await expect(page.getByRole('heading', { name: 'Moderation dashboard' })).toBeVisible()
  // The dev/staging seed data has no corpus of 5+ decided versions with an
  // overridable finding in the same age band/category (see file header), so
  // the real suggestions list is genuinely empty; this is the real backend
  // confirming the same "no suggestion below volume" gate
  // tests/integration/test_moderation_dashboard_api.py already proves at
  // the pytest level.
  await expect(page.getByText('No threshold suggestions right now.')).toBeVisible()
})
