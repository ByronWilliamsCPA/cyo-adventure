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
 * Real-backend CONTRACT-SMOKE (Phase 7.2, G2,
 * docs/planning/handoff-test-coverage-robustness-2026-07-22.md).
 *
 * The mocked tier (frontend/e2e/) fakes every API response with hand-written
 * `page.route` fulfilments that have no structural link to the real backend.
 * If a backend response shape changes, those fixtures keep passing while the
 * app silently breaks in production (the exact failure class behind the
 * prior P0-1 offline-resync 422: `toPutPayload()` sent a field the real
 * `ReadingStateBody` no longer accepted, and every mocked test stayed green).
 *
 * This file hits the real, unmocked backend for the four highest-drift
 * surfaces the mocked fixtures assume, and asserts only the fields the
 * frontend actually reads off each response (named per-assertion below), not
 * the whole body. A drift in any of these fields fails HERE instead of
 * silently diverging from the mocked tier's stale assumptions.
 *
 * Bearers mirror scripts/seed_dev_data.py's authn subjects; in
 * ENVIRONMENT=local the backend trusts the bearer string directly as the
 * principal (see real-stack.ts).
 */

const CHILD_BEARER = 'dev-child' // scripts/seed_dev_data.py _CHILD_SUBJECT
const GUARDIAN_BEARER = 'dev-guardian' // scripts/seed_dev_data.py _GUARDIAN_SUBJECT
const ADMIN_BEARER = 'dev-admin' // scripts/seed_dev_data.py _ADMIN_SUBJECT

// scripts/seed_dev_data.py `_REVIEW_STORY` ("08_tier2_bridge_builder.json"):
// in_review, flagged, first node "n_riverbank". reset_e2e_real_state.py
// reverts this story to in_review before every real-backend run, and
// approval-flow.spec.ts's approve() never clears its moderation_report, so
// the /review detail assertions below hold regardless of run order.
const REVIEW_STORY_ID = 's_bridge_builder'
const REVIEW_STORY_FIRST_NODE = 'n_riverbank'

async function apiGet(bearer: string, path: string) {
  return fetch(`${BACKEND}${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
    signal: AbortSignal.timeout(5000),
  })
}

async function apiPost(bearer: string, path: string, body: unknown) {
  return fetch(`${BACKEND}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  })
}

async function devReaderProfileId(bearer: string): Promise<string> {
  const res = await apiGet(bearer, '/api/v1/profiles')
  expect(res.ok, `GET /api/v1/profiles failed (HTTP ${res.status})`).toBe(true)
  const body = (await res.json()) as { profiles: { id: string; display_name: string }[] }
  const devReader = body.profiles.find((profile) => profile.display_name === 'Dev Reader')
  expect(devReader, 'seeded "Dev Reader" profile not found via GET /api/v1/profiles').toBeDefined()
  return devReader!.id
}

// Per-file reset so this file's review-queue/review-detail assertions hold
// regardless of what ran earlier in the same full-suite invocation (e.g.
// approval-flow.spec.ts already having approved s_bridge_builder).
test.beforeAll(() => {
  resetRealState()
})

test.beforeEach(async () => {
  await requireBackend()
})

test('GET /api/v1/library pins the LibraryItem contract BookCard/LibraryPage read', async () => {
  const profileId = await devReaderProfileId(CHILD_BEARER)

  const res = await apiGet(CHILD_BEARER, `/api/v1/library?profile_id=${profileId}`)
  expect(res.ok, `GET /api/v1/library failed (HTTP ${res.status})`).toBe(true)
  const body = (await res.json()) as { stories: Record<string, unknown>[] }
  expect(body.stories.length, 'seeded library is unexpectedly empty').toBeGreaterThan(0)

  for (const item of body.stories) {
    // BookCard.tsx: id (read-link href + React key), version (read-link href).
    expect(typeof item.id).toBe('string')
    expect(typeof item.version).toBe('number')
    // BookCard.tsx: title (heading text + letter-avatar fallback alt).
    expect(typeof item.title).toBe('string')
    // BookCard.tsx: cover_url (image src, null renders the letter fallback).
    expect(item.cover_url === null || typeof item.cover_url === 'string').toBe(true)
    // BookCard.tsx: rating (StarRating value).
    expect(item.rating === null || typeof item.rating === 'number').toBe(true)
    // BookCard.tsx: series_id !== null gates the "Ask for next book" button.
    expect(item.series_id === null || typeof item.series_id === 'string').toBe(true)
    // bookCardUtils.ts percentComplete(): node_count is the progress divisor.
    expect(typeof item.node_count).toBe('number')
    if (item.progress !== null) {
      const progress = item.progress as Record<string, unknown>
      // bookCardUtils.ts percentComplete(): nodes_visited is the numerator.
      expect(typeof progress.nodes_visited).toBe('number')
      // BookCard.tsx: progress.completed selects the "Read again" label.
      expect(typeof progress.completed).toBe('boolean')
      expect(typeof progress.current_node).toBe('string')
      expect(typeof progress.updated_at).toBe('string')
    }
  }
})

