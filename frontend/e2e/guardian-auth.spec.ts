import { expect, test } from '@playwright/test'

import { makeGuardianSession, mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian sign-in via the REAL login form (email/password, PR #101).
 * Only the Supabase token endpoint is mocked; supabase-js persists its own
 * session and fires SIGNED_IN, so AuthContext -> /me -> ProtectedRoute all
 * run for real. This closes the "guardian sign-in success" amber gap.
 */

test('signs in with email and password and lands on the console', async ({ page }) => {
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({ json: makeGuardianSession('e2e-guardian-token') })
  )
  await mockMe(page)
  await mockEmptyConsole(page)

  await page.goto('/guardian/login')
  await page.getByLabel('Email').fill('parent@example.com')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
})

test('wrong password shows the credentials error and stays on login', async ({ page }) => {
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({
      status: 400,
      json: { code: 400, error_code: 'invalid_credentials', msg: 'Invalid login credentials' },
    })
  )

  await page.goto('/guardian/login')
  await page.getByLabel('Email').fill('parent@example.com')
  await page.getByLabel('Password').fill('wrong')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toHaveText(
    "That email and password didn't match. Please try again."
  )
  await expect(page).toHaveURL(/\/guardian\/login$/)
})

test('sign-out returns to the login page and re-locks the console', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await mockEmptyConsole(page)
  await page.route('**/auth/v1/logout**', (route) => route.fulfill({ status: 204, body: '' }))

  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/guardian\/login$/)
})
