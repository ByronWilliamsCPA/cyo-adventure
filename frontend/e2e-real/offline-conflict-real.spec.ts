import { expect, test, type BrowserContext, type Page } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API S2 conflict race (register S2, "Conflict resolution"): two
 * genuinely separate Playwright `BrowserContext`s ("device A" and "device
 * B") authorized against the same seeded family/profile read "The Clockwork
 * Garden" (scripts/seed_dev_data.py, s_clockwork_garden) and race a save
 * against the real revision-based optimistic-concurrency check in
 * `PUT /api/v1/reading-state/{profile_id}/{storybook_id}`
 * (src/cyo_adventure/api/reading.py::put_reading_state). No route mocks:
 * every /api call hits uvicorn through the preview proxy, exactly as the
 * rest of this tier. Backend pytest coverage
 * (tests/integration/test_reading_state.py) already proves the 409
 * mechanism in isolation; this spec proves the FRONTEND's reconciliation
 * (ConflictDialog, offline/sync.ts resolveConflict) against a real 409 from
 * a real backend, mirroring the mocked frontend/e2e/reader-conflict.spec.ts
 * assertions one-for-one.
 *
 * Implements the real-backend gap described in
 * docs/planning/handoff-offline-conflict-real-backend-2026-07-16.md (that
 * doc lives on the PR #268 branch, not this one; fetched via
 * `git show origin/claude/frontend-testing-infrastructure-vag8z6:...`). It
 * closes test-traceability-matrix.md's S2 real-tier row and is picked up by
 * the nightly `e2e-real-nightly.yml` workflow (kept out of the PR path per
 * that matrix's action #6).
 *
 * ## Why explicit waits instead of a natural race
 *
 * The handoff doc's recipe assumes the FIRST save a device makes is a
 * post-choice save at `state_revision == 0`. In fact `ReaderPage.tsx`
 * persists on MOUNT, before any choice (see the identical note in
 * reader-conflict.spec.ts): opening the reader alone issues a PUT. Left to
 * run concurrently, two devices' mount-time saves would race the real
 * server nondeterministically, which is exactly the flakiness the handoff's
 * own #ASSUME/#VERIFY warns about.
 *
 * This spec sidesteps that race entirely rather than fighting it: every step
 * below is sequenced with `page.waitForResponse`, registered BEFORE the
 * action that triggers it (the same pattern naive-kid-misuse-real.spec.ts
 * uses), so each device's save is confirmed to have landed on the real
 * server before the next device acts. The conflict is still 100% real (a
 * genuine 409 from a genuine stale revision held in a genuine second
 * BrowserContext); only the ORDERING is deterministic, not faked.
 *
 * #CRITICAL: concurrency: the mechanism exploited here is that ReaderPage
 * keeps `revisionRef` in a plain React ref, updated only when THAT page
 * instance's own save succeeds. Device A's ref goes stale the moment device
 * B saves on the same row; the next save A issues (a real choice click)
 * carries A's stale revision and 409s for real. No mock ever stands in for
 * the server's response.
 * #VERIFY: each conflict assertion below checks both the 409 response
 * (waitForConflictPut) and the resulting ConflictDialog UI, so a change to
 * either the server contract or the frontend wiring fails this spec.
 *
 * #EDGE: data-integrity: "The Clockwork Garden" is deliberately not read by
 * any other e2e-real spec (kid-reads.spec.ts and series-continue-real.spec.ts
 * use the tide-pool story and the Ember Trail series respectively), so this
 * spec is the sole writer of that story's reading-state row for the seeded
 * "Dev Reader" profile. #VERIFY: if a future spec starts reading "The
 * Clockwork Garden" too, this spec's "device A creates the row" assumption
 * (test 1) breaks; give the new spec a different seeded story instead.
 *
 * #ASSUME: data-integrity: like approval-flow.spec.ts's approve test, this
 * spec mutates real server state across four dependent test cases; a CI
 * retry after a mid-sequence failure re-enters an already-advanced revision
 * and fails on a DIFFERENT assertion than the first attempt. #VERIFY: when
 * diagnosing a red run, always read the FIRST attempt's failure, not the
 * retry's (mirrors the existing guidance in playwright.config.ts).
 */

const STORYBOOK_TITLE = 'The Clockwork Garden'
const STORYBOOK_ID = 's_clockwork_garden'

async function openClockworkGarden(page: Page): Promise<void> {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)
  await page.getByRole('link', { name: STORYBOOK_TITLE }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()
}

/** Waits for the next SUCCESSFUL real reading-state save for this story. */
function waitForSavedPut(page: Page) {
  return page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/reading-state/') &&
      res.url().includes(STORYBOOK_ID) &&
      res.request().method() === 'PUT' &&
      res.status() === 200,
    { timeout: 10_000 }
  )
}

/** Waits for the next real 409 (revision conflict) for this story. */
function waitForConflictPut(page: Page) {
  return page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/reading-state/') &&
      res.url().includes(STORYBOOK_ID) &&
      res.request().method() === 'PUT' &&
      res.status() === 409,
    { timeout: 10_000 }
  )
}

