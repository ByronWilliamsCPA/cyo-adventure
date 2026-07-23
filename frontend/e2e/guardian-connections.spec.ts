import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian family-connections consent flow (ADR-016 ring 2, register G17):
 * a guardian's own side of a cross-family recommendation link, set up by the
 * app admin (the cousins case). Nothing flows until BOTH families' guardians
 * have consented (dual-consent), and revoking is unilateral and immediate.
 * This is privacy-load-bearing -- it is the guardian-facing gate that decides
 * whether a child's book activity crosses a family boundary -- and until now
 * had no browser-level coverage, only the component test
 * (src/guardian/ConnectionsPage.test.tsx).
 *
 * Unlike the component test, this spec drives the real confirm-dialog gate
 * end-to-end and asserts the exact HTTP method/path/id the mutation fires
 * with, proving the "confirm before calling" contract at the network layer
 * rather than only at the mocked-axios-instance layer.
 */

type ConnectionDirection = 'viewer' | 'sharer'

interface FamilyConnectionMineItem {
  id: string
  direction: ConnectionDirection
  counterpart_family_id: string
  counterpart_family_name: string
  my_consent: boolean
  active: boolean
  created_at: string
}

const VIEWER_ITEM: FamilyConnectionMineItem = {
  id: 'conn-1',
  direction: 'viewer',
  counterpart_family_id: 'fam-2',
  counterpart_family_name: 'Smith Family',
  my_consent: false,
  active: false,
  created_at: '2026-07-16T12:00:00Z',
}

const SHARER_ACTIVE_ITEM: FamilyConnectionMineItem = {
  id: 'conn-2',
  direction: 'sharer',
  counterpart_family_id: 'fam-3',
  counterpart_family_name: 'Jones Family',
  my_consent: true,
  active: true,
  created_at: '2026-07-16T12:00:00Z',
}

/**
 * The console shell fans out to these on every mount regardless of which
 * guardian page is active: GuardianShell's pending-count nav badge
 * (GET /v1/story-requests) and NotificationBell's unread poll
 * (GET /v1/notifications, fired via a setTimeout(0) on mount). Neither is
 * under test here; stub both to empty so nothing falls through to the
 * (absent) real backend proxy.
 */
async function mockShellFanOut(page: Page): Promise<void> {
  await page.route('**/api/v1/story-requests**', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications**', (route) =>
    route.fulfill({ json: { notifications: [], unread_count: 0 } })
  )
}

async function mockConnectionsList(
  page: Page,
  connections: FamilyConnectionMineItem[]
): Promise<void> {
  await page.route('**/api/v1/family-connections/mine', (route) =>
    route.fulfill({ json: { connections } })
  )
}

interface MutationCall {
  method: string
  id: string
}

/**
 * Route both the consent (POST) and revoke (DELETE) mutation, which share
 * the same URL shape: /v1/family-connections/{id}/consent
 * (connectionsApi.ts consent()/revoke()). Captures the method and the id
 * parsed out of the path so the test can assert the exact call the app made,
 * and fulfills with the caller-supplied post-mutation connection state.
 */
async function mockConnectionMutation(
  page: Page,
  responseBody: FamilyConnectionMineItem
): Promise<() => MutationCall | null> {
  let captured: MutationCall | null = null
  await page.route('**/api/v1/family-connections/*/consent', (route) => {
    const segments = new URL(route.request().url()).pathname.split('/').filter(Boolean)
    const id = segments[segments.length - 2]
    captured = { method: route.request().method(), id }
    return route.fulfill({ json: responseBody })
  })
  return () => captured
}

test('allowing a pending connection gates the POST behind the confirm dialog', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await mockShellFanOut(page)
  await mockConnectionsList(page, [VIEWER_ITEM])
  // Dual-consent: allowing does not flip `active`, only `my_consent`, until
  // the counterpart family's guardian also consents.
  const mutationCall = await mockConnectionMutation(page, {
    ...VIEWER_ITEM,
    my_consent: true,
    active: false,
  })

  await page.goto('/guardian/connections')
  await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible()
  // exact: the family name is in both the card name span AND the direction
  // summary paragraph; a substring match would be a strict-mode violation.
  await expect(page.getByText('Smith Family', { exact: true })).toBeVisible()
  await expect(page.getByText('Not active')).toBeVisible()

  await page.getByRole('button', { name: 'Allow' }).click()

  const dialog = page.getByRole('dialog', { name: 'Allow this connection?' })
  await expect(dialog).toBeVisible()
  await expect(
    dialog.getByText(/only takes effect once the Smith Family family's guardian agrees/)
  ).toBeVisible()

  // The dialog stages the action; it must not have called the backend yet.
  expect(mutationCall()).toBeNull()

  await dialog.getByRole('button', { name: 'Allow' }).click()

  await expect(dialog).toBeHidden()
  expect(mutationCall()).toEqual({ method: 'POST', id: 'conn-1' })

  // The row reflects the granted (but still pending counterpart) state:
  // Revoke replaces Allow, and the chip now shows the waiting status.
  await expect(page.getByRole('button', { name: 'Revoke' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Allow' })).toHaveCount(0)
  await expect(page.getByText('Waiting on the other family')).toBeVisible()
})

test('revoking an active connection gates the DELETE behind the confirm dialog', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await mockShellFanOut(page)
  await mockConnectionsList(page, [SHARER_ACTIVE_ITEM])
  const mutationCall = await mockConnectionMutation(page, {
    ...SHARER_ACTIVE_ITEM,
    my_consent: false,
    active: false,
  })

  await page.goto('/guardian/connections')
  // exact: as above, the name also appears inside the direction summary
  // paragraph, so a substring match would resolve two nodes.
  await expect(page.getByText('Jones Family', { exact: true })).toBeVisible()
  await expect(page.getByText('Active', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Revoke' }).click()

  const dialog = page.getByRole('dialog', { name: 'Revoke this connection?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(/Revoking now will stop this immediately/)).toBeVisible()

  // Staged, not yet fired.
  expect(mutationCall()).toBeNull()

  await dialog.getByRole('button', { name: 'Revoke' }).click()

  await expect(dialog).toBeHidden()
  expect(mutationCall()).toEqual({ method: 'DELETE', id: 'conn-2' })

  // The row reverts to the un-consented state: Allow replaces Revoke, and
  // the chip drops back to "Not active".
  await expect(page.getByRole('button', { name: 'Allow' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revoke' })).toHaveCount(0)
  await expect(page.getByText('Not active')).toBeVisible()
})
