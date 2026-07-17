import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API rating persistence: taps a star on a real seeded book and confirms
 * the rating survives a reload, i.e. it actually reached the database rather
 * than only updating client-side state. Closes the coverage-matrix gap
 * (mocked and component coverage existed for rating; no e2e-real spec did).
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
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('a tapped rating persists across reload', async ({ page }) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  const stars = page.getByRole('group', { name: 'Rate The Tide Pool Mystery' })
  await expect(stars).toBeVisible()
  await stars.getByRole('button', { name: '4 stars' }).click()
  await expect(stars.getByRole('button', { name: '4 stars' })).toHaveAttribute('aria-pressed', 'true')

  await page.reload()
  const starsAfterReload = page.getByRole('group', { name: 'Rate The Tide Pool Mystery' })
  await expect(starsAfterReload.getByRole('button', { name: '4 stars' })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
})
