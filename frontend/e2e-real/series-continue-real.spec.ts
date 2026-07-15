import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API series continuation: the seeded dev reader plays "Ember Trail 1"
 * (the WS-G PR2 dev seed's two-book, state-carrying series, scripts/
 * seed_dev_data.py) to its ending, follows "Continue the series", and lands
 * on "Ember Trail 2"'s opening passage. No route mocks; every /api call hits
 * uvicorn through the preview proxy, authorized as the seeded dev-child
 * subject (ENVIRONMENT=local trusts the bearer token).
 */

let deviceGrant: DeviceGrant | null = null

test.beforeEach(async ({ context }) => {
  await requireBackend()
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test.afterEach(async () => {
  // Revoke the per-test grant so a reused dev stack does not accumulate one
  // live grant row per run; best-effort (see revokeDevice), never fails a test.
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('the seeded child continues a real series into book 2', async ({ page }) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Locate the seeded "Ember Trail 1" card by title rather than a fixed
  // shelf position: the profile id in the URL is dynamic, so a direct
  // /read/<profileId>/s_dev_ember_1/1 navigation is not possible here.
  await page.getByRole('link', { name: 'Ember Trail 1' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  // Book 1's start node offers a courage-setting choice and a plain one,
  // both converging on a middle node whose single choice reaches the
  // success ending: at most two clicks.
  await page.getByTestId('choice-c_n_e1_brave').click()
  await page.locator('[data-testid^="choice-"]').first().click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()

  const continueButton = page.getByTestId('continue-series')
  await expect(continueButton).toBeVisible()
  await continueButton.click()

  // Book 2 opens at its declared series entry node.
  await expect(page).toHaveURL(/\/read\/[^/]+\/s_dev_ember_2\//)
  await expect(page.getByTestId('passage-body')).toContainText(
    'Ember Trail 2: the trail begins.'
  )
})
