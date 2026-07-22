import { expect, test, type Page } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import {
  authorizeDevice,
  BACKEND,
  requireBackend,
  resetRealState,
  revokeDevice,
} from './real-stack'

/**
 * Real-API G3 structural gap (Phase 7.3,
 * docs/planning/handoff-test-coverage-robustness-2026-07-22.md): proves the
 * client-side player engine (frontend/src/player/engine.ts) reaches the SAME
 * node path and ending offline as the real backend reaches online, for the
 * identical choice sequence, on a story with genuine variable-gated
 * branching. The risk this guards against: engine.ts is a hand-maintained TS
 * port of the Python reference engine (src/cyo_adventure/player/engine.py);
 * a silent drift between them would route an offline reader down a
 * different branch than an online one without either side raising an error.
 *
 * Story: "The Clockwork Garden" (s_clockwork_garden). It is the only seeded,
 * published story with real condition-gated choices (s_tide_pools has no
 * variables at all; the seeded Ember Trail series books set a `courage`
 * effect but both entry choices converge on the same node regardless, so
 * neither exercises branch-VISIBILITY parity). At node n_gate, three choices
 * coexist: c_unlock (has_key==true, false here, so HIDDEN), c_climb
 * (courage>=2, true here, so VISIBLE), and c_wait (unconditional, always
 * VISIBLE). Reaching n_gate with courage==2 and has_key==false and asserting
 * that exact visible/hidden split, identically online and offline, is the
 * branch-parity assertion this spec is built around.
 *
 * Fixed choice sequence (n_start -> n_clock_end, ending e_clock "The Garden
 * Wakes"): c_hedge -> c_squeeze (courage 0->1) -> c_to_gate2 (courage 1->2)
 * -> c_climb (n_gate's courage>=2 branch) -> c_wind. Final var_state is
 * {has_key: false, courage: 2}; final node path is [n_start, n_hedge,
 * n_clearing, n_gate, n_tower, n_clock_end].
 *
 * ## Backend cross-engine verification (not just client-vs-client)
 *
 * Comparing the offline pass only against the online pass would merely prove
 * the SAME TS engine agrees with itself across two runtimes; it says nothing
 * about the real Python engine. reading.py's PUT endpoint normally only
 * structurally validates a client-submitted save (player/replay.py's
 * "structural floor"); it independently REPLAYS the choice sequence through
 * the real Python engine only when the optional `choice_path` field is
 * present (currently unused by the frontend itself; debt item C5,
 * docs/planning/r1-deferred-debt-register.md). This spec exploits that
 * mechanism directly: after each pass's UI-driven sequence finishes, a raw
 * guardian-authorized fetch PUT resubmits the pass's own final state WITH
 * choice_path attached, forcing reading.py::_validate_against_pinned_version
 * -> player/replay.py::_check_replay -> the real Python StoryEngine to
 * replay all 5 choices independently. A 200 with a matching current_node and
 * var_state proves the Python engine reached the identical branch decision
 * at n_gate (courage>=2) that the TS engine did; a genuine divergence there
 * would surface as either a mismatched var_state/current_node or a 422 (the
 * Python engine's own choose() raises BusinessLogicError -> ValidationError
 * for an unavailable choice, see player/engine.py::choose and
 * player/replay.py::_check_replay).
 *
 * This verification call is deliberately issued only ONCE per pass, AFTER
 * that pass's UI is entirely done driving choices for its profile:
 * #CRITICAL: concurrency: ReaderPage.tsx's `revisionRef` only advances on
 * that page instance's own successful save; an out-of-band raw PUT issued
 * WHILE the browser still had more choices to click would bump the server's
 * state_revision behind the browser's back and manufacture a spurious 409
 * on the browser's own next save (the same mechanism offline-conflict-real
 * .spec.ts's file header documents deliberately exploiting for its OWN
 * conflict scenario). Sequencing this verification call after each pass's UI
 * is fully finished avoids that interference entirely.
 * #VERIFY: verifyBackendReplay is only called after the branch-point DOM
 * assertions and the final ending assertion for its pass, never in between.
 *
 * ## Profile isolation
 *
 * offline-conflict-real.spec.ts's file header claims sole-writer ownership
 * of s_clockwork_garden's reading_state row for the seeded "Dev Reader"
 * profile specifically; reading_state is keyed by (child_profile_id,
 * storybook_id), so two BRAND-NEW profiles minted here (one per pass) never
 * touch that row regardless of file-execution order within the
 * `real-backend` project. Both are deleted in `afterAll` (cascades the
 * reading_state row per db/models.py's ON DELETE CASCADE), leaving no extra
 * fixture behind on a normal run.
 *
 * #ASSUME: security: authorize_profile (api/deps.py) admits a guardian
 * principal for any profile in its own family for both GET and PUT, so the
 * seeded dev-guardian bearer can create/assign/verify without minting a real
 * child session token (same assumption kid-go-back-real.spec.ts relies on).
 * #VERIFY: a 403 anywhere below would mean that assumption broke.
 */

