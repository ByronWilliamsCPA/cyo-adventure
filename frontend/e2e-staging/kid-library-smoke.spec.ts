import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsStagingTestUser, unlockParentalGateIfPresent } from './support/auth'

/**
 * The one staging spec that writes: mints a device grant (via the real
 * console UI) to reach the seeded "Test Reader" profile's populated library,
 * then revokes it. Mirrors e2e-prod/kid-device-grant.spec.ts's narrow,
 * fully-reversible write pattern (exactly one grant, removed by the final
 * test and, if that never runs, by the afterAll backstop) rather than
 * inventing a new one; unlike prod's seeded kid (who has no assigned
 * stories), staging's "Test Reader" has two published stories, so this also
 * confirms the library renders populated content, not just an empty state.
 */
const DEVICE_GRANT_KEY = 'device_grant'
const TEST_KID_NAME = 'Test Reader'

test.describe('kid library via a real device grant on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsStagingTestUser(sharedPage, 'guardian')
  })

  test.afterAll(async () => {
    // See e2e-prod/kid-device-grant.spec.ts for the rationale: a best-effort
    // DELETE backstop in case the explicit revoke test below didn't run.
    try {
      const cleanup = await sharedPage.evaluate(async ([key]) => {
        const raw = window.localStorage.getItem(key)
        const token = window.localStorage.getItem('auth_token')
        let outcome: { attempted: boolean; ok: boolean; status: number } = {
          attempted: false,
          ok: false,
          status: 0,
        }
        if (raw && token) {
          try {
            const grant = JSON.parse(raw) as { id?: string }
            if (grant.id) {
              const res = await fetch(`/api/v1/device-grants/${grant.id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
              })
              outcome = {
                attempted: true,
                ok: res.ok || res.status === 404,
                status: res.status,
              }
            }
          } catch {
            outcome = { attempted: true, ok: false, status: 0 }
          }
        }
        window.localStorage.removeItem(key)
        return outcome
      }, [DEVICE_GRANT_KEY] as const)
      if (cleanup.attempted && !cleanup.ok) {
        console.warn(
          '[kid-library-smoke] backstop device-grant revoke did not confirm ' +
            `(HTTP ${cleanup.status}); a grant may still be live on staging. ` +
            'List device grants and revoke it manually.'
        )
      }
    } catch {
      /* page already closed / evaluate unavailable: nothing to clean */
    }
    await sharedPage.close()
  })

  test('the guardian authorizes this device for kid access', async () => {
    await sharedPage.goto('/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

    const setUp = sharedPage.getByRole('button', { name: 'Set up this device for your kids' })
    const reauthorize = sharedPage.getByRole('button', { name: 'Re-authorize this device' })
    if (await setUp.isVisible().catch(() => false)) {
      await setUp.click()
    } else {
      await reauthorize.click()
    }

    await expect(sharedPage.getByRole('button', { name: 'Hand device to a child' })).toBeVisible()
    const stored = await sharedPage.evaluate(
      (key) => window.localStorage.getItem(key),
      DEVICE_GRANT_KEY
    )
    expect(stored, 'a device grant should be persisted after authorize').not.toBeNull()
  })

  test('the authorized device opens the populated test kid library', async () => {
    await sharedPage.goto('/kids')
    await expect(sharedPage.getByRole('heading', { name: "Who's reading?", level: 1 })).toBeVisible()

    await sharedPage.getByRole('link', { name: TEST_KID_NAME }).click()
    await expect(sharedPage).toHaveURL(/\/library\//)

    // The seeded Test Reader has two published, assigned stories, so the
    // library renders the populated "My Books" view, not the empty state.
    await expect(sharedPage.getByRole('heading', { name: 'My Books' })).toBeVisible()
  })

  test('the guardian revokes the device authorization', async () => {
    await sharedPage.goto('/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

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
