import { expect, type Page } from '@playwright/test'

import { GUARDIAN_LOGIN_PATH } from '../../src/routes'
import { requireProdCredentials } from './prod-env'

/**
 * Signs in through the real login form against live production. Unlike the
 * local/mocked tiers' seedGuardianSession (a forged Supabase session), there
 * is no shortcut here: production verifies a real JWT signature and JWKS, so
 * this must go through an actual Supabase sign-in and land wherever the app
 * redirects a resolved Principal (guardian console or admin console).
 */
export async function signInAsProdTestAdmin(page: Page): Promise<void> {
  const { email, password } = requireProdCredentials()

  await page.goto(GUARDIAN_LOGIN_PATH)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()

  // Signed-in resolution is async (session -> /v1/me -> redirect); give it
  // real network time rather than the default assertion timeout.
  await expect(page).not.toHaveURL(new RegExp(GUARDIAN_LOGIN_PATH), { timeout: 15_000 })
}
