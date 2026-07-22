import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

import { loadLanternStory } from './support/fixtures'

const lantern = loadLanternStory()

const READER_PATH = '/read/child-a/s_lantern_cave/1'

/**
 * 409 reconciliation (the last amber gap). NOTE the scope: this suite drives
 * the LIVE-save conflict path (a save returning 409). Per the product decision
 * (child-UX), a reading-state conflict is resolved by NEWEST-WRITE-WINS,
 * SILENTLY: the app adopts the server's newest row and keeps the child reading,
 * with no dialog ever shown. The other wired path, the offline queue's
 * reconnect flush (useReplayOnReconnect in ReaderRoute invokes replayQueue on
 * mount and on 'online'), is covered component-side in
 * src/reader/ReaderRoute.test.tsx, including its silent conflict discard, the
 * failed banner, and the "All caught up!" success toast for a clean replay. The
 * fresh browser context here has an empty queue, so the mount-time flush is a
 * no-op (replayed 0) and never toasts into these assertions.
 *
 * ReaderPage persists on mount, not only on the first choice: Reader.tsx's
 * progress effect fires `onProgress` for the initial reading state as soon
 * as the machine mounts (frontend/src/reader/Reader.tsx:41-43), so the first
 * PUT (and thus the 409) arrives before any choice click could fire. The
 * silent adoption is asserted right after `reader` is visible; no choice click.
 */

// What "the other device" saved: further along, at the cave fork, revision 5.
const SERVER_ROW = {
  current_node: 'n_cave_fork',
  var_state: {},
  path: ['n_entrance', 'n_cave_fork'],
  visit_set: ['n_entrance', 'n_cave_fork'],
  version: 1,
  state_revision: 5,
  save_slots: {},
}

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /read/* redirects to guardian login.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
})

test('a 409 on save silently adopts the server position and re-saves it', async ({ page }) => {
  const putBodies: Array<Record<string, unknown>> = []
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    putBodies.push(route.request().postDataJSON() as Record<string, unknown>)
    if (putBodies.length === 1) {
      return route.fulfill({ status: 409, json: { current_row: SERVER_ROW } })
    }
    return route.fulfill({
      status: 200,
      json: { ...SERVER_ROW, state_revision: putBodies.length + 4 },
    })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  // Newest-write-wins: the reader silently adopts the server row and re-saves
  // it at the server's revision (5), with no dialog shown to the child.
  await expect.poll(() => putBodies.length).toBeGreaterThanOrEqual(2)
  expect(putBodies[1].state_revision).toBe(5)
  await expect(page.getByTestId('conflict-dialog')).toHaveCount(0)
  await expect(page.getByText('You were reading on another device')).toHaveCount(0)
})

test('a 409 on save moves the reader to the server position, no dialog', async ({ page }) => {
  let puts = 0
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    puts += 1
    if (puts === 1) return route.fulfill({ status: 409, json: { current_row: SERVER_ROW } })
    return route.fulfill({ status: 200, json: SERVER_ROW })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  // The reader remounts seeded from the adopted server row: the cave fork.
  // No dialog and no "which place do you want to keep?" prompt ever appear.
  await expect(page.getByText('The cave splits.')).toBeVisible()
  await expect(page.getByTestId('conflict-dialog')).toHaveCount(0)
})
