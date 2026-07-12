import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from '../support/auth'

/**
 * Cross-role misuse: double-click protection on the three non-kid submit
 * actions (approve, assign, generate), a genuine browser-back-then-resubmit
 * attempt, a hand-typed URL into a status an action no longer supports, and
 * session expiry mid-task. The kid-surface double-submit case (Request-a-
 * story's Send button) lives in naive-kid-misuse.spec.ts and is not repeated
 * here.
 */

test('double-clicking Approve on a guardian request only approves once', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)

  let requests = [
    {
      id: 'req-1',
      profile_id: 'p1',
      status: 'pending',
      request_text: 'A story about a friendly dragon',
      moderation_flags: [],
      created_at: '2026-07-04T10:00:00Z',
      initiator_role: 'child',
      age_band: '5-8',
      length: null,
      narrative_style: 'prose',
    },
  ]
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests } })
  )
  let approveCalls = 0
  // A deterministic gate (released only after the forced second click) keeps
  // the row mounted long enough for that click to land (in-flight, disabled)
  // rather than racing an instant-resolving mock: the row unmounts entirely
  // once approve resolves, and a fully-detached locator would otherwise make
  // the second click hang for the full test timeout instead of exercising the
  // guard. Replaces a raw 300ms sleep, which could still race a slow CI runner.
  // Mirrors the same pattern in naive-kid-misuse.spec.ts's Send button test.
  let releaseApprove: () => void = () => {}
  const approveGate = new Promise<void>((resolve) => {
    releaseApprove = resolve
  })
  await page.route('**/api/v1/story-requests/req-1/approve', async (route) => {
    approveCalls += 1
    requests = requests.filter((r) => r.id !== 'req-1')
    await approveGate
    return route.fulfill({
      json: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
  })

  await page.goto('/guardian/requests')
  const requestRow = page.getByTestId('request-req-1')
  await requestRow.getByLabel('Story length').selectOption('medium')
  const approveButton = requestRow.getByRole('button', { name: 'Approve' })
  await approveButton.click()
  // Locator-based wait: the in-flight guard disables the button synchronously,
  // so this is the deterministic signal that the forced second click lands
  // mid-flight (a disabled button never dispatches a click, even forced).
  await expect(approveButton).toBeDisabled()
  await approveButton.click({ force: true })
  releaseApprove()

  await expect(page.getByText('No requests to review')).toBeVisible()
  expect(approveCalls).toBe(1)
})

