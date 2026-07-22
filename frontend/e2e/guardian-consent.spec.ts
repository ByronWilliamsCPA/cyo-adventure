import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian consent gate (P1-1): the highest traffic x blast-radius surface
 * that had no browser-level coverage. Every guardian meets this screen on
 * first sign-in, and until 2026-07-22 it was only ever exercised by the
 * component test (src/auth/GuardianConsentPage.test.tsx) and one manual prod
 * check.
 *
 * The gate is driven by the ONBOARDING response, not /v1/me: AuthContext
 * calls POST /v1/onboarding first and derives status from it
 * (status !== 'active' -> awaiting-approval; consent_recorded === false ->
 * needs-consent). This spec mocks that endpoint as a small state machine so
 * it can prove the full needs-consent -> submit -> signed-in transition, plus
 * the awaiting-approval branch, which component tests cannot reach because
 * they never round-trip through ProtectedRoute's redirects.
 */

const CONSENT_POLICY_VERSION = '2026-07-20'

interface ConsentPayload {
  accepted?: boolean | null
  policy_version?: string | null
  signer_name?: string | null
}

/**
 * Route POST /v1/onboarding as a state machine: it reports the guardian as
 * un-consented until a request carrying a `consent` body arrives, then flips
 * to consent_recorded:true so the next syncPrincipal resolves to signed-in.
 * The page-level route registered here wins over the already-consented
 * context route that seedGuardianSession installs.
 *
 * Returns a getter for the captured consent payload so the test can assert the
 * exact body the app sent (trimmed name, policy version, accepted flag).
 */
async function mockConsentOnboarding(page: Page): Promise<() => ConsentPayload | null> {
  let consented = false
  let captured: ConsentPayload | null = null
  await page.route('**/api/v1/onboarding', (route) => {
    const body = (route.request().postDataJSON() ?? {}) as { consent?: ConsentPayload }
    if (body.consent) {
      consented = true
      captured = body.consent
    }
    return route.fulfill({
      json: {
        family_id: 'fam-1',
        user_id: 'e2e-user',
        role: 'guardian',
        created: false,
        status: 'active',
        consent_recorded: consented,
      },
    })
  })
  return () => captured
}

test('un-consented guardian is gated, and consenting unblocks the console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  const consentBody = await mockConsentOnboarding(page)
  await mockMe(page)
  await mockEmptyConsole(page)
  // The console also fans out to these on mount; stub them so nothing falls
  // through to the (absent) real backend proxy.
  await page.route('**/api/v1/story-requests**', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications**', (route) =>
    route.fulfill({ json: { notifications: [], unread_count: 0 } })
  )

  // A protected surface bounces to the consent gate while consent is missing.
  await page.goto('/guardian/intake')
  await expect(page).toHaveURL(/\/guardian\/consent$/)
  await expect(
    page.getByRole('heading', { name: 'Before you get started' })
  ).toBeVisible()

  // Submit is inert until both the legal name and the checkbox are provided.
  const submit = page.getByRole('button', { name: 'Agree and continue' })
  await expect(submit).toBeDisabled()

  // Leading/trailing whitespace proves the app trims the signature.
  await page.getByLabel('Your full legal name').fill('  Dana Guardian  ')
  await page
    .getByRole('checkbox', {
      name: /electronic signature agreeing to CYO Adventure's Privacy Notice/,
    })
    .check()
  await expect(submit).toBeEnabled()
  await submit.click()

  // Consenting resolves auth to signed-in and lands on the family console.
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()

  // The exact consent contract the backend expects.
  expect(consentBody()).toEqual({
    accepted: true,
    policy_version: CONSENT_POLICY_VERSION,
    signer_name: 'Dana Guardian',
  })

  // The gate no longer fires: intake now renders instead of redirecting.
  await page.goto('/guardian/intake')
  await expect(page).toHaveURL(/\/guardian\/intake$/)
  await expect(
    page.getByRole('heading', { name: 'Before you get started' })
  ).toHaveCount(0)
})

test('guardian pending admin approval sees the awaiting-approval interstitial', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  // status !== 'active' short-circuits before the consent check.
  await page.route('**/api/v1/onboarding', (route) =>
    route.fulfill({
      json: {
        family_id: 'fam-1',
        user_id: 'e2e-user',
        role: 'guardian',
        created: true,
        status: 'pending',
        consent_recorded: false,
      },
    })
  )
  await mockMe(page)

  await page.goto('/guardian/intake')
  await expect(page).toHaveURL(/\/guardian\/awaiting-approval$/)
  await expect(page.getByRole('heading', { name: 'Almost there' })).toBeVisible()
  await expect(
    page.getByText('Your account is awaiting approval')
  ).toBeVisible()
})
