import { expect, test } from '@playwright/test'

import {
  SUPABASE_SESSION_KEY,
  makeGuardianSession,
  mockEmptyConsole,
  mockMe,
  mockOnboarding,
} from './support/auth'

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
  await mockOnboarding(page)
  await mockMe(page)
  await mockEmptyConsole(page)

  await page.goto('/guardian/login')
  await page.getByLabel('Email').fill('parent@example.com')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
})

test('an admin-only adult lands on the admin console after sign-in', async ({ page }) => {
  // Role-based post-login redirect (LoginPage: role === 'admin' -> admin
  // console). An admin-only account has no guardian family surface, so it must
  // land on /admin, not /guardian.
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({ json: makeGuardianSession('e2e-admin-token') })
  )
  await mockOnboarding(page, { role: 'admin' })
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)

  await page.goto('/guardian/login')
  await page.getByLabel('Email').fill('admin@example.com')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/admin$/)
})

test('a dual-role adult lands on the guardian console after sign-in', async ({ page }) => {
  // A guardian who also holds the admin capability defaults to the guardian
  // console (role drives the redirect, not is_admin); the shells cross-link.
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({ json: makeGuardianSession('e2e-guardian-token') })
  )
  await mockOnboarding(page)
  await mockMe(page, { role: 'guardian', is_admin: true })
  await mockEmptyConsole(page)

  await page.goto('/guardian/login')
  await page.getByLabel('Email').fill('parent@example.com')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
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

test('sign-out returns to the login page and re-locks the console', async ({ page }) => {
  // S-7(b) needs a genuine re-navigation to the protected console AFTER
  // sign-out to prove the session was actually cleared, not just that
  // sign-out changed the URL once. seedGuardianSession's context.addInitScript
  // would replay on that later navigation too and silently re-plant the
  // session, masking a real sign-out regression -- so this test seeds the
  // session once via page.evaluate (a single localStorage write) instead of
  // the context-level init script every other spec in this file uses.
  await page.goto('/guardian/login')
  await page.evaluate(
    ([key, value, token]) => {
      window.localStorage.setItem(key, value)
      window.localStorage.setItem('auth_token', token)
    },
    [
      SUPABASE_SESSION_KEY,
      JSON.stringify(makeGuardianSession('e2e-guardian-token')),
      'e2e-guardian-token',
    ] as const
  )
  await mockOnboarding(page)
  await mockMe(page)
  await mockEmptyConsole(page)
  await page.route('**/auth/v1/logout**', (route) => route.fulfill({ status: 204, body: '' }))

  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/guardian\/login$/)

  // Re-navigate to the protected console and confirm ProtectedRoute re-gates
  // it (redirects back to login) instead of rendering the console from a
  // lingering session.
  await page.goto('/guardian')
  await expect(page).toHaveURL(/\/guardian\/login$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).not.toBeVisible()
})
