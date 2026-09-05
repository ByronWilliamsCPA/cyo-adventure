import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, BACKEND, requireBackend, revokeDevice } from './real-stack'

/**
 * Phase 7.1 (G1, docs/planning/handoff-test-coverage-robustness-2026-07-22.md):
 * the full request -> generate -> gate -> moderate pipeline, driven through a
 * REAL RQ worker rather than seeded data, and then the ADR-005 containment
 * that follows from what the real moderation stage decides about the result.
 * `scripts/seed_dev_data.py` only ever seeds already-published/already-in-review
 * stories; this spec and its two siblings in the `real-backend-pipeline`
 * projects are the ones that make the real generation worker do anything. It
 * calls the guardian-only concept/generate endpoints directly (there is no UI
 * for the bare concept intake, only for the story-request flow that wraps it),
 * polls the real `generation_job` row until the real worker (already running
 * against Redis, per the task brief) drives it to a terminal status, then reads
 * back what the worker and the moderation pipeline actually persisted.
 *
 * The mock generation provider (generation/providers -- ENVIRONMENT=local)
 * ignores the submitted brief and always returns the same canned story titled
 * "The Forest Path" (generation/provider.py `_CANNED_STORY`), so every title
 * assertion below is pinned to that title, not to the brief this spec sends.
 *
 * WHAT THE REAL STACK DECIDES ABOUT A MOCK-MODERATED BOOK (issue #290 root
 * cause, re-pinned 2026-09-05). The nightly stack runs with the default
 * `review_provider="mock"` (core/config.py), and the mock review backend
 * answers every call with the literal "{}" (moderation/review_provider.py::
 * build_review_provider). Stage 1 records every node as an unparseable
 * fail-safe FLAG with `concern="reviewer_unavailable"` (moderation/stages.py),
 * which `ModerationReport.has_coverage_gap` reads as "no reviewer saw these
 * nodes"; `blocks_release` is therefore true and run_moderation_pipeline calls
 * `auto_reject`, not `submit` (moderation/pipeline.py, PR #776 "stop an
 * unreviewed story passing as soft-flagged"). Independently, PR #769 stamps
 * every mock-reviewed report `reviewer_independent: false` in EVERY
 * environment, which `moderation_report_unusable` treats as unapprovable with
 * no override path (publishing/service.py::_assert_report_permits_approval).
 * Both are deliberate: a book nobody reviewed must never reach a child. So a
 * worker-generated book on this stack lands, deterministically, in
 * `needs_revision` with a stored (unusable) report, is absent from the
 * in_review-only admin queue, cannot be approved, and cannot be assigned.
 *
 * This file used to assert the pre-#769/#776 world (in_review -> approve ->
 * publish -> kid reads) and failed on every nightly since those PRs landed,
 * first at the queue lookup ("was not in the real review queue"). The approve
 * -> publish -> kid-read legs are still proven end to end against the real
 * stack, on the seeded review story whose report carries a genuinely
 * independent reviewer, by approval-flow.spec.ts and kid-reads.spec.ts in the
 * `real-backend` project. What THIS file now proves is the other half of the
 * crown-jewel property: the real worker produces a real book, the real
 * moderation stage holds it back, and every downstream surface honours that
 * hold. Driving a worker-generated book all the way to a child again needs a
 * real (non-mock) reviewer in the nightly, which is a secrets/cost decision
 * recorded in the unscheduled work register, not something a spec can
 * paper over.
 *
 * Serial: each test depends on real database state a prior test in this file
 * produced (the concept/job/storybook ids are generated fresh per run, so
 * they cannot be hardcoded like the seeded `s_bridge_builder` other real
 * specs use).
 */

test.describe.configure({ mode: 'serial' })

// Seeded subjects from scripts/seed_dev_data.py; ENVIRONMENT=local trusts the
// bearer string itself as the authn subject (mirrors real-stack.ts's
// SEEDED_GUARDIAN_BEARER, kept as a local literal here since that constant is
// not exported and every other e2e-real spec also inlines these subjects).
const GUARDIAN_BEARER = 'dev-guardian'
const ADMIN_BEARER = 'dev-admin'