const STORYBOOK_ID = 's_clockwork_garden'
const DEV_GUARDIAN_BEARER = 'dev-guardian'

const CHOICE_SEQUENCE = ['c_hedge', 'c_squeeze', 'c_to_gate2', 'c_climb', 'c_wind'] as const
const FINAL_NODE = 'n_clock_end'
const FINAL_PATH = ['n_start', 'n_hedge', 'n_clearing', 'n_gate', 'n_tower', 'n_clock_end']
const FINAL_VAR_STATE = { has_key: false, courage: 2 }
const ENDING_ID = 'e_clock'

interface ReadingStateRow {
  current_node: string
  var_state: Record<string, boolean | number>
  path: string[]
  visit_set: string[]
  version: number
  state_revision: number
}

/** Mints a brand-new child profile in the seeded Dev Family, assigned the story. */
async function createAssignedProfile(displayName: string): Promise<string> {
  const createRes = await fetch(`${BACKEND}/api/v1/profiles`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName, age_band: '8-11' }),
  })
  expect(createRes.ok, `POST /profiles failed (HTTP ${createRes.status})`).toBe(true)
  const { id } = (await createRes.json()) as { id: string }

  const assignRes = await fetch(`${BACKEND}/api/v1/storybooks/${STORYBOOK_ID}/assignments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_ids: [id] }),
  })
  expect(assignRes.ok, `POST /assignments failed (HTTP ${assignRes.status})`).toBe(true)
  return id
}

/**
 * Best-effort cleanup, mirrors real-stack.ts's revokeDevice: never throws, so
 * a teardown hiccup does not mask the real test result. A stray profile is
 * reset by the next scripts/seed_dev_data.py run regardless.
 */
async function deleteProfile(profileId: string): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/profiles/${profileId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    })
    if (!res.ok && res.status !== 404) {
      console.warn(
        `[offline-online-parity] profile delete did not confirm (HTTP ${res.status}) for ${profileId}`
      )
    }
  } catch (err) {
    console.warn(
      `[offline-online-parity] profile delete errored for ${profileId}: ${err instanceof Error ? err.message : String(err)}`
    )
  }
}

function waitForReadingStatePut(page: Page) {
  return page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/reading-state/') &&
      res.url().includes(STORYBOOK_ID) &&
      res.request().method() === 'PUT',
    { timeout: 10_000 }
  )
}

async function fetchServerRow(profileId: string): Promise<ReadingStateRow> {
  const res = await fetch(`${BACKEND}/api/v1/reading-state/${profileId}/${STORYBOOK_ID}`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
  })
  expect(res.ok, `GET /reading-state failed (HTTP ${res.status})`).toBe(true)
  return (await res.json()) as ReadingStateRow
}

/**
 * See the file header's "Backend cross-engine verification" section: forces
 * the real Python engine to independently replay the full choice sequence
 * and confirms it lands on the identical final node/var_state the TS engine
 * (client, either online or post-sync-offline) already persisted.
 */
async function verifyBackendReplay(profileId: string, row: ReadingStateRow): Promise<void> {
  const res = await fetch(`${BACKEND}/api/v1/reading-state/${profileId}/${STORYBOOK_ID}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      version: row.version,
      current_node: row.current_node,
      var_state: row.var_state,
      path: row.path,
      visit_set: row.visit_set,
      state_revision: row.state_revision,
      choice_path: CHOICE_SEQUENCE,
      event_id: `verify-replay-${profileId}-${Date.now()}`,
    }),
  })
  const bodyText = res.ok ? '' : await res.text()
  expect(
    res.ok,
    `real Python-engine replay of choice_path ${JSON.stringify(CHOICE_SEQUENCE)} was rejected ` +
      `(HTTP ${res.status}): ${bodyText}`
  ).toBe(true)
  const replayed = (await res.json()) as ReadingStateRow
  expect(replayed.current_node).toBe(FINAL_NODE)
  expect(replayed.var_state).toEqual(FINAL_VAR_STATE)
}