test.describe('reading-state PUT contract', () => {
  let deviceGrant: DeviceGrant | null = null

  test.beforeEach(async ({ context }) => {
    deviceGrant = await authorizeDevice(context)
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
  })

  test.afterEach(async () => {
    if (deviceGrant) {
      await revokeDevice(deviceGrant)
      deviceGrant = null
    }
  })

  function waitForReadingStatePut(page: Page) {
    return page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/reading-state/') &&
        res.request().method() === 'PUT' &&
        res.status() === 200,
      { timeout: 10_000 }
    )
  }

  function assertReadingStateShape(row: Record<string, unknown>): void {
    // player/types.ts ReadingState is exactly what offline/sync.ts's
    // saveProgress() returns as SaveResult.row and readerApi.ts's
    // makeSyncApi() maps res.data onto; these are the fields the client
    // reads off a successful PUT to update local state and the next save's
    // base state_revision/version.
    expect(typeof row.current_node).toBe('string')
    expect(typeof row.version).toBe('number')
    expect(typeof row.state_revision).toBe('number')
    expect(Array.isArray(row.path)).toBe(true)
    expect(Array.isArray(row.visit_set)).toBe(true)
    expect(row.var_state).not.toBeNull()
    expect(typeof row.var_state).toBe('object')
    expect(row.save_slots).not.toBeNull()
    expect(typeof row.save_slots).toBe('object')
  }

  test('PUT /api/v1/reading-state/{profile}/{story} pins the ReadingState contract offline/sync.ts reads', async ({
    page,
  }) => {
    // "The Tide Pool Mystery" (s_tide_pools) is also read by kid-reads.spec.ts;
    // that spec does not assert exact revision numbers, so sharing it is safe
    // as long as THIS spec asserts revisions relatively (below) rather than
    // pinning an absolute starting value that a prior run in the same
    // invocation could have already advanced past.
    const firstSave = waitForReadingStatePut(page)
    await page.goto('/kids')
    await page.getByText('Dev Reader').click()
    await expect(page).toHaveURL(/\/library\//)
    await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
    await expect(page).toHaveURL(/\/read\//)
    await expect(page.getByTestId('reader')).toBeVisible()

    const firstRes = await firstSave
    const firstBody = (await firstRes.json()) as Record<string, unknown>
    assertReadingStateShape(firstBody)
    expect(firstBody.state_revision as number).toBeGreaterThanOrEqual(1)

    const secondSave = waitForReadingStatePut(page)
    await page.locator('[data-testid^="choice-"]').first().click()
    const secondRes = await secondSave
    const secondBody = (await secondRes.json()) as Record<string, unknown>
    assertReadingStateShape(secondBody)
    // #ASSUME: data-integrity: the second save strictly advances the revision
    // the mount-time save established; this holds regardless of the absolute
    // starting value, so it is safe even if a future spec reads this same
    // seeded story earlier in a full-suite invocation.
    // #VERIFY: this is exactly the invariant offline/sync.ts's
    // toPutPayload()/resolveConflict() rely on for optimistic concurrency.
    expect(secondBody.state_revision as number).toBeGreaterThan(firstBody.state_revision as number)
  })
})

test('POST /api/v1/story-requests + GET /api/v1/story-requests pin the contract StoryRequestQueue reads', async () => {
  const profileId = await devReaderProfileId(GUARDIAN_BEARER)
  const requestText = 'A story about a friendly dragon who bakes bread for the village'

  const createRes = await apiPost(GUARDIAN_BEARER, '/api/v1/story-requests', {
    profile_id: profileId,
    request_text: requestText,
  })
  expect(createRes.status, `POST /api/v1/story-requests failed (HTTP ${createRes.status})`).toBe(
    201
  )
  const created = (await createRes.json()) as { id: string; status: string }
  // IntakePage / RequestStory success handling: id (tracking) and status
  // (STATUS_COPY lookup) are the entire StoryRequestCreatedView contract.
  expect(typeof created.id).toBe('string')
  // #ASSUME: data-integrity: the seeded "Dev Reader" profile has no
  // request_auto_approve pre-authorization (scripts/seed_dev_data.py never
  // sets it), so a benign, unflagged request rests "pending" rather than
  // ADR-015 G3 auto-approving; if that seed default ever changes, this
  // request would resolve "approved" and the next assertion (finding this
  // row in the pending queue) would need to follow suit.
  // #VERIFY: scripts/seed_dev_data.py's ChildProfile creation for "Dev
  // Reader" carries no request_auto_approve=True.
  expect(created.status).toBe('pending')

  const queueRes = await apiGet(GUARDIAN_BEARER, '/api/v1/story-requests?status=pending')
  expect(queueRes.ok, `GET /api/v1/story-requests failed (HTTP ${queueRes.status})`).toBe(true)
  const queue = (await queueRes.json()) as { requests: Record<string, unknown>[] }
  const row = queue.requests.find((r) => r.id === created.id)
  expect(row, `submitted request ${created.id} not found in the pending queue`).toBeDefined()
  const view = row!

  // StoryRequestQueue.tsx reads: request_text, created_at, moderation_flags,
  // age_band, proposed_series_title, anchor_storybook_id, status, id.
  expect(view.profile_id).toBe(profileId)
  expect(view.status).toBe('pending')
  expect(view.request_text).toBe(requestText)
  expect(Array.isArray(view.moderation_flags)).toBe(true)
  expect(typeof view.created_at).toBe('string')
  // api/story_requests.py::create_story_request hard-codes initiator_role to
  // "child" server-side for this endpoint regardless of the caller's actual
  // role (even a guardian-submitted request lands "child"); StoryRequestView
  // still carries the field, so pin it to the value the backend truly sets.
  expect(view.initiator_role).toBe('child')
  expect(typeof view.age_band).toBe('string')
  expect(view.series_id).toBeNull()
  expect(view.proposed_series_title).toBeNull()
  expect(view.anchor_storybook_id).toBeNull()
})

test('GET /api/v1/review-queue + GET /api/v1/storybooks/{id}/review pin the contract the admin console reads', async () => {
  const queueRes = await apiGet(ADMIN_BEARER, '/api/v1/review-queue')
  expect(queueRes.ok, `GET /api/v1/review-queue failed (HTTP ${queueRes.status})`).toBe(true)
  const queue = (await queueRes.json()) as { items: Record<string, unknown>[] }
  // #EDGE: data-integrity: review-queue only lists in_review stories.
  // scripts/reset_e2e_real_state.py reverts s_bridge_builder to in_review
  // before every real-backend project run, so this is non-empty when this
  // spec runs standalone (the validated configuration). A future full-suite
  // nightly invocation that runs approval-flow.spec.ts (which approves this
  // story for real) before this file would need a second in-review fixture
  // to keep this assertion meaningful.
  // #VERIFY: revisit if this file is folded into a fixed nightly ordering.
  expect(queue.items.length, 'admin review queue is unexpectedly empty').toBeGreaterThan(0)
  for (const item of queue.items) {
    // AdminConsolePage.tsx reads: storybook_id (review-detail link), title
    // (link text), screened + flagged_count (bucketing/badge text),
    // summary?.hard_block (badge severity).
    expect(typeof item.storybook_id).toBe('string')
    expect(typeof item.title).toBe('string')
    expect(typeof item.status).toBe('string')
    expect(typeof item.version).toBe('number')
    expect(typeof item.screened).toBe('boolean')
    expect(typeof item.flagged_count).toBe('number')
    if (item.summary !== null) {
      const summary = item.summary as Record<string, unknown>
      expect(typeof summary.hard_block).toBe('boolean')
      expect(typeof summary.soft_flag).toBe('boolean')
      expect(typeof summary.repaired).toBe('boolean')
      expect(typeof summary.reviewer_independent).toBe('boolean')
    }
  }

  const detailRes = await apiGet(ADMIN_BEARER, `/api/v1/storybooks/${REVIEW_STORY_ID}/review`)
  expect(detailRes.ok, `GET .../review failed (HTTP ${detailRes.status})`).toBe(true)
  const surface = (await detailRes.json()) as Record<string, unknown>

  // ReviewDetailPage.tsx reads: storybook_id, version, status (gates the
  // Approve/Send-back buttons' disabled state), screened (banner), summary
  // (badges: count/hard_block/soft_flag/repaired/reviewer_independent),
  // flagged_passages (per-node findings), story_level_findings.
  expect(surface.storybook_id).toBe(REVIEW_STORY_ID)
  expect(typeof surface.version).toBe('number')
  expect(typeof surface.status).toBe('string')
  // scripts/seed_dev_data.py stamps a moderation_report on this story at seed
  // time; approve() (publishing/service.py) never clears moderation_report,
  // so `screened` holds true regardless of this story's current approval
  // status in a given run.
  expect(surface.screened).toBe(true)

  const summary = surface.summary as Record<string, unknown>
  // scripts/seed_dev_data.py's _flagged_moderation_report(): exactly one
  // soft-flag finding, not a hard block, not reviewer-independent-repaired.
  expect(summary.count).toBe(1)
  expect(summary.hard_block).toBe(false)
  expect(summary.soft_flag).toBe(true)
  expect(summary.repaired).toBe(false)
  expect(summary.reviewer_independent).toBe(true)

  const flaggedPassages = surface.flagged_passages as Record<string, unknown>[]
  expect(flaggedPassages.length).toBeGreaterThan(0)
  const passage = flaggedPassages.find((p) => p.node_id === REVIEW_STORY_FIRST_NODE)
  expect(passage, `no flagged passage for seeded node ${REVIEW_STORY_FIRST_NODE}`).toBeDefined()
  expect(typeof passage!.prose).toBe('string')
  const findings = passage!.findings as Record<string, unknown>[]
  expect(findings.length).toBeGreaterThan(0)
  // scripts/seed_dev_data.py's _flagged_moderation_report(): a single
  // llm_safety/safety/flag finding with a fixed message and score.
  expect(findings[0].source).toBe('llm_safety')
  expect(findings[0].category).toBe('safety')
  expect(findings[0].verdict).toBe('flag')
  expect(typeof findings[0].message).toBe('string')

  expect(Array.isArray(surface.story_level_findings)).toBe(true)
})