// The mock provider ignores every field here except shape/validity; the title
// in particular is never used (the canned story is always "The Forest Path").
// Copied from tests/integration/test_generation_api.py `_BRIEF_PAYLOAD`.
const CONCEPT_BRIEF = {
  title: 'E2E full-pipeline probe (ignored by the mock provider)',
  premise: 'A young hero ventures into a mysterious cave to rescue a lost pet.',
  protagonist: { name: 'Captain Rosa', age: 10, role: 'young explorer' },
  point_of_view: 'second',
  age_band: '8-11',
  reading_level_target: 4.0,
  tier: 1,
  tone: 'adventurous',
  themes_allowed: ['friendship', 'bravery'],
  content_nogo: [],
  target_node_count: 5,
  ending_count: 2,
  structure_pattern: 'branch_and_bottleneck',
  desired_variables: [],
  special_constraints: [],
}

const CANNED_TITLE = 'The Forest Path'

// A published seeded book the kid library always shows (scripts/seed_dev_data.py,
// also the book kid-reads.spec.ts opens). Used only as a "the shelf has
// finished loading" marker before asserting the held-back book is absent.
const SEEDED_PUBLISHED_TITLE = 'The Tide Pool Mystery'

// #CRITICAL: timing dependencies: the mock provider still runs the full
// staged pipeline (validator gate, moderation) through a real RQ worker
// process, so a passing run still takes a few real seconds; 30s comfortably
// covers that while staying well under this file's per-test timeout (raised
// below via test.setTimeout for the driving test only).
// #VERIFY: pollGenerationJob fails with an actionable message (naming the
// worker, not a bare Playwright timeout) when the deadline is hit while the
// job is still queued/running, per the task brief's "do not try to restart
// it, report it" instruction.
const POLL_DEADLINE_MS = 30_000
const POLL_INTERVAL_MS = 1_000

async function apiFetch(path: string, bearer: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${BACKEND}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
    signal: AbortSignal.timeout(10_000),
  })
}

async function createConcept(): Promise<string> {
  const res = await apiFetch('/api/v1/concepts', GUARDIAN_BEARER, {
    method: 'POST',
    body: JSON.stringify({ brief: CONCEPT_BRIEF }),
  })
  // #ASSUME: data-integrity: a Response body stream can only be consumed
  // once. `res.text()` must not run as part of an `expect` message unless
  // the request actually failed: an eagerly-evaluated template literal reads
  // it on the success path too, so the `res.json()` call below would then
  // throw "Body is unusable: Body has already been read" on every passing
  // run. Check `res.ok` first and only drain the body for the error path.
  // #VERIFY: this test's own first run caught the regression this guards
  // against; a passing run now depends on `res.json()` succeeding below.
  if (!res.ok) {
    throw new Error(`POST /concepts failed (HTTP ${res.status}): ${await res.text()}`)
  }
  const body = (await res.json()) as { concept_id: string }
  return body.concept_id
}

/**
 * Enqueue generation for a concept, retrying once on a 409.
 *
 * #ASSUME: concurrency: MAX_ACTIVE_JOBS_PER_FAMILY (api/generation.py) is a
 * per-family throttle of 2 active (queued/running) jobs; `authored-request.spec.ts`
 * enqueues real generation for this same seeded family when the full
 * `real-backend` suite runs, so a job it started moments earlier can still be
 * "active" when this spec's enqueue call lands. The mock pipeline resolves a
 * job in a few seconds, so a short backoff clears the cap without masking a
 * genuine regression: a 409 on every attempt still fails the test below.
 * #VERIFY: the final attempt's response is asserted `ok`, so a real cap
 * regression (or a persistently over-quota family) still fails this spec.
 */
async function enqueueGeneration(conceptId: string): Promise<string> {
  const maxAttempts = 4
  let lastStatus = 0
  let lastBody = ''
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const res = await apiFetch(`/api/v1/concepts/${conceptId}/generate`, GUARDIAN_BEARER, {
      method: 'POST',
    })
    if (res.ok) {
      const body = (await res.json()) as { job_id: string }
      return body.job_id
    }
    lastStatus = res.status
    lastBody = await res.text()
    if (res.status === 409 && attempt < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, 3_000))
      continue
    }
    break
  }
  throw new Error(`POST /concepts/${conceptId}/generate failed (HTTP ${lastStatus}): ${lastBody}`)
}

