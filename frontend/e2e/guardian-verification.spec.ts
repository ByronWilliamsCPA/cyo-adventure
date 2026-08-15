import { expect, test } from '@playwright/test'
import type { Page, Request } from '@playwright/test'

import { mockOnboarding, seedGuardianSession } from './support/auth'

/**
 * ADR-018 D1 parent verification: `/guardian/verify`
 * (`frontend/src/auth/GuardianVerificationPage.tsx`).
 *
 * Why this file exists. The coverage matrix records the client's behavior
 * around the `/start` call as "proven only at the component tier". The
 * staging spec (`e2e-staging/kws-public-urls.spec.ts`) covers the redirect
 * RETURN leg and says so explicitly; nothing drove the send.
 *
 * What only a network-tier test can prove. Two things, and the first is an
 * architectural constraint rather than a behavior:
 *
 * 1. This page MUST NOT depend on GET /v1/me. ADR-018 D1 orders verification
 *    FIRST, ahead of admin approval, so a guardian sitting on this screen
 *    still has `User.status == 'awaiting_approval'` and
 *    `api/deps.py::require_principal` refuses them outright. AuthContext's
 *    component tests pin that IT does not call /me
 *    ("unverified guardian never calls /me"), but that is a claim about one
 *    module. The route renders a page inside a router alongside whatever
 *    else mounts there, and any of it could add the call. Only a test that
 *    watches the wire can say nothing on this route calls /me. Here the
 *    endpoint is registered as a hard failure, so a regression fails loudly
 *    and names itself instead of degrading into a puzzling redirect.
 *
 * 2. The country actually reaches the server. The select feeds
 *    `startKwsVerification(location)` -> `POST /v1/consent/kws/start
 *    {location}`, and the value decides which verification methods KWS
 *    offers, so a form that collects it and drops it is a silent failure: the
 *    parent sees a success screen either way. The assertion is on the request
 *    body at the network layer, which is the only place that distinguishes
 *    "collected" from "sent".
 */

const START_RESPONSE = {
  status: 'pending',
  attempt_id: 'att-1',
  message: null,
}

/**
 * Onboarding shape that puts a guardian in `needs-verification`. Both fields
 * matter: AuthContext gates on `verification_required` AND
 * `verification_status !== 'verified'`, because a tier with the flag off
 * reports 'none' for everyone, which is the same value a gated guardian who
 * has not started reads.
 */
const UNVERIFIED = {
  status: 'awaiting_approval',
  consent_recorded: false,
  verification_required: true,
  verification_status: 'none',
}

/** Fail the test if anything on this route reaches /v1/me. */
async function forbidMe(page: Page, calls: string[]): Promise<void> {
  await page.route('**/api/v1/me', (route) => {
    calls.push(route.request().url())
    return route.fulfill({ status: 403, json: { detail: 'forbidden' } })
  })
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('an unverified guardian is routed to /guardian/verify without any call to /v1/me', async ({
  page,
}) => {
  const meCalls: string[] = []
  await forbidMe(page, meCalls)
  await mockOnboarding(page, UNVERIFIED)

  // Enter through a gated console page, so the redirect is exercised rather
  // than assumed: navigating straight to /guardian/verify would prove only
  // that the route renders.
  await page.goto('/guardian/intake')

  await expect(page).toHaveURL(/\/guardian\/verify$/)
  await expect(
    page.getByRole('heading', { name: 'First, confirm you are an adult', level: 1 })
  ).toBeVisible()

  // The constraint. If this ever fails, the page has grown a dependency on an
  // endpoint that refuses the exact caller it is built for, and the symptom
  // in production is a guardian who cannot get past their first screen.
  expect(meCalls).toEqual([])
})

test('the picked country reaches POST /v1/consent/kws/start, and sending is gated on it', async ({
  page,
}) => {
  const meCalls: string[] = []
  await forbidMe(page, meCalls)
  await mockOnboarding(page, UNVERIFIED)

  const startRequests: Request[] = []
  await page.route('**/api/v1/consent/kws/start', (route) => {
    startRequests.push(route.request())
    return route.fulfill({ status: 202, json: START_RESPONSE })
  })

  await page.goto('/guardian/verify')

  const send = page.getByRole('button', { name: 'Email me a verification link' })

  // Gated before a country is picked. Asserted BEFORE the happy path, because
  // once a country is selected this state is unreachable without a reload,
  // and a disabled-button check that runs after the click would pass against
  // a button disabled for an unrelated reason (in-flight `busy`).
  await expect(send).toBeDisabled()
  expect(startRequests).toHaveLength(0)

  await page.getByLabel('Your country of residence').selectOption('US')
  await expect(send).toBeEnabled()
  await send.click()

  await expect.poll(() => startRequests.length).toBe(1)
  const body = startRequests[0]?.postDataJSON() as { location?: string } | undefined
  // The value, not merely the presence of a body: a form that posts
  // `{location: ''}` would satisfy a shape-only check while sending KWS
  // nothing it can act on.
  expect(body?.location).toBe('US')

  expect(meCalls).toEqual([])
})

test('an attempt already in flight shows the check-your-email wait state', async ({ page }) => {
  const meCalls: string[] = []
  await forbidMe(page, meCalls)
  // A parent who already triggered the email and came back to the tab. The
  // page reads this from onboarding, so it must resolve to the wait state on
  // first paint rather than re-offering a send that would mint a second
  // attempt.
  await mockOnboarding(page, { ...UNVERIFIED, verification_status: 'pending' })

  await page.goto('/guardian/verify')

  await expect(page.getByRole('heading', { name: 'Check your email', level: 1 })).toBeVisible()
  // The send form is gone, not merely disabled.
  await expect(page.getByRole('button', { name: 'Email me a verification link' })).toHaveCount(0)

  expect(meCalls).toEqual([])
})
