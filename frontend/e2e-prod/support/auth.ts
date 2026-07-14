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
  // real network time rather than the default assertion timeout. Race
  // against LoginPage's on-page error alert so a genuine login failure (bad
  // password, rate limit, 5xx) surfaces its actual message instead of a bare
  // 15s "expect().not.toHaveURL() timeout exceeded".
  const left = page
    .waitForURL((url) => url.pathname !== GUARDIAN_LOGIN_PATH, { timeout: 15_000 })
    .then(() => null)
  const failed = page
    .getByRole('alert')
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => page.getByRole('alert').innerText())

  const alertText = await Promise.race([left, failed])
  if (alertText !== null) {
    throw new Error(`Production login failed: ${alertText}`)
  }

  // Landing spot is either the guardian or admin console depending on the
  // account's role/capability mix (see api/me and the dual-role shells); the
  // login path itself is already ruled out above, so a real destination
  // check just confirms we reached one of the two adult consoles.
  const destination = new URL(page.url()).pathname
  if (!destination.startsWith('/guardian') && !destination.startsWith('/admin')) {
    throw new Error(`Unexpected post-login destination: ${destination}`)
  }
}

/**
 * Completes the AdultGate re-auth challenge if `page.goto()` landed on it.
 * Defensive fallback: after a real Supabase sign-in the gate is usually
 * already warm (see below), so this is typically a no-op, but it keeps the
 * suite robust if a navigation ever lands cold.
 *
 * ADR-014 reworked this boundary. The two former per-page ParentalGate
 * placements collapsed into a single AdultGate at the adult-subtree root, and
 * its warm state moved from module-level JS memory to sessionStorage: keyed by
 * userId, with a 5-minute TTL, and warmed on the SIGNED_IN auth event
 * (AuthContext). Two consequences for this tier:
 *   1. A real sign-in warms the gate, so the first adult-console navigation is
 *      generally NOT cold.
 *   2. sessionStorage survives same-tab `page.goto()` navigation, so once the
 *      gate is warm the remaining goto()s in this shared-page suite ride that
 *      warmth (within the TTL) rather than each re-challenging.
 * The gate re-locks only on TTL expiry, sign-out, or crossing down into the
 * kid surface (which this suite never does).
 */
export async function unlockParentalGateIfPresent(page: Page): Promise<void> {
  const gateHeading = page.getByRole('heading', { name: 'Grown-ups only', level: 1 })
  const gated = await gateHeading
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!gated) return

  const { password } = requireProdCredentials()
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Confirm' }).click()
  await expect(gateHeading).not.toBeVisible({ timeout: 15_000 })
}