test('double-clicking Assign in the guardian books dialog only posts once', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { subject: 'guardian-a', family_id: 'fam-a', profile_ids: ['p1', 'p2'] })
  await page.route('**/api/v1/guardian/books', (route) =>
    route.fulfill({
      json: {
        books: [
          {
            storybook_id: 'story-1',
            title: 'The Brave Little Fox',
            version: 1,
            age_band: '10-13',
            screened: true,
            flagged_count: 0,
            assigned_profile_ids: ['p1'],
          },
        ],
      },
    })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({
      json: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '10-13',
            reading_level_cap: 99,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
          {
            id: 'p2',
            display_name: 'Reader A2',
            age_band: '8-11',
            reading_level_cap: 99,
            avatar: 'owl',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
  )
  await page.route('**/api/v1/storybooks/story-1/content-summary', (route) =>
    route.fulfill({
      json: {
        storybook_id: 'story-1',
        version: 1,
        screened: true,
        summary: null,
        flagged_count: 0,
        findings: [],
      },
    })
  )
  let assignCalls = 0
  // Deterministic gate (released only after the forced second click) so the
  // dialog survives long enough for that click to land (in-flight, on a
  // disabled button) rather than racing an instant-resolving mock: the dialog
  // unmounts entirely once the assign resolves, and a fully-detached locator
  // would otherwise make the second click hang for the full test timeout
  // instead of exercising the guard. Replaces a raw 300ms sleep. Mirrors the
  // Approve and intake double-click tests in this file.
  let releaseAssign: () => void = () => {}
  const assignGate = new Promise<void>((resolve) => {
    releaseAssign = resolve
  })
  await page.route('**/api/v1/storybooks/story-1/assignments', async (route) => {
    if (route.request().method() === 'POST') {
      assignCalls += 1
      await assignGate
      return route.fulfill({ json: { storybook_id: 'story-1', profile_ids: ['p1', 'p2'] } })
    }
    return route.fulfill({ json: { storybook_id: 'story-1', profile_ids: ['p1'] } })
  })

  await page.goto('/guardian/books')
  await page.getByRole('button', { name: /^Assign The Brave Little Fox$/ }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox', { name: /Reader A2/ }).click()
  const assignButton = dialog.getByRole('button', { name: /^Assign$/ })
  await assignButton.click()
  // Locator-based wait: the saving flag disables the button synchronously, so
  // this is the deterministic signal that the forced second click lands mid-flight.
  await expect(assignButton).toBeDisabled()
  await assignButton.click({ force: true })
  releaseAssign()

  // Wait for the terminal success state (the dialog closes once the assign
  // resolves) before asserting the call count. expect.poll(...).toBe(1) would
  // pass the instant assignCalls first reaches 1, before a regression's later
  // second POST could arrive; anchoring on the dialog close and then asserting
  // strictly means a removed double-submit guard is actually observed.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(assignCalls).toBe(1)
})

test('double-clicking Request Story in intake only creates one generation job', async ({
  page,
  context,
}) => {
  // TRIAGE NOTE (verified): IntakePage.tsx does have a submit guard, mirroring
  // RequestStory.tsx's confirmed pattern. `canSubmit` (line 103) includes
  // `!saving`, and the submit Button's `disabled={!canSubmit}` (line 218)
  // disables the button as soon as submit() synchronously sets `saving=true`
  // (line 107, before any await), so a forced second click lands on a
  // disabled button and never re-enters submit(). This test passes on
  // confirmed real behavior, not a weakened assertion.
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({
      json: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '8-11',
            reading_level_cap: 4,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
  )
  // Mutable so the post-submit refreshJobs() call (IntakePage.tsx submit(),
  // called after the durable POSTs succeed) can actually surface the new job;
  // a route that always returns an empty list would leave request-status-j1
  // unrenderable regardless of the double-submit guard under test.
  let jobs: Array<Record<string, unknown>> = []
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs } }))
  let conceptCalls = 0
  // Deterministic gate instead of a raw 300ms sleep: hold the concept POST
  // open until the forced second click has landed on the disabled button, so
  // the in-flight window is guaranteed rather than timing-dependent.
  let releaseConcept: () => void = () => {}
  const conceptGate = new Promise<void>((resolve) => {
    releaseConcept = resolve
  })
  await page.route('**/api/v1/concepts', async (route) => {
    conceptCalls += 1
    await conceptGate
    return route.fulfill({ status: 201, json: { concept_id: 'c1' } })
  })
  await page.route('**/api/v1/concepts/c1/generate', (route) => {
    jobs = [
      {
        id: 'j1',
        status: 'queued',
        storybook_id: null,
        storybook_status: null,
        error: null,
        title: null,
        premise_snippet: 'tide pools and brave crabs',
        age_band: '8-11',
        created_at: '2026-07-05T00:00:00Z',
      },
    ]
    return route.fulfill({ status: 202, json: { job_id: 'j1', status: 'queued' } })
  })

  await page.goto('/guardian/intake')
  await page.getByTestId('child-chip-p1').click()
  await page.getByLabel(/What's it about/).fill('tide pools and brave crabs')
  const submitButton = page.getByRole('button', { name: 'Request Story' })
  await submitButton.click()
  // Locator-based wait: submit() sets `saving` synchronously before any await,
  // and the label flips to "Requesting…" while canSubmit disables the button;
  // waiting on the label change is the deterministic in-flight signal.
  await expect(page.getByRole('button', { name: 'Requesting…' })).toBeDisabled()
  await page.getByRole('button', { name: 'Requesting…' }).click({ force: true })
  releaseConcept()

  await expect(page.getByTestId('request-status-j1')).toHaveText('Generating')
  expect(conceptCalls).toBe(1)
})

