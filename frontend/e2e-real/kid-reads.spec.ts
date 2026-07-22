import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API kid journey: picker -> library -> read to an ending. No route
 * mocks; every /api call hits uvicorn through the preview proxy, authorized
 * as the seeded dev-child subject (ENVIRONMENT=local trusts the bearer token).
 * The kid surface is gated by DeviceAuthorizedRoute (ADR-014), so a real
 * device grant is minted and injected before the dev-child bearer.
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

test('the seeded child reads a real story to an ending', async ({ page }) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Open a specific standalone book by title. The library also carries the
  // two-book "Ember Trail" series (WS-G seed), so clicking the shelf's first
  // card blindly can land on a series book and leave server-side reading state
  // that resumes series-continue-real.spec.ts past its start node (the reader
  // restores the last persisted node). Pinning a standalone title keeps this
  // smoke isolated from that spec regardless of shelf ordering.
  await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  // A blind choice-walk that only checks it reaches an ending would pass even
  // if the backend served blank, identical, or garbled passages. Assert the
  // child actually sees real prose that CHANGES between nodes: the current
  // passage body must be non-empty prose at the start, and after at least one
  // choice the body must advance to a different, non-empty passage.
  const passageText = async (): Promise<string> =>
    (await page.getByTestId('passage-body').innerText()).trim()
  // A word of 3+ letters is the "real prose, not blank/garbled" signal used at
  // every node below (a run of punctuation or a single stray glyph fails it).
  const REAL_PROSE = /[A-Za-z]{3,}/

  const firstBody = await passageText()
  expect(firstBody).toMatch(REAL_PROSE)

  let previousBody = firstBody
  let advancedToNewPassage = false
  for (let i = 0; i < 40; i += 1) {
    if (await page.getByTestId('ending-screen').count()) break
    await page.locator('[data-testid^="choice-"]').first().click()
    // Settle on the next node: either the ending screen renders, or the reading
    // passage advances to a new, different body. A backend serving an identical
    // or blank body for the next node never satisfies this and fails here.
    await expect
      .poll(async () =>
        (await page.getByTestId('ending-screen').count())
          ? '__ended__'
          : await passageText()
      )
      .not.toBe(previousBody)
    if (await page.getByTestId('ending-screen').count()) break
    const body = await passageText()
    expect(body).toMatch(REAL_PROSE)
    advancedToNewPassage = true
    previousBody = body
  }
  // At least one reading-node -> reading-node transition happened (the "after a
  // choice, the passage changes" guarantee), not just an immediate ending.
  expect(advancedToNewPassage).toBe(true)

  // The ending screen must show real ending prose, not an empty celebration.
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  const endingBody = (
    await page.getByTestId('ending-screen').getByTestId('passage-body').innerText()
  ).trim()
  expect(endingBody).toMatch(REAL_PROSE)
})
