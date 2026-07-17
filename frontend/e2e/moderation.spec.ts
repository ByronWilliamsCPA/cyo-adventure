import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Mocked-tier E2E for the admin moderation dashboard/thresholds workflows.
 * Component tests already cover these pages in isolation
 * (ModerationThresholdsPage.test.tsx, ModerationDashboardPage.test.tsx); this
 * closes the coverage-matrix gap for an end-to-end workflow spec: navigate,
 * add/remove a threshold override, save the noise floor, and apply a
 * dashboard suggestion, each verified against the real routed app.
 */

const EMPTY_THRESHOLDS = {
  default_min_verdict: 'flag',
  rows: [] as { age_band: string; category: string; min_verdict: string; min_score: number | null }[],
  known_categories: ['violence', 'language'],
}

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
})

test.describe('moderation thresholds', () => {
  test('adds an override and it appears in the table', async ({ page }) => {
    let thresholds = { ...EMPTY_THRESHOLDS }
    // Two distinct route patterns: Playwright's single `*` glob does not cross
    // a `/`, so a combined 'moderation-thresholds*' pattern would match the
    // bare list GET but never the per-band PUT/DELETE path below it.
    await page.route('**/api/v1/admin/moderation-thresholds', (route) =>
      route.fulfill({ json: thresholds })
    )
    await page.route('**/api/v1/admin/moderation-thresholds/*', (route) => {
      if (route.request().method() !== 'PUT') return route.fulfill({ status: 405 })
      const body = route.request().postDataJSON() as { min_verdict: string; min_score: number | null }
      const url = new URL(route.request().url())
      const category = url.searchParams.get('category') ?? ''
      const ageBand = url.pathname.split('/moderation-thresholds/')[1] ?? ''
      thresholds = {
        ...thresholds,
        rows: [
          ...thresholds.rows,
          { age_band: ageBand, category, min_verdict: body.min_verdict, min_score: body.min_score },
        ],
      }
      return route.fulfill({ json: { age_band: ageBand, category, ...body } })
    })
    await page.route('**/api/v1/admin/moderation/noise-floor', (route) =>
      route.fulfill({ json: { value: 0.2 } })
    )

    await page.goto('/admin/moderation-thresholds')
    await expect(page.getByRole('heading', { name: 'Moderation thresholds' })).toBeVisible()
    await expect(page.getByText('No overrides yet.')).toBeVisible()

    await page.getByLabel('Category').fill('violence')
    await page.getByLabel('Surfaces at').selectOption('block')
    await page.getByRole('button', { name: 'Save override' }).click()

    // exact: true, else this also matches the row's "Remove violence
    // override for ..." button cell (substring match on role name).
    await expect(page.getByRole('cell', { name: 'violence', exact: true })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'block', exact: true })).toBeVisible()
    await expect(page.getByLabel('Category')).toHaveValue('')
  })

  test('removes an existing override', async ({ page }) => {
    let thresholds = {
      ...EMPTY_THRESHOLDS,
      rows: [{ age_band: '5-8', category: 'violence', min_verdict: 'block', min_score: null }],
    }
    await page.route('**/api/v1/admin/moderation-thresholds', (route) =>
      route.fulfill({ json: thresholds })
    )
    await page.route('**/api/v1/admin/moderation-thresholds/*', (route) => {
      if (route.request().method() !== 'DELETE') return route.fulfill({ status: 405 })
      thresholds = { ...thresholds, rows: [] }
      return route.fulfill({ json: thresholds })
    })
    await page.route('**/api/v1/admin/moderation/noise-floor', (route) =>
      route.fulfill({ json: { value: 0.2 } })
    )

    await page.goto('/admin/moderation-thresholds')
    await expect(page.getByRole('cell', { name: 'violence', exact: true })).toBeVisible()
    // Removing an override changes live surfacing behavior for a whole
    // age band/category, so it is gated behind a confirm dialog (main's
    // 2026-07-16 UX pass, same pattern as approve/decline); the delete
    // fires only from "Confirm remove", not the row button itself.
    await page.getByRole('button', { name: 'Remove violence override for 5-8' }).click()
    await page.getByRole('button', { name: 'Confirm remove' }).click()
    await expect(page.getByText('No overrides yet.')).toBeVisible()
  })

  test('saves the admin noise floor', async ({ page }) => {
    await page.route('**/api/v1/admin/moderation-thresholds*', (route) =>
      route.fulfill({ json: EMPTY_THRESHOLDS })
    )
    let savedValue: number | null = null
    await page.route('**/api/v1/admin/moderation/noise-floor', (route) => {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON() as { value: number }
        savedValue = body.value
        return route.fulfill({ json: { value: body.value } })
      }
      return route.fulfill({ json: { value: 0.2 } })
    })

    await page.goto('/admin/moderation-thresholds')
    const floorInput = page.getByLabel('Noise floor (0-1)')
    await floorInput.fill('0.35')
    // Saving the noise floor affects every reviewer, so it too is gated
    // behind a confirm dialog (main's 2026-07-16 UX pass); the PUT fires
    // only from "Confirm noise floor".
    await page.getByRole('button', { name: 'Save noise floor' }).click()
    await page.getByRole('button', { name: 'Confirm noise floor' }).click()

    await expect.poll(() => savedValue).toBe(0.35)
  })
})

test.describe('moderation dashboard', () => {
  test('applies a threshold suggestion and refreshes the dashboard', async ({ page }) => {
    const dashboard = { insights: [], recent_changes: [] }
    let suggestions = {
      min_decided_versions: 5,
      min_override_rate: 0.5,
      suggestions: [
        {
          age_band: '5-8',
          category: 'violence',
          decided_versions: 10,
          released_versions: 6,
          override_rate: 0.6,
          current_min_verdict: 'advisory',
          current_min_score: null,
          suggested_min_verdict: 'flag',
        },
      ],
    }
    let upsertPosted = false
    await page.route('**/api/v1/admin/moderation/dashboard', (route) =>
      route.fulfill({ json: dashboard })
    )
    await page.route('**/api/v1/admin/moderation/suggestions', (route) =>
      route.fulfill({ json: suggestions })
    )
    await page.route('**/api/v1/admin/moderation-thresholds/*', (route) => {
      if (route.request().method() === 'PUT') {
        upsertPosted = true
        suggestions = { ...suggestions, suggestions: [] }
        return route.fulfill({
          json: { age_band: '5-8', category: 'violence', min_verdict: 'flag', min_score: null },
        })
      }
      return route.fulfill({ status: 405 })
    })

    await page.goto('/admin/moderation-dashboard')
    await expect(page.getByRole('heading', { name: 'Moderation dashboard' })).toBeVisible()
    await expect(page.getByText('violence in 5-8')).toBeVisible()

    // Applying a suggestion changes live surfacing behavior, so it too is
    // gated behind a confirm dialog (main's 2026-07-16 UX pass); the upsert
    // fires only from "Confirm apply", not the row button itself.
    await page
      .getByRole('button', { name: 'Apply: raise violence (5-8) to flag' })
      .click()
    await page.getByRole('button', { name: 'Confirm apply' }).click()

    await expect.poll(() => upsertPosted).toBe(true)
    await expect(page.getByText('No threshold suggestions right now.')).toBeVisible()
  })
})