test('browser back after a successful approve disables the Approve affordance (#130 closed)', async ({
  page,
  context,
}) => {
  // #130 closed: ReviewDetailPage.tsx now gates the action bar on
  // surface.status, so after the story is published the remounted review detail
  // still keeps the "Approve" button (its accessible name is unchanged) but
  // renders it disabled. This test pins that: the naive browser-back move lands
  // on a review URL whose Approve control is present-but-disabled rather than
  // clickable, and no second approve reaches the network.
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  let approved = false
  await page.route('**/api/v1/review-queue', (route) =>
    route.fulfill({
      json: {
        items: approved
          ? []
          : [
              {
                storybook_id: 's1',
                title: 'The Cave',
                status: 'in_review',
                version: 1,
                screened: true,
                flagged_count: 0,
                summary: {
                  count: 0,
                  hard_block: false,
                  soft_flag: false,
                  repaired: false,
                  reviewer_independent: false,
                },
              },
            ],
      },
    })
  )
  await page.route('**/api/v1/storybooks/s1/review*', (route) =>
    // no-store so the post-goBack remount refetches the CURRENT (published)
    // surface instead of the browser replaying the first in_review GET from its
    // HTTP cache; without it the status gate would read stale in_review state.
    route.fulfill({
      headers: { 'cache-control': 'no-store' },
      json: {
        storybook_id: 's1',
        version: 1,
        status: approved ? 'published' : 'in_review',
        screened: true,
        summary: {
          count: 0,
          hard_block: false,
          soft_flag: false,
          repaired: false,
          reviewer_independent: false,
        },
        blob: { title: 'The Cave', nodes: [{ id: 'n1', body: 'A dark cave yawned ahead.' }] },
        flagged_passages: [],
        story_level_findings: [],
      },
    })
  )
  let approveCalls = 0
  await page.route('**/api/v1/storybooks/s1/approve', (route) => {
    approveCalls += 1
    approved = true
    return route.fulfill({
      json: {
        id: 's1',
        status: 'published',
        current_published_version: 1,
        approved_by: 'admin-user-id',
        published_at: '2026-07-05T00:00:00Z',
      },
    })
  })

  await page.goto('/guardian/review/s1')
  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/guardian$/)

  // The naive move: hit back expecting to redo the approval. A bfcache restore
  // can hand back the pre-approval snapshot (stale in_review state, no refetch),
  // so reload once to force the review detail to re-read current server truth,
  // which is what the naive user's next interaction would trigger anyway.
  await page.goBack()
  await expect(page).toHaveURL(/\/guardian\/review\/s1$/)
  await page.reload()
  // Wait for the remount's data fetch to actually resolve before checking for
  // Approve; without this, the assertion below races ReviewDetailPage's own
  // `loading` state and can pass for the wrong reason (caught before the
  // fetch settles).
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  // #130 closed: the Approve button is still present (name unchanged) but the
  // status gate now disables it for the already-published story.
  await expect(page.getByRole('button', { name: /^Approve$/ })).toBeDisabled()
  expect(approveCalls).toBe(1)
})

test('a hand-typed review URL for an already-published storybook disables Approve (#130 closed)', async ({
  page,
  context,
}) => {
  // #130 closed (shared with the browser-back test above): ReviewDetailPage.tsx
  // now gates the action bar on `surface.status`, so a hand-typed review URL for
  // a published (no longer in_review) story keeps the "Approve" button but renders
  // it disabled rather than clickable.
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  await page.route('**/api/v1/storybooks/s1/review*', (route) =>
    route.fulfill({
      json: {
        storybook_id: 's1',
        version: 1,
        status: 'published',
        screened: true,
        summary: {
          count: 0,
          hard_block: false,
          soft_flag: false,
          repaired: false,
          reviewer_independent: false,
        },
        blob: { title: 'The Cave', nodes: [{ id: 'n1', body: 'A dark cave yawned ahead.' }] },
        flagged_passages: [],
        story_level_findings: [],
      },
    })
  )

  await page.goto('/guardian/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Approve$/ })).toBeDisabled()
})

test('an expired session mid-intake redirects to sign-in rather than hanging silently', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({
      json: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '8-11',
            reading_level_cap: 4,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
  )
  // IntakePage.tsx's initial loadData() fetches profiles and jobs via
  // Promise.all; without this mock the unmocked jobs request rejects the
  // whole load and the child chip never renders, failing before the intended
  // 401-mid-submit scenario is even reached.
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  // Simulate a token that expired between page load and submit.
  await page.route('**/api/v1/concepts', (route) =>
    route.fulfill({ status: 401, json: { detail: 'token expired' } })
  )
  // A fully expired session: the refresh token is dead too. useApi's 401 path
  // (P6-06) tries ONE supabase.auth.refreshSession() before tearing the
  // session down; mock that token endpoint to fail (invalid_grant) so the
  // refresh resolves as "no recovery" immediately instead of hanging against
  // the dummy Supabase URL until the client-side refresh deadline elapses.
  // This is the branch where a redirect to sign-in is the correct terminal
  // state; the recoverable-refresh case is covered in useApi.test.ts.
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({
      status: 400,
      json: { code: 400, error_code: 'invalid_grant', msg: 'Invalid Refresh Token' },
    })
  )

  await page.goto('/guardian/intake')
  await page.getByTestId('child-chip-p1').click()
  await page.getByLabel(/What's it about/).fill('tide pools and brave crabs')
  await page.getByRole('button', { name: 'Request Story' }).click()

  // useApi.ts's response interceptor closes the gap this test characterizes:
  // on a 401 from a `/guardian/*` surface it first attempts a single silent
  // refresh-and-retry (P6-06), and when that refresh cannot recover the
  // session it clears `auth_token` AND redirects to the guardian login (via
  // window.location.replace, so the expired URL does not linger in history).
  // So a fully expired session mid-intake lands the naive user on sign-in
  // instead of a retryable inline error that would fail identically on every
  // retry.
  await expect(page).toHaveURL(/\/guardian\/login$/)
})
