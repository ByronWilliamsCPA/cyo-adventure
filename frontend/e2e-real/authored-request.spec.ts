import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { BACKEND, requireBackend } from './real-stack'

// ENVIRONMENT=local trusts the bearer string itself as the authn subject
// (api/deps.py::_resolve_subject); 'dev-guardian' is the seeded Dev Family
// guardian (scripts/seed_dev_data.py). Inlined as a local literal exactly
// like full-pipeline-real.spec.ts, since real-stack.ts does not export it.
const GUARDIAN_BEARER = 'dev-guardian'

/**
 * Authenticated backend fetch, mirroring full-pipeline-real.spec.ts's helper
 * (that constant is spec-local there too). Body-stream discipline: the caller
 * must only ``await res.text()`` on the failure branch, never eagerly in an
 * ``expect`` message, or a later ``res.json()`` throws "Body has already been
 * read".
 */
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

interface StoryRequestRow {
  id: string
  status: string
  request_text: string | null
  initiator_role: string
  age_band: string
  length: string | null
  series_id: string | null
}

/**
 * Read the guardian's family-scoped story-request list (GET
 * /api/v1/story-requests is family-scoped for every caller, api/story_requests.py)
 * and return the row whose brief text exactly matches, or ``undefined``. The
 * ``?status=approved`` filter keeps a blocked sibling (whose request_text is
 * redacted to null) out of the way; the exact request_text match is the row key.
 */
async function findApprovedRequest(requestText: string): Promise<StoryRequestRow | undefined> {
  const res = await apiFetch('/api/v1/story-requests?status=approved', GUARDIAN_BEARER)
  expect(res.ok, `GET /story-requests failed (HTTP ${res.status})`).toBe(true)
  const body = (await res.json()) as { requests: StoryRequestRow[] }
  return body.requests.find((row) => row.request_text === requestText)
}

/**
 * Real-API authored story request (WS-B PR2): a guardian submits the
 * pre-approved "Request a story" form on RequestsPage
 * (src/guardian/RequestStoryForm.tsx, mode="guardian") with no route mocks;
 * the POST to /api/v1/story-requests/authored hits uvicorn through the
 * preview proxy, authorized as the seeded dev-guardian subject
 * (ENVIRONMENT=local trusts the bearer token, mirroring approval-flow.spec.ts).
 *
 * Kept minimal per the task brief: no child is selected (the seeded
 * dev-guardian's children are not guaranteed to exist or match a specific
 * band), so the request rides the guardian's own family with an
 * explicitly-chosen age band and length. This only asserts the success
 * notice; it does not invent new real-stack seeding helpers.
 */

test.beforeEach(async ({ context }) => {
  await requireBackend()
  await seedGuardianSession(context, 'dev-guardian')
})

test('a guardian submits an authored request and sees the success notice', async ({ page }) => {
  await page.goto('/guardian/requests')

  await page.getByLabel('What should the story be about?').fill('A story about a lighthouse keeper')
  await page.getByLabel('Age band').selectOption('8-11')
  await page.getByLabel('Story length').selectOption('short')
  await page.getByRole('button', { name: 'Send request' }).click()

  await expect(page.getByText('Request approved and sent for authoring.')).toBeVisible()

  // Downstream materialization (S-6): the success toast alone would pass even
  // against a backend that 201s and does nothing. Read the request back through
  // the real family-scoped GET and assert it actually persisted as an approved
  // story-request row with the fields the form sent. The authored path builds a
  // Concept and stamps the row `approved` (story_requests/service.py); it does
  // NOT enqueue a generation job (that is the later admin authoring-plan step),
  // so the approved story-request row -- not a generation job -- is the correct
  // proof of materialization here.
  const materialized = await findApprovedRequest('A story about a lighthouse keeper')
  expect(
    materialized,
    'authored "lighthouse keeper" request did not materialize as an approved story-request row'
  ).toBeTruthy()
  expect(materialized?.status).toBe('approved')
  expect(materialized?.initiator_role).toBe('guardian')
  expect(materialized?.age_band).toBe('8-11')
  expect(materialized?.length).toBe('short')
})

// WS-B PR 3: same authored-request path, with the optional series title
// filled in before sending, proving the field reaches the real backend.
test('a guardian submits an authored request with a series title and sees the success notice', async ({
  page,
}) => {
  await page.goto('/guardian/requests')

  await page
    .getByLabel('What should the story be about?')
    .fill('A story about a lighthouse keeper who charts the coastline')
  await page.getByLabel('Age band').selectOption('8-11')
  await page.getByLabel('Story length').selectOption('short')
  await page.getByLabel('Series title (optional)').fill('Lighthouse Keeper Tales')
  await page.getByRole('button', { name: 'Send request' }).click()

  await expect(page.getByText('Request approved and sent for authoring.')).toBeVisible()

  // Downstream materialization (S-6): prove the request persisted AND that the
  // optional series title actually reached the backend, not just that the toast
  // rendered. On the guardian authored path the series title is materialized as
  // a real Series (api/story_requests.py create_authored_story_request calls
  // service.create_series and stores its id as the request's series_id); it is
  // NOT left as the pending-ratification proposed_series_title. So a non-null
  // series_id on the row is the proof the title reached the backend. This brief
  // text is distinct from the first test's, so the exact request_text match
  // uniquely identifies this run's row.
  const materialized = await findApprovedRequest(
    'A story about a lighthouse keeper who charts the coastline'
  )
  expect(
    materialized,
    'authored series request did not materialize as an approved story-request row'
  ).toBeTruthy()
  expect(materialized?.status).toBe('approved')
  expect(
    materialized?.series_id,
    'series title did not materialize as a linked Series on the request row'
  ).toBeTruthy()
})
