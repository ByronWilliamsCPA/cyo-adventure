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

// #ASSUME: timing-dependencies: matches on the outgoing PUT body's own
// current_node, not queue position. Reading-state saves are NOT concurrent:
// ReaderPage.tsx's persist() (lines 622-631) captures the previous save,
// advances saveChainRef synchronously, and awaits that previous save before
// issuing the network call, releasing the slot in a finally only after the
// call settles, so two PUTs are never simultaneously in flight. The real
// hazard is an off-by-one in response DELIVERY: an earlier save's response
// can still be undelivered when the next wait registers (see
// docs/testing/coverage-matrix.md's kid-go-back-real.spec.ts entry), and
// page.waitForResponse resolves on whichever matching response the browser
// delivers first, not the one issued by the action a caller just performed.
// An unqualified URL+method predicate therefore has no way to tell "the
// leftover n_crab response from the earlier click" apart from "the n_pools
// response the go-back click just triggered": both are PUTs to the same
// URL. Naming the expected node at each call site removes that ambiguity;
// see #290 for the nightly failures this produced (savedRow.current_node
// === 'n_crab' at what should have been the go-back's own n_pools save,
// while the server's actual persisted state was already correct).
// #VERIFY: if a future save shape ever leaves two undelivered responses that
// legitimately carry the same current_node (e.g. a client-side retry of an
// unresolved save), this predicate can no longer distinguish them; add a
// request-id or timestamp discriminator if that scenario ever arises.
//
// Diagnosability: on a timeout, the bare Playwright error names nothing.
// Track every reading-state PUT body observed for this story while waiting
// so a real regression reports what WAS sent instead of a bare "Timeout
// 10000ms exceeded".
function waitForReadingStatePut(page: Page, expectedNode: string) {
  const observedNodes: string[] = []
  return page
    .waitForResponse(
      (res) => {
        if (!res.url().includes('/api/v1/reading-state/')) return false
        if (!res.url().includes(STORYBOOK_ID)) return false
        if (res.request().method() !== 'PUT') return false
        let body: { current_node?: string } | null
        try {
          body = res.request().postDataJSON() as { current_node?: string } | null
        } catch {
          return false
        }
        if (body?.current_node) observedNodes.push(body.current_node)
        return body?.current_node === expectedNode
      },
      { timeout: 10_000 }
    )
    .catch((error: unknown) => {
      const seen =
        observedNodes.length > 0
          ? `nodes actually observed: ${JSON.stringify(observedNodes)}`
          : 'no reading-state PUT for this story observed at all'
      throw new Error(
        `no reading-state PUT carrying current_node ${JSON.stringify(expectedNode)} observed within 10s (${seen}): ${
          error instanceof Error ? error.message : String(error)
        }`
      )
    })
}

// Order-based counterpart to waitForReadingStatePut, for the one call site
// (the go-back save below) whose safety rests on two preconditions that must
// BOTH hold, not on the call site's position after an already-awaited prior
// save alone (that was also true of this same call site when #290's nightly
// failures happened; the premise never implied the conclusion by itself).
// (1) mountSave/firstSave/secondSave above are matched by BODY, so each
// await means that specific save's response landed, not merely that some
// response landed; by the time this wait registers there is no earlier
// undelivered response left for it to resolve on instead. (2) ReaderPage's
// saveChainRef serializes persist() calls (see waitForReadingStatePut's
// #ASSUME above), so no earlier save can still be in flight to race
// against. If either precondition regresses (in-flight/queue-based
// matching upstream, or saveChainRef chaining removed), this call site
// silently returns to identifying the go-back PUT by position, exactly the
// defect #290 fixed. Matching on order here and asserting the body's
// current_node separately keeps a real regression diagnosable: it fails on
// the assertion below, naming the node actually observed, instead of a bare
// "Timeout 10000ms exceeded while waiting for response" that names nothing.
function waitForNextReadingStatePut(page: Page) {
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

// Per-file reset (truncates reading_state) so the walk below always starts
// at n_start for s_tide_pools, regardless of what ran earlier in the same
// full-suite invocation and however that left the shared story's position.
test.beforeAll(() => {
  resetRealState()
})

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
  // not a later one triggered by a choice click below. The mount save drains
  // through the n_open prelude to n_start (PL-25's forced first-decision
  // depth), so that is the node this wait names.
  const mountSave = waitForReadingStatePut(page, 'n_start')

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
  const firstSave = waitForReadingStatePut(page, 'n_pools')
  await page.locator('[data-testid^="choice-"]').first().click()
  await firstSave
  await expect(page.getByTestId('choice-c_rock')).toBeVisible()

  // n_pools -> n_crab.
  const secondSave = waitForReadingStatePut(page, 'n_crab')
  await page.getByTestId('choice-c_rock').click()
  await secondSave
  await expect(page.getByTestId('choice-c_cave')).toBeVisible()

  // Go back: n_crab -> n_pools. secondSave was already awaited above, so no
  // earlier save can still be in flight here; an order-based wait is safe at
  // this specific call site (see waitForNextReadingStatePut's docstring) and
  // keeps a real regression diagnosable, since it fails on the node
  // assertion below (naming the node actually observed) instead of timing
  // out with no indication of what was sent. See #290.
  const backSave = waitForNextReadingStatePut(page)
  await page.getByTestId('go-back').click()
  const backResponse = await backSave
  expect(backResponse.status()).toBe(200)
  const savedRow = (await backResponse.json()) as ReadingStateRow
  expect(
    savedRow.current_node,
    `go-back click's PUT carried current_node ${JSON.stringify(savedRow.current_node)}, expected 'n_pools'`
  ).toBe('n_pools')
  // The recorded path starts at n_open, not n_start: PL-25 requires the first
  // decision to land at least two nodes in, so s_tide_pools opens on an
  // establishing prelude (n_open) whose single choice flows into n_start. This
  // assertion predates that prelude. Derive it from the story, never trim it to
  // match: a genuinely truncated path would then read as a pass.
  expect(savedRow.path).toEqual(['n_open', 'n_start', 'n_pools'])

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
  // The endpoint answers 200 with { state: ReadingStateRow | null }
  // (ReadingStateResultView); the go-back click above already saved a row,
  // so a null state here means that save did not land, not a legitimate
  // first-time-reader absence.
  const serverBody = (await serverRes.json()) as { state: ReadingStateRow | null }
  expect(serverBody.state, 'GET /reading-state returned null state after a save').not.toBeNull()
  const serverRow = serverBody.state as ReadingStateRow
  expect(serverRow.current_node).toBe('n_pools')
  // Same n_open prelude as the assertion above; see its comment.
  expect(serverRow.path).toEqual(['n_open', 'n_start', 'n_pools'])
})
