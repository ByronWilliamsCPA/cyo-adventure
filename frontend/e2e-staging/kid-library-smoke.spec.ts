import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { unlockParentalGateIfPresent } from './support/auth'
import { stagingStorageStatePath } from './support/auth-storage'
import {
  createDeviceGrantMintState,
  readPersistedGrantId,
  revokeDeviceGrantBackstop,
} from './support/device-grant'
import { removeDeviceFromConsole } from '../e2e-support/device-grant-ui'
import { gotoResilient, paceNavigation } from '../e2e-support/rate-limit'

/**
 * A grant-writing staging spec (moderation-qa-invisibility.spec.ts runs the
 * same reversible pattern): mints a device grant (via the real console UI)
 * to reach the seeded "Test Reader" profile's populated library,
 * then revokes it. Mirrors e2e-prod/kid-device-grant.spec.ts's narrow,
 * fully-reversible write pattern (exactly one grant, removed by the final
 * test and, if that never runs, by the afterAll backstop) rather than
 * inventing a new one; unlike prod's seeded kid (who has no assigned
 * stories), staging's "Test Reader" has two published stories, so this also
 * confirms the library renders populated content, not just an empty state.
 *
 * `beforeAll` restores a pre-authenticated guardian session
 * (`stagingStorageStatePath('guardian')`) rather than signing in through the
 * login form; the tier's sign-ins now happen once each, up front, in
 * `e2e-staging/auth.setup.ts`. The device-grant mint and revoke below are
 * unaffected: they are real writes this spec still performs against staging,
 * only the guardian's own authentication is now reused rather than repeated.
 */
const DEVICE_GRANT_KEY = 'device_grant'
const TEST_KID_NAME = 'Test Reader'

test.describe('kid library via a real device grant on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  /**
   * Captured at mint time, not re-read at teardown: a device-grant 401 makes
   * useApi.ts clear the localStorage record, so the backstop's only input
   * would be gone in exactly the runs where the backstop is the only cleanup
   * left. The `mintAttempted` half is what makes an uncaptured id still
   * reportable. See support/device-grant.ts.
   */
  const grantState = createDeviceGrantMintState()

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage({ storageState: stagingStorageStatePath('guardian') })
  })

  test.afterAll(async () => {
    // See e2e-prod/kid-device-grant.spec.ts for the rationale: a best-effort
    // DELETE backstop in case the explicit revoke test below didn't run.
    await revokeDeviceGrantBackstop(sharedPage, grantState, '[kid-library-smoke]')
    await sharedPage.close()
  })

  test('the guardian authorizes this device for kid access', async () => {
    await gotoResilient(sharedPage, '/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

    const setUp = sharedPage.getByRole('button', { name: 'Set up this device for your kids' })
    const reauthorize = sharedPage.getByRole('button', { name: 'Re-authorize this device' })

    // Armed BEFORE the click, not after the id is read: the POST can mint
    // server-side and still leave this test with no id (the visibility
    // assertion below can time out, or a device-grant 401 can clear the
    // localStorage record first). From here on, teardown must report a leak
    // even with nothing to revoke.
    grantState.mintAttempted = true
    if (await setUp.isVisible().catch(() => false)) {
      await setUp.click()
    } else {
      await reauthorize.click()
    }

    await expect(sharedPage.getByRole('button', { name: 'Hand device to a child' })).toBeVisible()
    grantState.grantId = await readPersistedGrantId(sharedPage)
    expect(
      grantState.grantId,
      'a device grant carrying an id should be persisted after authorize; the ' +
        'afterAll backstop has no other way to revoke it if a later test fails'
    ).not.toBeNull()
  })

  test('the authorized device opens the populated test kid library', async () => {
    await gotoResilient(sharedPage, '/kids')
    await expect(
      sharedPage.getByRole('heading', { name: "Who's reading?", level: 1 })
    ).toBeVisible()

    // Paced by hand because this is an in-app route change, not a goto: the
    // library mount fans out into its own list and recommendations fetches, so
    // it spends request budget exactly like a navigation and must advance the
    // same floor.
    await paceNavigation(sharedPage)
    await sharedPage.getByRole('link', { name: TEST_KID_NAME }).click()
    await expect(sharedPage).toHaveURL(/\/library\//)

    // The seeded Test Reader has two published, assigned stories, so the
    // library renders the populated "My Books" view, not the empty state.
    //
    // A 429 on this route does NOT reach either state: LibraryPage classifies
    // it as transient and, finding no IndexedDB cache in a fresh CI browser,
    // renders "We lost the bookshelf" instead. That copy matches neither this
    // assertion nor RATE_LIMIT_ALERT, so a rate limit here fails the test
    // (correctly) while reporting a missing heading. The paceNavigation call
    // above is what keeps that from happening in the first place.
    await expect(sharedPage.getByRole('heading', { name: 'My Books' })).toBeVisible()
  })

  test('the guardian revokes the device authorization', async () => {
    await gotoResilient(sharedPage, '/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

    await removeDeviceFromConsole(sharedPage)
    const stored = await sharedPage.evaluate(
      (key) => window.localStorage.getItem(key),
      DEVICE_GRANT_KEY
    )
    expect(stored, 'the device grant should be cleared after remove').toBeNull()
    // Revoked explicitly, so the backstop has nothing left to do: clear both
    // halves, or the uncaptured-mint branch would report a phantom leak.
    grantState.grantId = null
    grantState.mintAttempted = false
  })
})
