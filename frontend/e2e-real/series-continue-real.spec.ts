import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, resetRealState, revokeDevice } from './real-stack'

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
  // Truncate reading_state (among other seed-family fixture state) so each test
  // starts with NO server-side reading row for either Ember book. This matters
  // because ReaderPage applies a continuation seed only when saved server state
  // is undefined (ReaderPage.tsx: "the continuation seed applies ONLY to a fresh
  // read"): without the reset, one test's persisted book-2 row would suppress
  // the other test's carry/no-carry play and make the courage-gate assertions
  // order-dependent. resetRealState preserves the seeded s_dev_ember_1/_2 books
  // (it deletes only worker-generated UUID-shaped storybook ids).
  resetRealState()
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

  // carries_state:true proof (the point of the whole flow): book 1's brave path
  // set courage=3, and that var_state carried through the real reading-state
  // persistence into book 2, unlocking the choice gated on courage>=2. That
  // choice is hidden on a fresh, non-carried play of book 2 (asserted by the
  // next test), so its presence here proves the carry happened rather than
  // being a choice that is simply always shown. See scripts/seed_dev_data.py's
  // _series_blob for the gated choice and its condition.
  await expect(page.getByTestId('choice-c_n_e2_carried')).toBeVisible()
})

test('book 2 played fresh, without a carried courage, hides the gated choice', async ({
  page,
}) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Open book 2 directly from the shelf: a fresh read with no book-1 state to
  // carry in, so courage stays at its initial 0. This is the negative half of
  // the carries_state proof: the courage>=2 choice unlocked in the test above
  // is genuinely gated, not unconditionally rendered.
  await page.getByRole('link', { name: 'Ember Trail 2' }).click()
  await expect(page).toHaveURL(/\/read\/[^/]+\/s_dev_ember_2\//)
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toContainText(
    'Ember Trail 2: the trail begins.'
  )

  // The plain choice is always offered; the courage-gated choice is hidden
  // (visibleChoices drops a false-condition choice, matching runtime semantics)
  // because no book-1 courage was carried in.
  await expect(page.getByTestId('choice-c_n_e2_plain')).toBeVisible()
  await expect(page.getByTestId('choice-c_n_e2_carried')).toHaveCount(0)
})