test.describe.serial('S2: two real devices race a save on the same story', () => {
  let contextA: BrowserContext
  let contextB: BrowserContext
  let pageA: Page
  let pageB: Page
  let grantA: DeviceGrant | null = null
  let grantB: DeviceGrant | null = null

  test.beforeAll(async ({ browser }) => {
    await requireBackend()
    contextA = await browser.newContext()
    contextB = await browser.newContext()
    // Two independent, family-scoped device grants: real-stack.ts's
    // authorizeDevice mints one per BrowserContext, matching how two
    // physical devices would each hold their own grant (ADR-014).
    grantA = await authorizeDevice(contextA)
    grantB = await authorizeDevice(contextB)
    await contextA.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await contextB.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    pageA = await contextA.newPage()
    pageB = await contextB.newPage()
  })

  test.afterAll(async () => {
    // Best-effort, never throws (see revokeDevice); mirrors every other
    // e2e-real spec's per-test cleanup so a reused dev stack does not
    // accumulate live device-grant rows.
    if (grantA) await revokeDevice(grantA)
    if (grantB) await revokeDevice(grantB)
    await contextA?.close()
    await contextB?.close()
  })

  test('device A opens first and creates the real reading-state row', async () => {
    // ReaderPage's mount-time onProgress save (see file header) is the
    // FIRST-EVER write for this profile+story pair, so it must land at
    // state_revision 0 and create the row server-side at revision 1.
    const created = waitForSavedPut(pageA)
    await openClockworkGarden(pageA)
    await created
  })

  test('device B opens second, resyncs onto the real row, then advances it', async () => {
    // B's own mount-time load() does a fresh GET (its IndexedDB is empty,
    // a brand-new BrowserContext), finds device A's just-created row, and
    // adopts it as B's initial reading state: no conflict yet, this is the
    // ordinary cross-device resume path (K4). B's OWN mount-time save then
    // re-persists that adopted state, bumping the real row forward again.
    const resynced = waitForSavedPut(pageB)
    await openClockworkGarden(pageB)
    await resynced

    // Now B diverges for real: "Peer through the tall hedge" advances the
    // real row past device A's still-cached knowledge of it.
    const advanced = waitForSavedPut(pageB)
    await pageB.getByTestId('choice-c_hedge').click()
    await advanced
    await expect(pageB.getByTestId('passage-body')).toContainText(
      'Through a gap you glimpse a fountain and a tower wrapped in ivy.'
    )
  })

  test('a stale device A save gets a real 409; "Keep this device" rebases and wins', async () => {
    // Device A never learned about device B's resync-and-advance above (A's
    // page was never reloaded), so A's in-memory revision is now stale. A's
    // own next choice, "Search the leaning garden shed," carries that stale
    // revision and the real server rejects it with a genuine 409.
    const conflicted = waitForConflictPut(pageA)
    await pageA.getByTestId('choice-c_shed').click()
    await conflicted

    await expect(pageA.getByTestId('conflict-dialog')).toBeVisible()
    await expect(pageA.getByText('You were reading on another device')).toBeVisible()

    // resolveConflict('continue_from_this_device') rebases A's own local
    // choice onto the server's current revision and re-sends it for real
    // (offline/sync.ts); A's position wins and becomes the new real state.
    const rebased = waitForSavedPut(pageA)
    await pageA.getByTestId('conflict-keep').click()
    await rebased

    await expect(pageA.getByTestId('conflict-dialog')).toHaveCount(0)
    await expect(pageA.getByTestId('passage-body')).toContainText(
      'Dust hangs in the light. A toolbox sits beside a wall of strange brass gears.'
    )
  })

  test('a stale device B save gets a real 409; "Use the newest place" adopts the server row', async () => {
    // Symmetric to the previous case: device B is now the stale side (it
    // never learned about A's rebase-and-win). B's next choice, "Squeeze
    // bravely through the gap," 409s for real against A's now-current row.
    const conflicted = waitForConflictPut(pageB)
    await pageB.getByTestId('choice-c_squeeze').click()
    await conflicted

    await expect(pageB.getByTestId('conflict-dialog')).toBeVisible()
    await expect(pageB.getByText('You were reading on another device')).toBeVisible()

    // resolveConflict('use_newer_progress') adopts the server row locally
    // (no further network write) and ReaderPage remounts the Reader seeded
    // from it, so B's screen shows device A's real, server-canonical
    // position.
    await pageB.getByTestId('conflict-use-newest').click()

    await expect(pageB.getByTestId('conflict-dialog')).toHaveCount(0)
    await expect(pageB.getByTestId('passage-body')).toContainText(
      'Dust hangs in the light. A toolbox sits beside a wall of strange brass gears.'
    )
  })
})
