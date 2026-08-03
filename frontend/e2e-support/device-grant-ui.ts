import { expect, type Page } from '@playwright/test'

/**
 * Guardian-console device-grant UI interactions shared by every live tier.
 *
 * Lives here rather than in `e2e-staging/support/device-grant.ts` because the
 * prod tier drives the same console with the same copy; that module is scoped
 * to staging-only teardown. Three specs already carried a byte-identical copy
 * of this interaction (kid-library-smoke, moderation-qa-invisibility,
 * e2e-prod/kid-device-grant), and all three were wrong in the same way, which
 * is the argument for one implementation rather than three.
 */

/**
 * Removes this device's grant from the guardian console, through the two-step
 * flow the console actually implements.
 *
 * #CRITICAL: security: removal is deliberately guarded by a confirmation
 * dialog (ConsolePage.tsx, `confirmingRemove`), because a misclick locks kids
 * out of reading until a guardian re-authorizes. The danger button only opens
 * that dialog; `removeFromThisDevice()` runs from the dialog's "Remove device"
 * action. Every caller previously clicked the danger button and asserted the
 * first-run CTA immediately, so the dialog sat open, the console kept
 * rendering its authorized branch, and the assertion failed with
 * "element(s) not found" pointing at the CTA rather than at the missing
 * confirm. Assert the dialog, then confirm through it.
 * #VERIFY: ConsolePage.test.tsx "asks for confirmation before removing the
 * device grant" is the unit-level statement of the same contract; if that copy
 * changes, both it and this helper must change together.
 *
 * The console clears the local grant only after the server DELETE succeeds, so
 * the first-run CTA returning proves the revoke landed on the backend rather
 * than only in the browser. That also makes the wait network-bound: the default
 * 5s assertion budget is not enough here, and the confirm is the LAST action of
 * the last spec in a tier that signs in five times against one runner IP, so it
 * competes with the 60 rpm/IP limiter. Observed flaking once at 5s on staging
 * run 30775018054 and passing on retry, hence the explicit 15s.
 *
 * A failed revoke leaves `deviceStatus === 'error'`, which renders an error
 * banner while the console keeps its authorized branch. Racing the two states
 * rather than waiting only for the CTA means a backend revoke failure is
 * reported as itself instead of as a timeout on an unrelated button.
 *
 * @param page - A page already on `/guardian` with the AdultGate cleared.
 */
export async function removeDeviceFromConsole(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Remove from this device' }).click()
  await expect(page.getByRole('heading', { name: 'Remove this device?' })).toBeVisible()
  await page.getByRole('button', { name: 'Remove device', exact: true }).click()

  const cta = page.getByRole('button', { name: 'Set up this device for your kids' })
  const revokeFailed = page.getByText(/That didn.t work\. Check your connection/)
  await expect(cta.or(revokeFailed).first()).toBeVisible({ timeout: 15_000 })
  await expect(
    revokeFailed,
    'the console reported a failed device-grant revoke; the grant is still live ' +
      'on the backend and the afterAll backstop is now the only thing that will ' +
      'clean it up'
  ).not.toBeVisible()
  await expect(cta).toBeVisible()
}