let onlineProfileId: string
let offlineProfileId: string
let onlineFinalRow: ReadingStateRow
let offlineFinalRow: ReadingStateRow
// Exact display names, not just the "E2E Parity Online/Offline" prefix: a
// prior run's afterAll cleanup can be skipped (a failed earlier test in this
// same describe block still runs afterAll, but a hard browser/context crash
// or a killed process would not), leaving an old profile with the same
// prefix but a different Date.now() suffix in the kid picker. A prefix-only
// getByText then resolves to more than one picker tile and throws a strict
// mode violation instead of the intended profile's own tile.
// #VERIFY: naming the profile with the full suffix here, and matching on the
// full name below, keeps this test correct even when a stale same-prefix
// profile is present from an earlier, incompletely cleaned-up run.
let onlineProfileName: string
let offlineProfileName: string

test.describe.serial('G3: offline reading reaches the same branch as the real backend', () => {
  test.beforeAll(async () => {
    // Per-file reset so this file is order-independent in the shared-DB tier.
    resetRealState()
    await requireBackend()
    const suffix = Date.now()
    onlineProfileName = `E2E Parity Online ${suffix}`
    offlineProfileName = `E2E Parity Offline ${suffix}`
    onlineProfileId = await createAssignedProfile(onlineProfileName)
    offlineProfileId = await createAssignedProfile(offlineProfileName)
  })

  test.afterAll(async () => {
    await deleteProfile(onlineProfileId)
    await deleteProfile(offlineProfileId)
  })

  test('online: the real backend drives the branching sequence to the real ending', async ({
    context,
    page,
  }) => {
    const deviceGrant: DeviceGrant = await authorizeDevice(context)
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })

    const mountSave = waitForReadingStatePut(page)
    await page.goto('/kids')
    await page.getByText(onlineProfileName, { exact: true }).click()
    await expect(page).toHaveURL(/\/library\//)
    await page.getByRole('link', { name: 'The Clockwork Garden' }).click()
    await expect(page).toHaveURL(/\/read\//)
    await expect(page.getByTestId('reader')).toBeVisible()
    await mountSave

    // n_start -> n_hedge -> n_clearing (courage 0 -> 1 -> 2), waiting for each
    // real save so a click never races the server (matches
    // offline-conflict-real.spec.ts's sequencing rationale).
    for (const choiceId of ['c_hedge', 'c_squeeze', 'c_to_gate2'] as const) {
      const saved = waitForReadingStatePut(page)
      await page.getByTestId(`choice-${choiceId}`).click()
      await saved
    }

    // Branch point: n_gate with has_key=false, courage=2. c_unlock's
    // condition is false so engine.ts must not render it at all (visible
    // choices are simply omitted, not disabled); c_climb's condition is
    // true and c_wait is unconditional, so both render.
    await expect(page.getByTestId('passage-body')).toContainText('The iron gate ticks')
    await expect(page.getByTestId('choice-c_unlock')).toHaveCount(0)
    await expect(page.getByTestId('choice-c_climb')).toBeVisible()
    await expect(page.getByTestId('choice-c_wait')).toBeVisible()

    for (const choiceId of ['c_climb', 'c_wind'] as const) {
      const saved = waitForReadingStatePut(page)
      await page.getByTestId(`choice-${choiceId}`).click()
      await saved
    }

    await expect(page.getByTestId('ending-screen')).toBeVisible()
    await expect(page.getByTestId('ending-id')).toHaveText(ENDING_ID)

    onlineFinalRow = await fetchServerRow(onlineProfileId)
    expect(onlineFinalRow.current_node).toBe(FINAL_NODE)
    expect(onlineFinalRow.path).toEqual(FINAL_PATH)
    expect(onlineFinalRow.visit_set.slice().sort()).toEqual(FINAL_PATH.slice().sort())
    expect(onlineFinalRow.var_state).toEqual(FINAL_VAR_STATE)

    // Real backend (Python engine) cross-check, issued only now that the UI
    // is done driving this profile (see file header #CRITICAL note).
    await verifyBackendReplay(onlineProfileId, onlineFinalRow)

    await revokeDevice(deviceGrant)
  })

  test('offline: the client engine alone reaches the same branch, then syncs to the same real state', async ({
    context,
    page,
  }) => {
    const deviceGrant: DeviceGrant = await authorizeDevice(context)
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })

    // Open online ONCE first: this is how the storybook blob and the
    // initial reading state land in this brand-new context's IndexedDB
    // cache (offline/db.ts), matching frontend/e2e/reader.spec.ts's mocked
    // "plays to an ending with the network disabled" setup. The mount save
    // still happens online, so it is not queued.
    const mountSave = waitForReadingStatePut(page)
    await page.goto('/kids')
    await page.getByText(offlineProfileName, { exact: true }).click()
    await expect(page).toHaveURL(/\/library\//)
    await page.getByRole('link', { name: 'The Clockwork Garden' }).click()
    await expect(page).toHaveURL(/\/read\//)
    await expect(page.getByTestId('reader')).toBeVisible()
    await mountSave

    await context.setOffline(true)

    // Identical sequence, driven purely client-side: no waitForResponse
    // (there is no network), just DOM assertions that engine.ts computed
    // the same next node offline as the backend did online.
    for (const choiceId of ['c_hedge', 'c_squeeze', 'c_to_gate2'] as const) {
      await page.getByTestId(`choice-${choiceId}`).click()
    }

    await expect(page.getByTestId('passage-body')).toContainText('The iron gate ticks')
    await expect(page.getByTestId('choice-c_unlock')).toHaveCount(0)
    await expect(page.getByTestId('choice-c_climb')).toBeVisible()
    await expect(page.getByTestId('choice-c_wait')).toBeVisible()

    await page.getByTestId('choice-c_climb').click()
    await page.getByTestId('choice-c_wind').click()

    await expect(page.getByTestId('ending-screen')).toBeVisible()
    await expect(page.getByTestId('ending-id')).toHaveText(ENDING_ID)

    // Reconnect: Playwright's setOffline(false) dispatches the browser
    // 'online' event, which useReplayOnReconnect.ts listens for to flush
    // offline/sync.ts's queue. The success toast only fires when every
    // queued write replayed cleanly (ReaderRoute.tsx's handleReplayOutcome),
    // so waiting for it is the app's own "sync is fully done" signal.
    await context.setOffline(false)
    await expect(page.getByText('All caught up! Your reading is saved.')).toBeVisible({
      timeout: 15_000,
    })

    offlineFinalRow = await fetchServerRow(offlineProfileId)
    expect(offlineFinalRow.current_node).toBe(FINAL_NODE)
    expect(offlineFinalRow.path).toEqual(FINAL_PATH)
    expect(offlineFinalRow.visit_set.slice().sort()).toEqual(FINAL_PATH.slice().sort())
    expect(offlineFinalRow.var_state).toEqual(FINAL_VAR_STATE)

    await verifyBackendReplay(offlineProfileId, offlineFinalRow)

    await revokeDevice(deviceGrant)
  })

  test('parity: the offline-computed final state matches the online-computed final state exactly', () => {
    // The core G3 assertion: two different profiles, one driven online and
    // one driven offline-then-synced, through the identical choice
    // sequence, land on byte-for-byte the same node path, visit set, ending,
    // and variable state. Both rows were already independently confirmed
    // against the real Python engine in the tests above; this comparison
    // proves neither runtime silently diverged from the other either.
    expect(offlineFinalRow.current_node).toBe(onlineFinalRow.current_node)
    expect(offlineFinalRow.path).toEqual(onlineFinalRow.path)
    expect(offlineFinalRow.visit_set.slice().sort()).toEqual(
      onlineFinalRow.visit_set.slice().sort()
    )
    expect(offlineFinalRow.var_state).toEqual(onlineFinalRow.var_state)
  })
})
