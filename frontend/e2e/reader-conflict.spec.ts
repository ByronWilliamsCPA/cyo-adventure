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
      return route.fulfill({ status: 200, json: { state: null } })
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
      return route.fulfill({ status: 200, json: { state: null } })
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

/**
 * F-6d: the OTHER wired conflict path, the offline queue's reconnect flush
 * (useReplayOnReconnect in ReaderRoute.tsx, exercised in isolation by
 * ReaderRoute.test.tsx's "silently discards a replayed 409 without showing a
 * conflict dialog"), proven here end to end against a real IndexedDB queue
 * instead of a mocked queue module.
 *
 * A single route handler models three phases via closure state, mirroring
 * reader-reload-resume.spec.ts's one-handler-per-test convention rather than
 * re-registering page.route mid-test:
 *   1. normal: the mount-time save succeeds, establishing a real, confirmed
 *      server revision.
 *   2. offline: a choice tap's save transport-fails (route.abort(), which
 *      readerApi.ts maps to the same OfflineError a genuine outage would
 *      throw), so offline/sync.ts's saveProgress queues it into the real
 *      offline_queue store instead of throwing (this test captures that
 *      write's event_id before aborting the request). The engine still
 *      advances the passage locally and optimistically (same mechanism as
 *      this file's sibling reader.spec.ts "plays to an ending with the
 *      network disabled").
 *   3. reconnect: on page.reload(), TWO independent saves fire for the same
 *      story: ReaderPage's own fresh mount-time save (a brand-new event_id,
 *      resumed from the local cache) and ReaderRoute's queued-write replay
 *      (the SAME event_id captured in step 2). The mock routes on event_id,
 *      not call order, so the replay's write is deterministically the one
 *      that 409s, which is the exact case F-6d targets: a conflict
 *      discovered DURING the reconnect flush, not during a live in-session
 *      save (that path is already covered by the tests above).
 */
test('an offline choice queued for replay is silently resolved on reconnect', async ({ page }) => {
  let mode: 'normal' | 'offline' | 'reconnect' = 'normal'
  let offlineAttempts = 0
  let queuedEventId: string | null = null
  let reconnectPuts = 0
  let replayPuts = 0
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, json: { state: null } })
    }
    const body = route.request().postDataJSON() as { event_id?: string }
    if (mode === 'offline') {
      offlineAttempts += 1
      queuedEventId = body.event_id ?? null
      return route.abort('internetdisconnected')
    }
    if (mode === 'reconnect') {
      reconnectPuts += 1
      if (body.event_id === queuedEventId) {
        // The queued-write replay: this is the write F-6d targets, so it is
        // the one that discovers the cross-device conflict.
        replayPuts += 1
        return route.fulfill({
          status: 409,
          json: { current_row: { ...SERVER_ROW, state_revision: 1 } },
        })
      }
      // ReaderPage's own fresh mount-time save (a new event_id): unrelated to
      // the queue replay, accepted normally so it does not itself confuse
      // the assertions below.
      return route.fulfill({ status: 200, json: { ...SERVER_ROW, state_revision: 1 } })
    }
    // 'normal': establish a confirmed revision for the initial mount-time save.
    return route.fulfill({
      status: 200,
      json: { ...SERVER_ROW, current_node: 'n_entrance', path: ['n_entrance'], state_revision: 1 },
    })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  mode = 'offline'
  await page.getByTestId('choice-c_take_lantern').click()
  await expect(page.getByTestId('passage-body')).toContainText('The cave splits.')
  await expect.poll(() => offlineAttempts).toBeGreaterThanOrEqual(1)
  expect(queuedEventId).not.toBeNull()

  // Confirm the write actually landed in the real offline queue (not merely
  // attempted) before reloading, so the reconnect flush below replays a real
  // queued item rather than racing an in-flight IndexedDB write.
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            // Versionless open: pinning a version here breaks silently on every
            // DB_VERSION bump (opening an existing v4 database at 3 rejects
            // with VersionError, and onerror's -1 just fails the poll), while a
            // versionless open attaches at whatever version the app created.
            const req = indexedDB.open('cyo-reader')
            req.onerror = () => resolve(-1)
            req.onsuccess = () => {
              try {
                const countReq = req.result
                  .transaction('offline_queue', 'readonly')
                  .objectStore('offline_queue')
                  .count()
                countReq.onsuccess = () => resolve(countReq.result)
                countReq.onerror = () => resolve(-1)
              } catch {
                // Store missing (the app has not created it yet): report a
                // non-match so the poll retries instead of hanging.
                resolve(-1)
              }
            }
          })
      )
    )
    .toBeGreaterThanOrEqual(1)

  mode = 'reconnect'
  await page.reload()

  // Graceful reconnect: the reader stays put at the queued passage (never a
  // dead end, never the error screen), the replay conflict is silently
  // discarded (ReaderRoute.tsx's #ASSUME "newest-write-wins... the child is
  // never shown a ... dialog"), and the success toast is suppressed because a
  // conflict, not a clean replay, occurred.
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toContainText('The cave splits.')
  await expect(page.locator('.reader-error')).toHaveCount(0)
  await expect(page.getByTestId('conflict-dialog')).toHaveCount(0)
  await expect(page.getByText('You were reading on another device')).toHaveCount(0)
  await expect(page.getByText('All caught up! Your reading is saved.')).toHaveCount(0)
  await expect.poll(() => reconnectPuts).toBeGreaterThanOrEqual(1)
  await expect.poll(() => replayPuts).toBe(1)
})
