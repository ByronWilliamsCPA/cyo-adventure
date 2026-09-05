import { expect, test } from '@playwright/test'

import { BACKEND, requireBackend } from './real-stack'

/**
 * S-5 negative path (review finding S-5): the full request -> generate -> gate
 * pipeline driven to a HARD-BLOCK through a REAL RQ worker, proving the
 * deterministic validator gate BLOCKS (not just passes). The sibling
 * `full-pipeline-real.spec.ts` proves the gate PASSING via the gate-clean
 * canned story ("The Forest Path"); this spec proves the gate BLOCKING via the
 * structurally invalid fixture, so the crown-jewel pipeline is exercised in
 * both directions.
 *
 * REQUIRES a backend launched with ALL of:
 *   - ENVIRONMENT=local                       (mock provider allowed at all)
 *   - CYO_ADVENTURE_GENERATION_PROVIDER=mock  (the default in local)
 *   - CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid
 *
 * The last var (added for S-5, see core/config.py::Settings.mock_story_fixture)
 * flips build_provider's mock branch to serve the structurally broken
 * `_INVALID_STORY` fixture (generation/provider.py): a non-ending node with no
 * choices, which the validator gate (validator/) flags as an ERROR-severity
 * topology violation on every repair attempt. It defaults to "safe" (the
 * canned "The Forest Path" story), so running this spec against a default
 * backend would see a PASSING run and fail at the block assertion below.
 *
 * HOW IT IS WIRED (issue #290 remediation, 2026-09-05): `mock_story_fixture`
 * is a per-worker-process setting, and the positive specs need the default
 * `safe` fixture from the same "generation" queue, so one worker cannot serve
 * both directions. For 37 consecutive nightlies this spec ran under the
 * positive tier's safe-fixture worker and failed with "expected a HARD-BLOCK
 * terminal status, got passed", which was the wiring rather than the gate. It
 * therefore has its own Playwright project, `real-backend-pipeline-negative`
 * (npm run test:e2e:real:pipeline:negative), which
 * .github/workflows/e2e-real-nightly.yml runs only after stopping the safe
 * worker (and asserting none survives) and starting a second worker with
 * CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid. Locally: start the worker with
 * that variable exported, then run the npm script above. It reuses the exact
 * helper shapes proven by full-pipeline-real.spec.ts.
 *
 * Serial: the concept/job ids are generated fresh per run and cannot be
 * hardcoded, so the steps thread state through a module-scoped variable.
 */

test.describe.configure({ mode: 'serial' })

// ENVIRONMENT=local trusts the bearer string itself as the authn subject
// (mirrors full-pipeline-real.spec.ts); seeded by scripts/seed_dev_data.py.
const GUARDIAN_BEARER = 'dev-guardian'
const ADMIN_BEARER = 'dev-admin'

// The mock provider ignores every field except shape/validity; with
// MOCK_STORY_FIXTURE=invalid the served story is the broken fixture regardless
// of this brief. Shape copied from full-pipeline-real.spec.ts `CONCEPT_BRIEF`.
const CONCEPT_BRIEF = {
  title: 'E2E negative-path probe (ignored by the mock provider)',
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

// #CRITICAL: timing dependencies: a BLOCKING run still runs the full staged
// pipeline (validator gate, up to 3 repairs) through a real RQ worker, so it
// takes a few real seconds; 30s covers that while staying under the per-test
// timeout raised below.
// #VERIFY: pollGenerationJob throws an actionable, worker-naming message (not a
// bare timeout) if the deadline is hit while still queued/running.
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
  // Drain the body only on the error path: a Response stream is single-use, so
  // an eager template literal would break the `res.json()` success path below
  // (see full-pipeline-real.spec.ts::createConcept for the regression note).
  if (!res.ok) {
    throw new Error(`POST /concepts failed (HTTP ${res.status}): ${await res.text()}`)
  }
  const body = (await res.json()) as { concept_id: string }
  return body.concept_id
}

/**
 * Enqueue generation for a concept, retrying once on a 409 (per-family active
 * job cap), exactly like full-pipeline-real.spec.ts::enqueueGeneration.
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

let blockedJobId = ''

test.beforeEach(async () => {
  await requireBackend()
})

test('the real worker HARD-BLOCKS the invalid fixture to a non-publishable outcome', async () => {
  // Raised from the file default: this waits on a real worker across several
  // real HTTP round trips, not just one poll.
  test.setTimeout(90_000)

  const conceptId = await createConcept()
  const jobId = await enqueueGeneration(conceptId)
  blockedJobId = jobId
  const result = await pollGenerationJob(jobId)

  // The gate BLOCKS: the terminal status is a review/failure outcome, never
  // "passed". If this backend was launched without MOCK_STORY_FIXTURE=invalid,
  // the gate-clean canned story passes instead and this assertion fails,
  // surfacing the missing env var rather than silently passing.
  expect(
    ['needs_review', 'failed'],
    `expected a HARD-BLOCK terminal status, got "${result.status}" ` +
      '(is the backend running with CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid?)'
  ).toContain(result.status)

  // No Storybook is persisted for a blocked run, so nothing can ever be
  // approved, published, or assigned to a child.
  expect(result.storybookId, 'a blocked story must not persist a Storybook').toBeNull()
})

test('the blocked story never reaches the admin review queue', async () => {
  expect(blockedJobId, 'no job id carried over from the block step').toBeTruthy()

  // A blocked run creates no Storybook, so the review queue the admin approves
  // from must not contain a row for this job. The generated-storybook id would
  // have been `s_${jobId}` on a passing run (see full-pipeline-real.spec.ts);
  // assert that id is absent, proving the story never entered the approval
  // surface and can never be published to a child library.
  const wouldBeStorybookId = `s_${blockedJobId}`
  const queueRes = await apiFetch('/api/v1/review-queue', ADMIN_BEARER)
  expect(queueRes.ok, `GET /review-queue failed (HTTP ${queueRes.status})`).toBe(true)
  const queue = (await queueRes.json()) as {
    items: Array<{ storybook_id: string }>
  }
  const leaked = queue.items.find((candidate) => candidate.storybook_id === wouldBeStorybookId)
  expect(leaked, `blocked story ${wouldBeStorybookId} must NOT be in the review queue`).toBeFalsy()
})
