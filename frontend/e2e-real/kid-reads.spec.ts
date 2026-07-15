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

  for (let i = 0; i < 40; i += 1) {
    if (await page.getByTestId('ending-screen').count()) break
    await page.locator('[data-testid^="choice-"]').first().click()
  }
  await expect(page.getByTestId('ending-screen')).toBeVisible()
})
