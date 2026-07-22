import { expect, test, type Page } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, BACKEND, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API K5 kid go-back path: Reader.tsx's "Go back" control (data-testid
 * "go-back") undoes the last choice by replaying the recorded node path
 * through the deterministic engine (player/engine.ts::back), never by
 * reversing effects. Go back is NOT purely client-side: Reader's onProgress
 * effect fires on every `reading` change, back included, so ReaderPage.tsx's
 * persist() sends the reverted state through the same real
 * `PUT /api/v1/reading-state/{profile_id}/{storybook_id}` any forward choice
 * uses. No route mocks, every /api call hits uvicorn through the preview
 * proxy, authorized as the seeded dev-child subject.
 *
 * #EDGE: data-integrity: "The Tide Pool Mystery" (s_tide_pools) is also read
 * by kid-reads.spec.ts, kid-flag-real.spec.ts, and kid-read-aloud-real.spec.ts.
 * Unlike "The Clockwork Garden" (exclusively owned by
 * offline-conflict-real.spec.ts, per that file's header), this story tolerates
 * shared reading_state across specs: kid-reads.spec.ts only asserts that SOME
 * ending is reached (any of the story's three endings, from any starting
 * node, since the graph is a forward DAG with no cycles back toward
 * n_start), and kid-flag-real.spec.ts never advances a choice. This spec
 * leaves the row at `n_pools` (mid-story, not an ending) when it finishes,
 * which both of those tolerate.
 * #VERIFY: if a future spec adds a strict starting-position assertion for
 * this story, give it its own seeded story instead of joining this one.
 */

const STORYBOOK_ID = 's_tide_pools'
const DEV_GUARDIAN_BEARER = 'dev-guardian'

interface ProfileRow {
  id: string
  display_name: string
}

interface ReadingStateRow {
  current_node: string
  path: string[]
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

async function findDevReaderProfileId(): Promise<string> {
  const res = await fetch(`${BACKEND}/api/v1/profiles`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    signal: AbortSignal.timeout(5000),
  })
  expect(res.ok, `GET /profiles failed (HTTP ${res.status})`).toBe(true)
  const { profiles } = (await res.json()) as { profiles: ProfileRow[] }
  const row = profiles.find((p) => p.display_name === 'Dev Reader')
  expect(row, 'no profile named "Dev Reader" found via GET /profiles').toBeTruthy()
  return (row as ProfileRow).id
}

let deviceGrant: DeviceGrant | null = null

test.beforeEach(async ({ context }) => {
  await requireBackend()
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test.afterEach(async () => {
  // Revoke the per-test grant so a reused dev stack does not accumulate one
  // live grant row per run; best-effort (see revokeDevice), never fails a test.
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('going back after two real choices reverts the current node and the persisted reading-state', async ({
  page,
}) => {
  // Registered before navigating so it reliably catches ReaderPage's
  // mount-time save (Reader's onProgress effect fires on the very first
  // render too, before any choice; see ReaderPage.tsx's persist() docstring),
  // not a later one triggered by a choice click below.
  const mountSave = waitForReadingStatePut(page)

  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()
  await mountSave

  // n_start -> n_pools. c_rock (one of n_pools's own choices) is a marker
  // unique to n_pools among this story's nodes, so its visibility is how
  // later assertions confirm which node is current without reading
  // server-only state.
  const firstSave = waitForReadingStatePut(page)
  await page.locator('[data-testid^="choice-"]').first().click()
  await firstSave
  await expect(page.getByTestId('choice-c_rock')).toBeVisible()

  // n_pools -> n_crab.
  const secondSave = waitForReadingStatePut(page)
  await page.getByTestId('choice-c_rock').click()
  await secondSave
  await expect(page.getByTestId('choice-c_cave')).toBeVisible()

  // Go back: n_crab -> n_pools. The wait is registered before the click so
  // the real PUT this triggers is caught as it happens, matching
  // naive-kid-misuse-real.spec.ts's wait-then-act ordering.
  const backSave = waitForReadingStatePut(page)
  await page.getByTestId('go-back').click()
  const backResponse = await backSave
  expect(backResponse.status()).toBe(200)
  const savedRow = (await backResponse.json()) as ReadingStateRow
  expect(savedRow.current_node).toBe('n_pools')
  expect(savedRow.path).toEqual(['n_start', 'n_pools'])

  // The reader itself shows n_pools again, not n_crab.
  await expect(page.getByTestId('choice-c_rock')).toBeVisible()
  await expect(page.getByTestId('choice-c_cave')).toHaveCount(0)

  // Cross-device confirmation, not just this same browser's IndexedDB cache:
  // a direct guardian-authorized GET of the real reading-state row (the same
  // endpoint ReaderPage's cold-cache resume calls) proves the server, not
  // only the client, holds the reverted node.
  // #ASSUME: security: authorize_profile (api/deps.py) admits a guardian
  // principal for any profile in their own family, so the seeded dev-guardian
  // bearer can read the Dev Reader profile's reading-state without minting a
  // child session token of its own.
  // #VERIFY: reading.py::get_reading_state's authorize_profile call; a 403
  // here would mean that assumption broke.
  const profileId = await findDevReaderProfileId()
  const serverRes = await fetch(`${BACKEND}/api/v1/reading-state/${profileId}/${STORYBOOK_ID}`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    signal: AbortSignal.timeout(5000),
  })
  expect(serverRes.ok, `GET /reading-state failed (HTTP ${serverRes.status})`).toBe(true)
  const serverRow = (await serverRes.json()) as ReadingStateRow
  expect(serverRow.current_node).toBe('n_pools')
  expect(serverRow.path).toEqual(['n_start', 'n_pools'])
})
