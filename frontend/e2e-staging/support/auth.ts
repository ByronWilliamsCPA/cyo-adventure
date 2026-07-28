import { expect, type Page } from '@playwright/test'

import { GUARDIAN_CONSENT_PATH, GUARDIAN_LOGIN_PATH } from '../../src/routes'
import { requireStagingCredentials } from './staging-env'

/**
 * Legal name typed into the ADR-018 consent form's electronic-signature field.
 * Deliberately self-identifying: this string is persisted on the staging
 * guardian's consent record, so anyone auditing staging consent data can see at
 * a glance that it came from the automated tier, not from a real guardian.
 */
const CONSENT_SIGNER_NAME = 'Staging E2E Test Guardian'

/**
 * Signs in through the real login form against the staging Supabase project,
 * as either the seeded test guardian or the seeded test admin (see
 * scripts/seed_staging.py). Adapted from e2e-prod/support/auth.ts's
 * signInAsProdTestAdmin: same real-Supabase-signin mechanics, parameterized
 * by role since staging seeds two separate accounts rather than one
 * dual-role account.
 */
export async function signInAsStagingTestUser(
  page: Page,
  role: 'guardian' | 'admin'
): Promise<void> {
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

  await acceptGuardianConsentIfPresent(page)
}

/**
 * Completes the ADR-018 guardian-consent interstitial if the post-login
 * destination is it.
 *
 * #CRITICAL: data integrity: this is the ONE staging interstitial that is not
 * re-presented on a later visit. ProtectedRoute derives `needs-consent` from
 * `/v1/me`, so an unconsented guardian is bounced to GUARDIAN_CONSENT_PATH from
 * EVERY protected route, and submitting the form writes a persistent consent
 * record rather than a per-session flag. That is why the call sits in
 * signInAsStagingTestUser rather than beside unlockParentalGateIfPresent at each
 * navigation: clearing it once per sign-in is sufficient, and probing per page
 * would spend the 5s absent-gate timeout on every goto for no added coverage.
 *
 * The gap this closes: guardian-admin-smoke.spec.ts and kid-library-smoke.spec.ts
 * only ever handled the ADR-014 AdultGate ("Grown-ups only"), a different
 * interstitial with a different trigger, so both specs asserted against a
 * consent form they had no way to get past. Every run of the staging tier since
 * it was added failed here, and the Playwright error-context snapshot named the
 * cause plainly: `heading "Before you get started" [level=1]`.
 *
 * #VERIFY: this makes the otherwise read-only staging smoke tier perform exactly
 * one write, and only on a guardian who has never consented. If the seed ever
 * starts recording consent for the staging test guardian (scripts/seed_staging.py),
 * this becomes a no-op probe rather than dead code, which is the intended
 * steady state.
 */
export async function acceptGuardianConsentIfPresent(page: Page): Promise<void> {
  const consentHeading = page.getByRole('heading', { name: 'Before you get started', level: 1 })
  const gated = await consentHeading
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!gated) return

  await page.getByLabel('Your full legal name').fill(CONSENT_SIGNER_NAME)
  await page
    .getByRole('checkbox', {
      name: /electronic signature agreeing to CYO Adventure's Privacy Notice/,
    })
    .check()
  await page.getByRole('button', { name: 'Agree and continue' }).click()

  // The page has no local success state: recordConsent's syncPrincipal flips
  // AuthStatus to 'signed-in' and ProtectedRoute re-renders past this component.
  // Assert on both halves of that transition so a consent POST that 4xxs surfaces
  // here, at its cause, instead of as a confusing assertion failure in the caller.
  await expect(consentHeading).not.toBeVisible({ timeout: 15_000 })
  await expect(page).not.toHaveURL(new RegExp(`${GUARDIAN_CONSENT_PATH}$`))
}

/**
 * Completes the AdultGate re-auth challenge if `page.goto()` landed on it.
 * See e2e-prod/support/auth.ts's unlockParentalGateIfPresent for the ADR-014
 * warm/cold-gate rationale this mirrors.
 */
export async function unlockParentalGateIfPresent(
  page: Page,
  role: 'guardian' | 'admin'
): Promise<void> {
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
