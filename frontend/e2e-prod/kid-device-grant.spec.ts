import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin, unlockParentalGateIfPresent } from './support/auth'

/**
 * The one prod spec that WRITES: it exercises the real ADR-014 device-grant
 * flow end to end against live production. A device grant is the only kid-gate
 * that cannot be read-only-tested, so the guardian mints one through the real
 * console UI, the authorized device opens the seeded "E2E Test Kid" library,
 * and the guardian then revokes it. The write is deliberately narrow and fully
 * reversible: exactly one grant, removed by the final test and, if that never
 * runs, by the afterAll safety net. Manual trigger only (see
 * playwright.e2e-prod.config.ts); every run authenticates a real account.
 *
 * Serial + one shared page: mint, use, and revoke are a single stateful thread
 * and must run in order against one authenticated session, not four separate
 * prod logins.
 */
const DEVICE_GRANT_KEY = 'device_grant'
const TEST_KID_NAME = 'E2E Test Kid'

test.describe('kid access via a real device grant', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsProdTestAdmin(sharedPage)
  })

  test.afterAll(async () => {
    // #CRITICAL: security: this tier writes to live production, so it MUST NOT
    // leave a usable device grant behind if an assertion failed before the
    // explicit "remove" test ran. Best-effort DELETE through the same-origin
    // API (baseURL resolves to /api in the prod build) using the guardian
    // bearer the app stores under `auth_token`; "Set up this device" never
    // signs the guardian out, so that token is still valid here. Cleanup
    // errors are swallowed: they must never mask or replace a real failure.
    // #VERIFY: the explicit revoke test below is the primary path; this is the
    // backstop, and list()ing grants after a run should show none.
    try {
      await sharedPage.evaluate(async ([key]) => {
        const raw = window.localStorage.getItem(key)
        const token = window.localStorage.getItem('auth_token')
        if (raw && token) {
          try {
            const grant = JSON.parse(raw) as { id?: string }
            if (grant.id) {
              await fetch(`/api/v1/device-grants/${grant.id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
              })
            }
          } catch {
            /* malformed blob or network error: nothing more we can do here */
          }
        }
        window.localStorage.removeItem(key)
      }, [DEVICE_GRANT_KEY] as const)
    } catch {
      /* page already closed / evaluate unavailable: nothing to clean */
    }
    await sharedPage.close()
  })

  test('the guardian authorizes this device for kid access', async () => {
    await sharedPage.goto('/guardian')
    await unlockParentalGateIfPresent(sharedPage)

    // First run shows "Set up this device for your kids"; a prior interrupted
    // run that left a grant shows "Re-authorize this device" instead. Either
    // one mints a fresh grant (authorizeDevice revokes any previous id), so
    // accept whichever the console renders.
    const setUp = sharedPage.getByRole('button', { name: 'Set up this device for your kids' })
    const reauthorize = sharedPage.getByRole('button', { name: 'Re-authorize this device' })
    if (await setUp.isVisible().catch(() => false)) {
      await setUp.click()
    } else {
      await reauthorize.click()
    }

    // A live grant makes the hand-off control appear, and the grant blob lands
    // in localStorage under the key DeviceAuthorizedRoute reads on the kid side.
    await expect(sharedPage.getByRole('button', { name: 'Hand device to a child' })).toBeVisible()
    const stored = await sharedPage.evaluate(
      (key) => window.localStorage.getItem(key),
      DEVICE_GRANT_KEY
    )
    expect(stored, 'a device grant should be persisted after authorize').not.toBeNull()
  })

  test('the authorized device opens the test kid library', async () => {
    await sharedPage.goto('/kids')
    await expect(sharedPage.getByRole('heading', { name: "Who's reading?", level: 1 })).toBeVisible()

    // The picker tile is a link whose accessible name is the display name (its
    // avatar is aria-hidden); the E2E Test Family holds only this one kid.
    await sharedPage.getByRole('link', { name: TEST_KID_NAME }).click()
    await expect(sharedPage).toHaveURL(/\/library\//)

    // The seeded test kid has no assigned stories, so the library renders its
    // empty state, an <h2> "No books yet", never the populated "My Books" h1.
    // The RequestStory form also renders here; do NOT submit it (it POSTs a
    // real story request, which this non-destructive tier must not create).
    await expect(sharedPage.getByRole('heading', { name: 'No books yet' })).toBeVisible()
  })

  test('the guardian revokes the device authorization', async () => {
    // Crossing into /kids parked the AdultGate (DeviceAuthorizedRoute calls
    // parkAdultGate), so this navigation lands cold and needs a re-unlock.
    await sharedPage.goto('/guardian')
    await unlockParentalGateIfPresent(sharedPage)

    // "Remove from this device" clears the local grant only after the server
    // DELETE succeeds, so the first-run CTA returning proves the revoke landed
    // on the backend, not just in the browser.
    await sharedPage.getByRole('button', { name: 'Remove from this device' }).click()
    await expect(
      sharedPage.getByRole('button', { name: 'Set up this device for your kids' })
    ).toBeVisible()
    const stored = await sharedPage.evaluate(
      (key) => window.localStorage.getItem(key),
      DEVICE_GRANT_KEY
    )
    expect(stored, 'the device grant should be cleared after remove').toBeNull()
  })
})
