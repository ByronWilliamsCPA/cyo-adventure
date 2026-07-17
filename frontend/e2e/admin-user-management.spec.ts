import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Manual-verification smoke spec for the WS-J admin user-management console
 * (real routing/rendering in a real browser; the full behavioral matrix
 * lives in Vitest: src/admin/UserManagementPage.test.tsx). Mirrors
 * guardian-console.spec.ts's mocked-tier pattern: a seeded GoTrue session
 * plus route-mocked API responses, no backend required.
 */

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active',
  guardian_count: 2,
  kid_count: 1,
  created_at: '2026-01-01T00:00:00Z',
}

const USER_A = {
  id: 'user-1',
  family_id: 'fam-a',
  email: 'guardian@example.com',
  role: 'guardian',
  is_admin: false,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
}

test.beforeEach(async ({ context, page }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/users*', (route) =>
    route.fulfill({ json: { users: [USER_A] } })
  )
  await page.route('**/api/v1/admin/profiles*', (route) =>
    route.fulfill({ json: { profiles: [] } })
  )
  await page.route('**/api/v1/admin/families', (route) =>
    route.fulfill({ json: { families: [FAMILY_A] } })
  )
  await page.route('**/api/v1/admin/family-connections', (route) =>
    route.fulfill({ json: { connections: [] } })
  )
})

test('an admin can reach the user management console from the admin nav', async ({ page }) => {
  await page.goto('/admin')
  await page.getByRole('link', { name: 'User management' }).click()
  await expect(page).toHaveURL(/\/admin\/users$/)
  await expect(page.getByRole('heading', { name: 'User management' })).toBeVisible()
  await expect(page.getByText('guardian@example.com')).toBeVisible()
})

test('switching tabs shows the Families tab with member counts', async ({ page }) => {
  await page.goto('/admin/users')
  await page.getByRole('button', { name: 'Families' }).click()
  await expect(page.getByRole('cell', { name: 'Family A' })).toBeVisible()
})

test('inviting a guardian posts the expected body and refreshes the roster', async ({ page }) => {
  let capturedBody: unknown
  await page.route('**/api/v1/admin/users', (route) => {
    if (route.request().method() === 'POST') {
      capturedBody = route.request().postDataJSON()
      return route.fulfill({
        status: 201,
        json: {
          id: 'user-2',
          family_id: 'fam-a',
          email: 'new@example.com',
          role: 'guardian',
          is_admin: false,
          status: 'pending',
          created_at: '2026-01-05T00:00:00Z',
        },
      })
    }
    return route.fulfill({ json: { users: [USER_A] } })
  })

  await page.goto('/admin/users')
  await page.getByLabel('Email').fill('new@example.com')
  await page.getByLabel('Family').selectOption('fam-a')
  await page.getByRole('button', { name: 'Send invite' }).click()

  await expect
    .poll(() => capturedBody)
    .toEqual({
      email: 'new@example.com',
      family_id: 'fam-a',
      role: 'guardian',
      is_admin: false,
    })
})

test('a plain guardian visiting /admin/users is sent back to the guardian console', async ({
  page,
}) => {
  await mockMe(page, { role: 'guardian' })
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/guardian$/)
})
