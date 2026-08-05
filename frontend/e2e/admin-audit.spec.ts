import { expect, test } from '@playwright/test'
import type { Route } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Admin audit log (`/admin/audit`, AuditPage.tsx, register A13): fills the
 * access-control gap left by admin-read-heavy.spec.ts's filter/paging
 * coverage and admin-touch-targets.spec.ts's tap-floor smoke, neither of
 * which asserts what happens for a non-admin caller or an unauthenticated
 * one, and neither of which drives "Clear filters" or a Previous-page click.
 */

const EVENT_1 = {
  id: 'evt-1',
  occurred_at: '2026-07-01T12:00:00Z',
  actor_id: 'admin-1',
  actor_role: 'admin',
  entity_type: 'user',
  entity_id: 'user-2',
  event_type: 'user_managed',
  from_state: null,
  to_state: null,
  payload: {},
}

const EVENT_2 = {
  id: 'evt-2',
  occurred_at: '2026-06-30T09:00:00Z',
  actor_id: 'admin-1',
  actor_role: 'admin',
  entity_type: 'storybook',
  entity_id: 's9',
  event_type: 'released',
  from_state: 'in_review',
  to_state: 'published',
  payload: {},
}

function queryParams(route: Route): URLSearchParams {
  return new URL(route.request().url()).searchParams
}

test('a signed-in admin sees the audit log with the recorded event', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/audit*', (route) =>
    route.fulfill({ json: { events: [EVENT_1], limit: 50, offset: 0, has_more: false } })
  )

  await page.goto('/admin/audit')

  await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'user: user-2' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'admin (admin-1)' })).toBeVisible()
})

test('clearing filters resets the kind filter and the page offset', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  const kindsRequested: (string | null)[] = []
  const offsetsRequested: (string | null)[] = []
  await page.route('**/api/v1/admin/audit*', (route) => {
    const params = queryParams(route)
    kindsRequested.push(params.get('kind'))
    offsetsRequested.push(params.get('offset'))
    if (params.get('kind') === 'user_managed') {
      return route.fulfill({ json: { events: [EVENT_1], limit: 50, offset: 0, has_more: false } })
    }
    return route.fulfill({
      json: { events: [EVENT_1, EVENT_2], limit: 50, offset: 0, has_more: true },
    })
  })

  await page.goto('/admin/audit')
  await page.getByLabel('Filter by event kind').selectOption('user_managed')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect.poll(() => kindsRequested.at(-1)).toBe('user_managed')

  await page.getByRole('button', { name: 'Clear filters' }).click()

  await expect.poll(() => kindsRequested.at(-1)).toBeNull()
  await expect.poll(() => offsetsRequested.at(-1)).toBe('0')
  await expect(page.getByLabel('Filter by event kind')).toHaveValue('')
})

test('paging to the next page and back fires offset=50 then offset=0', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  const offsetsRequested: (string | null)[] = []
  await page.route('**/api/v1/admin/audit*', (route) => {
    const params = queryParams(route)
    const offset = params.get('offset')
    offsetsRequested.push(offset)
    if (offset === '50') {
      return route.fulfill({ json: { events: [EVENT_2], limit: 50, offset: 50, has_more: false } })
    }
    return route.fulfill({
      json: { events: [EVENT_1], limit: 50, offset: 0, has_more: true },
    })
  })

  await page.goto('/admin/audit')
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect.poll(() => offsetsRequested.at(-1)).toBe('50')
  await expect(page.getByRole('cell', { name: 'storybook: s9' })).toBeVisible()

  await page.getByRole('button', { name: 'Previous page' }).click()

  await expect.poll(() => offsetsRequested.at(-1)).toBe('0')
  await expect(page.getByRole('cell', { name: 'user: user-2' })).toBeVisible()
})

test('a plain guardian visiting /admin/audit is sent back to the guardian console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'guardian' })
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  const adminAuditRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/admin/audit')) adminAuditRequests.push(request.url())
  })

  await page.goto('/admin/audit')

  await expect(page).toHaveURL(/\/guardian$/)
  expect(adminAuditRequests, 'a guardian must never reach the admin audit endpoint').toEqual([])
})

test('an unauthenticated visit to /admin/audit redirects to guardian login', async ({ page }) => {
  await page.goto('/admin/audit')

  await expect(page).toHaveURL(/\/guardian\/login$/)
})
