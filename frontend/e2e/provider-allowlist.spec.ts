import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Mocked-tier E2E for the admin provider-allowlist settings page: add an
 * entry, toggle it disabled, then remove it, against the routed app.
 */

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
})

test('an admin adds, disables, and removes a provider allowlist entry', async ({ page }) => {
  let rows: {
    id: string
    provider: string
    model_id: string
    enabled: boolean
    display_name: string | null
  }[] = []
  let nextId = 1

  await page.route('**/api/v1/admin/provider-allowlist', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { rows } })
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as {
        provider: string
        model_id: string
        display_name: string | null
      }
      const created = { id: `a${nextId}`, enabled: true, ...body }
      nextId += 1
      rows = [...rows, created]
      return route.fulfill({ status: 201, json: created })
    }
    return route.fulfill({ status: 405 })
  })
  await page.route('**/api/v1/admin/provider-allowlist/*', (route) => {
    const method = route.request().method()
    if (method === 'PUT') {
      const body = route.request().postDataJSON() as { enabled: boolean; display_name: string | null }
      const id = route.request().url().split('/provider-allowlist/')[1]
      rows = rows.map((r) => (r.id === id ? { ...r, ...body } : r))
      return route.fulfill({ json: rows.find((r) => r.id === id) })
    }
    if (method === 'DELETE') {
      const id = route.request().url().split('/provider-allowlist/')[1]
      rows = rows.filter((r) => r.id !== id)
      return route.fulfill({ json: { rows } })
    }
    return route.fulfill({ status: 405 })
  })

  await page.goto('/admin/provider-allowlist')
  await expect(page.getByRole('heading', { name: 'Provider allowlist' })).toBeVisible()
  await expect(page.getByText('No allowlist entries yet.')).toBeVisible()

  await page.getByLabel('Provider').selectOption('ollama')
  await page.getByLabel('Model id').fill('qwen2.5:14b')
  await page.getByRole('button', { name: 'Add to allowlist' }).click()

  // exact: true, else this also matches the row's "Disable/Remove
  // qwen2.5:14b" button cell (substring match on role name).
  await expect(page.getByRole('cell', { name: 'qwen2.5:14b', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Enabled', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Disable qwen2.5:14b' }).click()
  await expect(page.getByRole('cell', { name: 'Disabled', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Remove qwen2.5:14b' }).click()
  await expect(page.getByText('No allowlist entries yet.')).toBeVisible()
})
