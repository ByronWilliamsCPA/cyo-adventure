import { expect, type Page } from '@playwright/test'

import { GUARDIAN_LOGIN_PATH } from '../../src/routes'
import { requireStagingCredentials } from './staging-env'

/**
 * Signs in through the real login form against the staging Supabase project,
 * as either the seeded test guardian or the seeded test admin (see
 * scripts/seed_staging.py). Adapted from e2e-prod/support/auth.ts's
 * signInAsProdTestAdmin: same real-Supabase-signin mechanics, parameterized
 * by role since staging seeds two separate accounts rather than one
 * dual-role account.
 */
export async function signInAsStagingTestUser(page: Page, role: 'guardian' | 'admin'): Promise<void> {
  const { email, password } = requireStagingCredentials(role)

  await page.goto(GUARDIAN_LOGIN_PATH)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()

  const left = page
    .waitForURL((url) => url.pathname !== GUARDIAN_LOGIN_PATH, { timeout: 15_000 })
    .then(() => null)
  const failed = page
    .getByRole('alert')
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => page.getByRole('alert').innerText())

  const alertText = await Promise.race([left, failed])
  if (alertText !== null) {
    throw new Error(`Staging login failed for role=${role}: ${alertText}`)
  }

  const destination = new URL(page.url()).pathname
  if (!destination.startsWith('/guardian') && !destination.startsWith('/admin')) {
    throw new Error(`Unexpected post-login destination for role=${role}: ${destination}`)
  }
}

/**
 * Completes the AdultGate re-auth challenge if `page.goto()` landed on it.
 * See e2e-prod/support/auth.ts's unlockParentalGateIfPresent for the ADR-014
 * warm/cold-gate rationale this mirrors.
 */
export async function unlockParentalGateIfPresent(page: Page, role: 'guardian' | 'admin'): Promise<void> {
  const gateHeading = page.getByRole('heading', { name: 'Grown-ups only', level: 1 })
  const gated = await gateHeading
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!gated) return

  const { password } = requireStagingCredentials(role)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Confirm' }).click()
  await expect(gateHeading).not.toBeVisible({ timeout: 15_000 })
}
