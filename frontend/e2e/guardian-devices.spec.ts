import { expect, test } from '@playwright/test'
import type { BrowserContext, Page, Route } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian device management (`/guardian/devices`, DevicesPage.tsx, register
 * G15 / ADR-014's lost-device mitigation): list the family's authorized
 * device grants and revoke one. Had no browser-level coverage before this
 * file: `deviceGrantApi.ts.list()`/`.revoke()` were exercised only against a
 * mocked axios instance, never through the real confirm-dialog gate in a
 * routed page.
 */

const TABLET = {
  id: 'device-1',
  label: 'Kitchen tablet',
  created_at: '2026-07-01T00:00:00Z',
}

const PHONE = {
  id: 'device-2',
  label: null,
  created_at: '2026-07-20T00:00:00Z',
}

/** Guardian shell fan-out fired on every mount, same as other guardian specs. */
async function setUp(context: BrowserContext, page: Page): Promise<void> {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/story-requests**', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications**', (route) =>
    route.fulfill({ json: { notifications: [], unread_count: 0 } })
  )
}

test('renders every authorized device with its label or the unnamed fallback', async ({
  page,
  context,
}) => {
  await setUp(context, page)
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [TABLET, PHONE] }))

  await page.goto('/guardian/devices')

  await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible()
  await expect(page.getByText('Kitchen tablet')).toBeVisible()
  await expect(page.getByText('Unnamed device')).toBeVisible()
})

test('shows the empty state when the family has no authorized devices', async ({
  page,
  context,
}) => {
  await setUp(context, page)
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [] }))

  await page.goto('/guardian/devices')

  await expect(page.getByText('No devices authorized yet')).toBeVisible()
})

test('cancelling the revoke dialog leaves the device in place with no DELETE fired', async ({
  page,
  context,
}) => {
  await setUp(context, page)
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [TABLET] }))
  let deleteFired = false
  await page.route('**/api/v1/device-grants/*', (route) => {
    // Scoped to DELETE so an unrelated GET to the same path cannot fail this
    // negative test for the wrong reason.
    if (route.request().method() === 'DELETE') deleteFired = true
    return route.fulfill({ status: 204, body: '' })
  })

  await page.goto('/guardian/devices')
  await page.getByRole('button', { name: 'Revoke' }).click()
  const dialog = page.getByRole('dialog', { name: 'Revoke this device?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel' }).click()

  await expect(dialog).toBeHidden()
  await expect(page.getByText('Kitchen tablet')).toBeVisible()
  expect(deleteFired).toBe(false)
})

test('confirming the revoke dialog calls DELETE for that device and drops it from the list', async ({
  page,
  context,
}) => {
  await setUp(context, page)
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [TABLET, PHONE] }))
  let deletedPath: string | null = null
  let deletedMethod: string | null = null
  await page.route('**/api/v1/device-grants/*', (route: Route) => {
    // Record the verb, not just the path: without this the test would still pass
    // if revoke regressed to a different method (e.g. a soft-disable PATCH) on
    // the same URL, which is a real change in revocation semantics.
    deletedMethod = route.request().method()
    deletedPath = new URL(route.request().url()).pathname
    return route.fulfill({ status: 204, body: '' })
  })

  await page.goto('/guardian/devices')
  await page
    .getByRole('listitem')
    .filter({ hasText: 'Kitchen tablet' })
    .getByRole('button', { name: 'Revoke' })
    .click()
  const dialog = page.getByRole('dialog', { name: 'Revoke this device?' })
  await expect(dialog).toBeVisible()
  expect(deletedPath).toBeNull()

  await dialog.getByRole('button', { name: 'Revoke' }).click()

  await expect(dialog).toBeHidden()
  await expect.poll(() => deletedPath).toBe('/api/v1/device-grants/device-1')
  expect(deletedMethod).toBe('DELETE')
  await expect(page.getByText('Kitchen tablet')).toHaveCount(0)
  await expect(page.getByText('Unnamed device')).toBeVisible()
})

test('an unauthenticated visit to the devices route redirects to guardian login', async ({
  page,
}) => {
  await page.goto('/guardian/devices')

  await expect(page).toHaveURL(/\/guardian\/login$/)
})