interface JobPollResult {
  status: string
  storybookId: string | null
}

async function pollGenerationJob(jobId: string): Promise<JobPollResult> {
  const deadline = Date.now() + POLL_DEADLINE_MS
  let last: JobPollResult = { status: 'queued', storybookId: null }
  while (Date.now() < deadline) {
    const res = await apiFetch(`/api/v1/generation-jobs/${jobId}`, GUARDIAN_BEARER)
    expect(res.ok, `GET /generation-jobs/${jobId} failed (HTTP ${res.status})`).toBe(true)
    const body = (await res.json()) as { status: string; storybook_id: string | null }
    last = { status: body.status, storybookId: body.storybook_id }
    if (last.status !== 'queued' && last.status !== 'running') {
      return last
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }
  throw new Error(
    `Generation job ${jobId} is still "${last.status}" after ${POLL_DEADLINE_MS}ms. ` +
      'The real RQ generation worker does not appear to be consuming the ' +
      '"generation" queue (it should already be running per the task brief; ' +
      'do not start a fresh one from this spec, report this as the real blocker).'
  )
}

interface ReviewSurface {
  status: string
  screened: boolean
  report_unusable: boolean
  blob: { title?: string }
  summary: { reviewer_independent: boolean; hard_block: boolean } | null
}

let storybookId = ''

test.beforeEach(async () => {
  await requireBackend()
})

test('a guardian creates a concept and the real worker generates a story the real moderation stage holds back', async () => {
  // Raised from the file's default 30s: this test waits on a real worker
  // process across several real HTTP round trips, not just one poll.
  test.setTimeout(90_000)

  const conceptId = await createConcept()
  const jobId = await enqueueGeneration(conceptId)
  const result = await pollGenerationJob(jobId)

  // The GATE passed: the canned story is structurally clean, so the job is
  // "passed" and a real Storybook row was persisted under the worker's
  // per-job id (generation/worker.py::_persist_and_moderate).
  expect(result.status, `generation job ${jobId} ended in an unexpected terminal status`).toBe(
    'passed'
  )
  expect(result.storybookId).toBe(`s_${jobId}`)
  storybookId = result.storybookId as string

  // The MODERATION stage then ran on that row and, with the mock reviewer,
  // auto-rejected it (see the header). Read the persisted state back through
  // the admin review surface, which serves any lifecycle status.
  const reviewRes = await apiFetch(`/api/v1/storybooks/${storybookId}/review`, ADMIN_BEARER)
  expect(
    reviewRes.ok,
    `GET /storybooks/${storybookId}/review failed (HTTP ${reviewRes.status})`
  ).toBe(true)
  const review = (await reviewRes.json()) as ReviewSurface
  expect(review.blob.title).toBe(CANNED_TITLE)
  // `screened` is "a moderation report exists": the pipeline ran and stored
  // its verdict, it did not skip the book.
  expect(review.screened).toBe(true)
  expect(
    review.status,
    'a mock-moderated book must be auto-rejected to needs_revision, never submitted to in_review ' +
      '(moderation/pipeline.py routes on blocks_release; a "{}" mock review is a coverage gap)'
  ).toBe('needs_revision')
  // The stored report is self-identifying as mock-moderated (PR #769): that
  // is the arm moderation_report_unusable trips on, and what makes the book
  // permanently unapprovable below.
  expect(review.summary?.reviewer_independent).toBe(false)
  expect(review.report_unusable).toBe(true)

  // The admin review queue lists in_review only, so the held-back book must
  // not be offered for approval there...
  const queueRes = await apiFetch('/api/v1/review-queue', ADMIN_BEARER)
  expect(queueRes.ok, `GET /review-queue failed (HTTP ${queueRes.status})`).toBe(true)
  const queue = (await queueRes.json()) as { items: Array<{ storybook_id: string }> }
  expect(
    queue.items.find((candidate) => candidate.storybook_id === storybookId),
    `auto-rejected storybook ${storybookId} must NOT appear in the in_review-only review queue`
  ).toBeUndefined()

  // ...but it is not lost either: the admin master library lists every
  // lifecycle status, so an operator can still find and re-open it.
  const libraryRes = await apiFetch('/api/v1/admin/storybooks?status=needs_revision', ADMIN_BEARER)
  expect(libraryRes.ok, `GET /admin/storybooks failed (HTTP ${libraryRes.status})`).toBe(true)
  const library = (await libraryRes.json()) as {
    items: Array<{ storybook_id: string; title: string; status: string }>
  }
  const shelved = library.items.find((candidate) => candidate.storybook_id === storybookId)
  expect(shelved, `storybook ${storybookId} missing from the admin library`).toBeTruthy()
  expect(shelved?.title).toBe(CANNED_TITLE)
  expect(shelved?.status).toBe('needs_revision')
})

test('the held-back story cannot be approved through the real API', async () => {
  expect(storybookId, 'no storybook id carried over from the generation step').toBeTruthy()

  // Two independent gates refuse this, and the state machine is the first one
  // reached: approve is legal only from in_review (publishing/state_machine.py),
  // and a needs_revision book 409s with StateTransitionError. Even a book that
  // somehow reached in_review with this report would then be refused by
  // _assert_report_permits_approval (unusable report, no override path).
  const approveRes = await apiFetch(`/api/v1/storybooks/${storybookId}/approve`, ADMIN_BEARER, {
    method: 'POST',
    body: JSON.stringify({ visibility: 'family' }),
  })
  expect(approveRes.status, 'approve must be refused for a needs_revision book').toBe(409)

  // Persisted, not inferred from the refusal: the row is still needs_revision
  // and still has no published version.
  const reviewRes = await apiFetch(`/api/v1/storybooks/${storybookId}/review`, ADMIN_BEARER)
  expect(reviewRes.ok).toBe(true)
  const review = (await reviewRes.json()) as { status: string }
  expect(review.status).toBe('needs_revision')
})

let deviceGrant: DeviceGrant | null = null

test.afterEach(async () => {
  // Best-effort per-test cleanup (see revokeDevice); never fails the test.
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('the held-back story never reaches the seeded child: assignment is refused and the shelf omits it', async ({
  page,
  context,
}) => {
  expect(storybookId, 'no storybook id carried over from the generation step').toBeTruthy()

  const profilesRes = await apiFetch('/api/v1/profiles', GUARDIAN_BEARER)
  expect(profilesRes.ok, `GET /profiles failed (HTTP ${profilesRes.status})`).toBe(true)
  const profiles = (await profilesRes.json()) as {
    profiles: Array<{ id: string; display_name: string }>
  }
  const devReader = profiles.profiles.find((profile) => profile.display_name === 'Dev Reader')
  expect(devReader, 'seeded "Dev Reader" child profile not found').toBeTruthy()

  // ADR-005: only a published book can be assigned (api/assignments.py raises
  // BusinessLogicError -> 400 for anything else). A guardian cannot route an
  // unreviewed book onto a child's shelf by assigning it directly.
  const assignRes = await apiFetch(
    `/api/v1/storybooks/${storybookId}/assignments`,
    GUARDIAN_BEARER,
    {
      method: 'POST',
      body: JSON.stringify({ profile_ids: [devReader?.id] }),
    }
  )
  expect(
    assignRes.status,
    'assigning a needs_revision book must be refused (only published books are assignable)'
  ).toBe(400)

  // The real kid shelf, through the real UI: the seeded published book is
  // there (proves the shelf loaded), the held-back one is not. The kid surface
  // is gated by DeviceAuthorizedRoute (ADR-014); mint and inject a real grant
  // before the child bearer, exactly like kid-reads.spec.ts.
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })

  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)
  await expect(page.getByRole('link', { name: SEEDED_PUBLISHED_TITLE })).toBeVisible()
  await expect(page.getByRole('link', { name: CANNED_TITLE })).toHaveCount(0)
})
