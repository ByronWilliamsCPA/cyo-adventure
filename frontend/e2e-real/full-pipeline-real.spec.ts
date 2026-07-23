import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, BACKEND, requireBackend, revokeDevice } from './real-stack'

import { seedGuardianSession } from '../e2e/support/auth'

/**
 * Phase 7.1 (G1, docs/planning/handoff-test-coverage-robustness-2026-07-22.md):
 * the full request -> generate -> gate -> moderate -> approve -> publish ->
 * read pipeline, driven through a REAL RQ worker rather than seeded data.
 * `scripts/seed_dev_data.py` only ever seeds already-published/already-in-review
 * stories; no other e2e-real spec makes the real generation worker do anything.
 * This spec is the one that does: it calls the guardian-only concept/generate
 * endpoints directly (there is no UI for the bare concept intake, only for the
 * story-request flow that wraps it), polls the real `generation_job` row until
 * the real worker (already running against Redis, per the task brief) drives
 * it to a terminal status, then drives the real admin approve UI and the real
 * kid reader against whatever the worker actually produced.
 *
 * The mock generation provider (generation/providers -- ENVIRONMENT=local)
 * ignores the submitted brief and always returns the same canned story titled
 * "The Forest Path" (generation/provider.py `_CANNED_STORY`), so every
 * assertion below is pinned to that title, not to the brief this spec sends.
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

let storybookId = ''

test.beforeEach(async () => {
  await requireBackend()
})

test('a guardian creates a concept and the real worker generates a story to in_review', async () => {
  // Raised from the file's default 30s: this test waits on a real worker
  // process across several real HTTP round trips, not just one poll.
  test.setTimeout(90_000)

  const conceptId = await createConcept()
  const jobId = await enqueueGeneration(conceptId)
  const result = await pollGenerationJob(jobId)

  expect(result.status, `generation job ${jobId} ended in an unexpected terminal status`).toBe(
    'passed'
  )
  expect(result.storybookId).toBe(`s_${jobId}`)
  storybookId = result.storybookId as string

  const queueRes = await apiFetch('/api/v1/review-queue', ADMIN_BEARER)
  expect(queueRes.ok, `GET /review-queue failed (HTTP ${queueRes.status})`).toBe(true)
  const queue = (await queueRes.json()) as {
    items: Array<{ storybook_id: string; title: string; status: string; screened: boolean }>
  }
  const item = queue.items.find((candidate) => candidate.storybook_id === storybookId)
  expect(item, `generated storybook ${storybookId} was not in the real review queue`).toBeTruthy()
  expect(item?.title).toBe(CANNED_TITLE)
  expect(item?.status).toBe('in_review')
  expect(item?.screened).toBe(true)

  const reviewRes = await apiFetch(`/api/v1/storybooks/${storybookId}/review`, ADMIN_BEARER)
  expect(
    reviewRes.ok,
    `GET /storybooks/${storybookId}/review failed (HTTP ${reviewRes.status})`
  ).toBe(true)
  const review = (await reviewRes.json()) as {
    status: string
    screened: boolean
    blob: { title?: string }
  }
  expect(review.status).toBe('in_review')
  expect(review.screened).toBe(true)
  expect(review.blob.title).toBe(CANNED_TITLE)
})

test('the admin approves and publishes the generated story through the real API', async ({
  page,
  context,
}) => {
  expect(storybookId, 'no storybook id carried over from the generation step').toBeTruthy()

  await seedGuardianSession(context, 'dev-admin')
  await page.goto(`/admin/review/${storybookId}`)
  await expect(page.getByRole('heading', { name: CANNED_TITLE })).toBeVisible()

  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/admin$/)

  // Persisted, not optimistic: read back the real row rather than trusting
  // the UI's own redirect.
  const reviewRes = await apiFetch(`/api/v1/storybooks/${storybookId}/review`, ADMIN_BEARER)
  expect(reviewRes.ok).toBe(true)
  const review = (await reviewRes.json()) as { status: string }
  expect(review.status).toBe('published')
})

let deviceGrant: DeviceGrant | null = null

test.afterEach(async () => {
  // Best-effort per-test cleanup (see revokeDevice); never fails the test.
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('the published story reaches the seeded child once assigned, and reads to an ending', async ({
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

  const assignRes = await apiFetch(
    `/api/v1/storybooks/${storybookId}/assignments`,
    GUARDIAN_BEARER,
    {
      method: 'POST',
      body: JSON.stringify({ profile_ids: [devReader?.id] }),
    }
  )
  expect(
    assignRes.ok,
    `assignment failed (HTTP ${assignRes.status}): ${await assignRes.text()}`
  ).toBe(true)

  // The kid surface is gated by DeviceAuthorizedRoute (ADR-014); mint and
  // inject a real grant before the child bearer, exactly like kid-reads.spec.ts.
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })

  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  await page.getByRole('link', { name: CANNED_TITLE }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  for (let i = 0; i < 40; i += 1) {
    if (await page.getByTestId('ending-screen').count()) break
    await page.locator('[data-testid^="choice-"]').first().click()
  }
  await expect(page.getByTestId('ending-screen')).toBeVisible()
})
