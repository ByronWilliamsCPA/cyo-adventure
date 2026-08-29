import { expect, test, type Page } from '@playwright/test'

import { authorizeDevice, BACKEND, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API offline-queue replay-on-reconnect, driven through an actual
 * Playwright `context.setOffline()` network toggle (never a route mock),
 * verifying `useReplayOnReconnect` -> `replayQueue()`
 * (frontend/src/offline/sync.ts) against the real backend for two distinct
 * outcomes:
 *
 * 1. A clean reconnect: every queued offline write replays and lands on the
 *    real `reading_state` row. The app's own "All caught up!" success signal
 *    (ReaderRoute.tsx's `handleReplayOutcome`) is used as the completion
 *    oracle, then cross-checked against a direct GET of the persisted row so
 *    the assertion does not just trust the toast.
 * 2. A genuine reconnect-time CONFLICT: a real second `BrowserContext`
 *    ("device B") advances the same real `reading_state` row while "device A"
 *    is offline; when A reconnects, `replayQueue`'s own PUT for the stale
 *    queued write gets a real 409 from the real backend. Per the product
 *    decision documented in ReaderRoute.tsx (`o.conflicts.length > 0`
 *    suppresses both the success toast and the failed-banner), the app must
 *    show neither; critically, `replayQueue`'s 409 branch never resends the
 *    stale write (frontend/src/offline/sync.ts, the `conflicted` latch), so
 *    it can never silently clobber device B's real, newer save. This spec
 *    proves that data-integrity property against the real backend rather
 *    than trusting the code comment alone.
 *
 * Distinct from the existing real-backend offline coverage:
 * - offline-online-parity-real.spec.ts drives a SINGLE profile through a full
 *   offline session and asserts branch-parity between the TS and Python
 *   engines; it never has a second device and never hits a reconnect-time
 *   conflict.
 * - offline-conflict-real.spec.ts's four conflicts are all LIVE 409s from two
 *   always-online devices racing ReaderPage's in-session save path, never a
 *   queued write replayed after a genuine offline period.
 * Neither exercises `replayQueue`'s `conflicted` branch against a real
 * backend; this spec is the one that does.
 *
 * Story: "The Clockwork Garden" (s_clockwork_garden), same as
 * offline-online-parity-real.spec.ts. Brand-new profiles are minted per run
 * (never the shared seeded "Dev Reader"), so this file's reading_state rows
 * are exclusively its own regardless of file-execution order in the shared
 * `real-backend` project (`fullyParallel: false` still shares one DB across
 * files).
 *
 * #CRITICAL: concurrency: in the conflict test, device B's mount-time save
 * must land on the real server strictly AFTER device A has gone offline and
 * queued its own choice, and strictly BEFORE device A reconnects, or the
 * revision A's queued write is rebased against would not actually be stale
 * and no conflict would occur. Every step below is sequenced with
 * `page.waitForResponse` (registered before the triggering action, the same
 * pattern offline-conflict-real.spec.ts and offline-online-parity-real.spec.ts
 * use) so the ordering is deterministic rather than a timing race.
 * #VERIFY: `waitForConflictPut` below asserts the real 409 fires during
 * device A's reconnect replay, not merely that no error is thrown.
 */

const STORYBOOK_ID = 's_clockwork_garden'
const STORYBOOK_TITLE = 'The Clockwork Garden'
const DEV_GUARDIAN_BEARER = 'dev-guardian'

// The exact banner text ReaderRoute.tsx renders on a genuine replay FAILURE
// (o.failed.length > 0). Asserting its absence, alongside the toast's and the
// live-save conflict dialog's, pins down that a reconnect CONFLICT (distinct
// from a failure) surfaces none of the app's three other replay signals.
const REPLAY_FAILED_BANNER_TEXT =
  "We couldn't save some of your reading. Ask a grown-up if this keeps happening."
const SUCCESS_TOAST_TEXT = 'All caught up! Your reading is saved.'

interface ReadingStateRow {
  current_node: string
  var_state: Record<string, boolean | number>
  state_revision: number
}

/** Mints a brand-new child profile in the seeded Dev Family, assigned the story. */
async function createAssignedProfile(displayName: string): Promise<string> {
  const createRes = await fetch(`${BACKEND}/api/v1/profiles`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName, age_band: '10-13' }),
    // Must match (or exceed) s_clockwork_garden's own 10-13 band. The H1
    // ceiling in api/assignments.py refuses to assign a book banded ABOVE the
    // target profile, so the '8-11' this previously sent made the very next
    // POST /assignments a deterministic 400 and the whole describe block
    // failed in beforeAll. The gate is correct; the fixture was not.
    signal: AbortSignal.timeout(5000),
  })
  expect(createRes.ok, `POST /profiles failed (HTTP ${createRes.status})`).toBe(true)
  const { id } = (await createRes.json()) as { id: string }

  const assignRes = await fetch(`${BACKEND}/api/v1/storybooks/${STORYBOOK_ID}/assignments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_ids: [id] }),
    signal: AbortSignal.timeout(5000),
  })
  expect(assignRes.ok, `POST /assignments failed (HTTP ${assignRes.status})`).toBe(true)
  return id
}

/** Best-effort cleanup; never throws (mirrors real-stack.ts's revokeDevice). */
async function deleteProfile(profileId: string): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/profiles/${profileId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok && res.status !== 404) {
      console.warn(
        `[offline-reconnect] profile delete did not confirm (HTTP ${res.status}) for ${profileId}`
      )
    }
  } catch (err) {
    console.warn(
      `[offline-reconnect] profile delete errored for ${profileId}: ${err instanceof Error ? err.message : String(err)}`
    )
  }
}

// #EDGE: timing-dependencies: matches by URL+method+status only, the same
// shape #290 traced kid-go-back-real.spec.ts's flaky failure to (queue
// position, not the response's own identity). The "at most one 200 ... ever
// pending at once" bound below is already false at MOUNT, not just at a
// queued replay: these profiles are age_band '10-13' (a FLOWED_BANDS entry),
// so a mount (mountSave/mountA/mountB below) does not stop at n_open, it
// auto-flows through n_open's single unconditional choice and issues a PUT
// for both n_open and n_start before the reader shows a choice to click. A
// live probe confirms it: instrumenting page.on('request')/page.on('response')
// at the moment a mount's own reader-visible assertion resolves shows both
// PUTs issued but only n_open's response delivered by then, so a second
// 200 candidate is genuinely still pending. This file is safe anyway for a
// narrower reason: no assertion in this file reads a field off the captured
// response body (the actual data checks all go through a fresh
// fetchServerRow() GET, or a Playwright `.poll`/toast wait). The queued
// three-choice replay on reconnect does still fire multiple sequential
// PUTs, but this wait's only job is "some save landed", not "which one".
// #VERIFY: if a future edit here starts asserting on this promise's own
// `.json()`, that would make this predicate unsafe; that call site needs
// kid-go-back-real.spec.ts's node-matching predicate instead, not this
// URL/status-only form.
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

async function fetchServerRow(profileId: string): Promise<ReadingStateRow> {
  const res = await fetch(`${BACKEND}/api/v1/reading-state/${profileId}/${STORYBOOK_ID}`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    signal: AbortSignal.timeout(5000),
  })
  expect(res.ok, `GET /reading-state failed (HTTP ${res.status})`).toBe(true)
  // The endpoint answers 200 with { state: ReadingStateRow | null }
  // (ReadingStateResultView); every call site in this file fetches after a
  // save has already happened, so a null state here means the save the test
  // just made did not land, not a legitimate first-time-reader absence.
  const body = (await res.json()) as { state: ReadingStateRow | null }
  expect(body.state, 'GET /reading-state returned null state after a save').not.toBeNull()
  return body.state as ReadingStateRow
}

async function openClockworkGarden(page: Page, profileName: string): Promise<void> {
  await page.goto('/kids')
  await page.getByText(profileName, { exact: true }).click()
  await expect(page).toHaveURL(/\/library\//)
  await page.getByRole('link', { name: STORYBOOK_TITLE }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()
}

test.describe.serial('Offline queue replay-on-reconnect via a real network toggle', () => {
  let cleanProfileId: string
  let cleanProfileName: string
  let conflictProfileId: string
  let conflictProfileName: string

  test.beforeAll(async () => {
    await requireBackend()
    const suffix = Date.now()
    cleanProfileName = `E2E Reconnect Clean ${suffix}`
    conflictProfileName = `E2E Reconnect Conflict ${suffix}`
    cleanProfileId = await createAssignedProfile(cleanProfileName)
    conflictProfileId = await createAssignedProfile(conflictProfileName)
  })

  test.afterAll(async () => {
    await deleteProfile(cleanProfileId)
    await deleteProfile(conflictProfileId)
  })

  test('clean reconnect: every queued offline choice replays and lands on the real backend', async ({
    context,
    page,
  }) => {
    const grant = await authorizeDevice(context)
    // #CRITICAL: security: the grant is a live credential, so every path out of
    // this test must revoke it. Without the finally, any assertion failure below
    // leaves an unrevoked device grant behind, which is how a red run can still
    // leak an authorized device (mirrors the sibling conflict test's pattern).
    // #VERIFY: revokeDevice runs on both the pass and the fail path.
    try {
      await context.addInitScript(() => {
        window.localStorage.setItem('auth_token', 'dev-child')
      })

      const mountSave = waitForSavedPut(page)
      await openClockworkGarden(page, cleanProfileName)
      await mountSave

      await context.setOffline(true)

      // Three choices made purely client-side while genuinely offline; each one
      // enqueues a write (offline/sync.ts's saveProgress -> OfflineError ->
      // enqueueWrite) and never reaches the network until reconnect.
      for (const choiceId of ['c_hedge', 'c_squeeze', 'c_to_gate2'] as const) {
        await page.getByTestId(`choice-${choiceId}`).click()
      }
      await expect(page.getByTestId('passage-body')).toContainText('The iron gate ticks')

      // Reconnect: Playwright's setOffline(false) dispatches the browser
      // 'online' event, which useReplayOnReconnect.ts listens for to flush the
      // queue. Registering the wait BEFORE flipping back online, per this
      // file's dependent-ordering rationale.
      const replayed = waitForSavedPut(page)
      await context.setOffline(false)
      await replayed
      await expect(page.getByText(SUCCESS_TOAST_TEXT)).toBeVisible({ timeout: 15_000 })

      const row = await fetchServerRow(cleanProfileId)
      expect(row.current_node).toBe('n_gate')
      expect(row.var_state).toEqual({ has_key: false, courage: 2 })
    } finally {
      await revokeDevice(grant)
    }
  })

  test('conflict on reconnect: a real second device advances the row while offline; the stale replay 409s and never clobbers it', async ({
    browser,
  }) => {
    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    const grantA = await authorizeDevice(contextA)
    const grantB = await authorizeDevice(contextB)
    await contextA.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await contextB.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()

    try {
      const mountA = waitForSavedPut(pageA)
      await openClockworkGarden(pageA, conflictProfileName)
      await mountA
      const rowAfterAMount = await fetchServerRow(conflictProfileId)

      await contextA.setOffline(true)
      // Queued locally; base_revision is A's cached (now stale-to-be) revision.
      await pageA.getByTestId('choice-c_hedge').click()

      // Device B, still online, opens the SAME profile+story: its own
      // mount-time save re-persists the server's still-n_start row and bumps
      // the real revision forward, exactly like offline-conflict-real
      // .spec.ts's "device B opens second" step -- the mechanism that makes
      // A's queued write stale.
      const mountB = waitForSavedPut(pageB)
      await openClockworkGarden(pageB, conflictProfileName)
      await mountB
      const rowAfterBMount = await fetchServerRow(conflictProfileId)
      expect(rowAfterBMount.state_revision).toBeGreaterThan(rowAfterAMount.state_revision)

      const conflicted = waitForConflictPut(pageA)
      await contextA.setOffline(false)
      await conflicted // proves replayQueue actually fired and hit a real 409

      // Per ReaderRoute.tsx's handleReplayOutcome: a conflict outcome shows
      // neither the success toast nor the failed/"ask a grown-up" banner,
      // and (unlike a LIVE save 409) there is no conflict dialog on this
      // reconnect-replay path at all.
      await expect(pageA.getByText(SUCCESS_TOAST_TEXT)).toHaveCount(0)
      await expect(pageA.getByTestId('conflict-dialog')).toHaveCount(0)
      await expect(pageA.getByText(REPLAY_FAILED_BANNER_TEXT)).toHaveCount(0)

      // Data-integrity: replayQueue's 409 branch dequeues the stale write and
      // pushes it to outcome.conflicts WITHOUT ever resending it (see the
      // `conflicted` latch in frontend/src/offline/sync.ts), so it cannot
      // silently overwrite device B's real, newer save.
      const finalRow = await fetchServerRow(conflictProfileId)
      expect(finalRow.state_revision).toBe(rowAfterBMount.state_revision)
      expect(finalRow.current_node).toBe('n_start')
    } finally {
      await revokeDevice(grantA)
      await revokeDevice(grantB)
      await contextA.close()
      await contextB.close()
    }
  })
})
