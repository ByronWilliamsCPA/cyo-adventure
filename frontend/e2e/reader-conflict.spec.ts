import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

import { loadLanternStory } from './support/fixtures'

const lantern = loadLanternStory()

const READER_PATH = '/read/child-a/s_lantern_cave/1'

/**
 * 409 reconciliation (the last amber gap). NOTE the scope: this suite drives
 * the LIVE-save conflict path (a save returning 409 opens ConflictDialog with
 * two resolutions; both are covered here). The other wired path, the offline
 * queue's reconnect flush (useReplayOnReconnect in ReaderRoute invokes
 * replayQueue on mount and on 'online'), is covered component-side in
 * src/reader/ReaderRoute.test.tsx, including its conflict dialog, failed
 * banner, and the "All caught up!" success toast for a clean replay. The
 * fresh browser context here has an empty queue, so the mount-time flush is
 * a no-op (replayed 0) and never toasts into these assertions.
 *
 * ReaderPage persists on mount, not only on the first choice: Reader.tsx's
 * progress effect fires `onProgress` for the initial reading state as soon
 * as the machine mounts (frontend/src/reader/Reader.tsx:41-43), so the first
 * PUT (and thus the 409) arrives before any choice click could fire. The
 * dialog is asserted right after `reader` is visible; no choice click.
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

test('a 409 on save opens the conflict dialog; keeping this device rebases and re-saves', async ({
  page,
}) => {
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

  await expect(page.getByTestId('conflict-dialog')).toBeVisible()
  await expect(page.getByText('You were reading on another device')).toBeVisible()

  await page.getByTestId('conflict-keep').click()
  await expect(page.getByTestId('conflict-dialog')).toHaveCount(0)

  // resolveConflict('continue_from_this_device') rebases the local save onto
  // the server's revision before re-sending (offline/sync.ts:183-187).
  await expect.poll(() => putBodies.length).toBeGreaterThanOrEqual(2)
  expect(putBodies[1].state_revision).toBe(5)
})

test('choosing the newest place adopts the server position', async ({ page }) => {
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

  await expect(page.getByTestId('conflict-dialog')).toBeVisible()
  await page.getByTestId('conflict-use-newest').click()

  // The reader remounts seeded from the adopted server row: the cave fork.
  await expect(page.getByTestId('conflict-dialog')).toHaveCount(0)
  await expect(page.getByText('The cave splits.')).toBeVisible()
})
