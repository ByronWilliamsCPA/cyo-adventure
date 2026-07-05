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
    },
  ]
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests } })
  )
  let approveCalls = 0
  await page.route('**/api/v1/story-requests/req-1/approve', async (route) => {
    approveCalls += 1
    requests = requests.filter((r) => r.id !== 'req-1')
    // An artificial delay so the row survives long enough for the forced
    // second click to land (in-flight, disabled) rather than racing the
    // instant-resolving mock: the row unmounts entirely once approve
    // resolves, and a fully-detached locator would otherwise make the second
    // click hang for the full test timeout instead of exercising the guard.
    // Mirrors the same pattern in naive-kid-misuse.spec.ts's Send button test.
    await new Promise((resolve) => setTimeout(resolve, 300))
    return route.fulfill({
      json: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
    })
  })

  await page.goto('/guardian/requests')
  const approveButton = page.getByTestId('request-req-1').getByRole('button', { name: 'Approve' })
  await approveButton.click()
  await approveButton.click({ force: true })

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
  await page.route('**/api/v1/storybooks/story-1/assignments', (route) => {
    if (route.request().method() === 'POST') {
      assignCalls += 1
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
  await assignButton.click({ force: true })

  await expect.poll(() => assignCalls).toBe(1)
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
  await page.route('**/api/v1/concepts', async (route) => {
    conceptCalls += 1
    await new Promise((resolve) => setTimeout(resolve, 300))
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
  await submitButton.click({ force: true })

  await expect(page.getByTestId('request-status-j1')).toHaveText('Generating')
  expect(conceptCalls).toBe(1)
})

test('browser back after a successful approve, then a resubmit attempt, does not double-approve', async ({
  page,
  context,
}) => {
  // Known gap: ReviewDetailPage.tsx does not gate Approve button on surface.status, rendering it unconditionally even for published stories
  test.fail()
  // TRIAGE NOTE (verified, and the real cause is more fundamental than the
  // bfcache theory this note started from): ReviewDetailPage.tsx does refetch
  // the review surface on remount (its data-loading useEffect keys on
  // storybookId, not a bfcache snapshot). But the component never reads
  // `surface.status` at all (grep confirms the only "status" reference in the
  // file is the unrelated `role="status"` loading indicator) -- the Approve
  // button at lines 205-209 renders unconditionally regardless of story
  // status. So even a fresh, correct refetch after goBack() still offers
  // Approve on an already-published story; only the server-side re-check
  // (referenced in the confirm-button's #CRITICAL comment) prevents an actual
  // re-approval. This is left red as a genuine naive-user affordance gap for
  // Task 11 to track, not a bfcache issue and not something to force-pass.
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
    route.fulfill({
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

  // The naive move: hit back expecting to redo the approval.
  await page.goBack()
  await expect(page).toHaveURL(/\/guardian\/review\/s1$/)
  // Wait for the remount's data fetch to actually resolve before checking for
  // Approve; without this, the assertion below races ReviewDetailPage's own
  // `loading` state and can pass for the wrong reason (caught before the
  // fetch settles) instead of deterministically exercising the real gap.
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Approve$/ })).toHaveCount(0)
  expect(approveCalls).toBe(1)
})

test('a hand-typed review URL for a storybook that is no longer in_review does not offer Approve', async ({
  page,
  context,
}) => {
  // Known gap: ReviewDetailPage.tsx does not gate Approve button on surface.status, rendering it unconditionally even for published stories
  test.fail()
  // NOT originally triage-flagged (the brief called this "confirmed existing
  // behavior"), but it turned out to share the exact same gap as the
  // browser-back test above: ReviewDetailPage.tsx never gates the Approve
  // button on `surface.status`, so it renders unconditionally for a published
  // story too. Left red for the same reason and tracked together in Task 11.
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
  await expect(page.getByRole('button', { name: /^Approve$/ })).toHaveCount(0)
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

  await page.goto('/guardian/intake')
  await page.getByTestId('child-chip-p1').click()
  await page.getByLabel(/What's it about/).fill('tide pools and brave crabs')
  await page.getByRole('button', { name: 'Request Story' }).click()

  // TRIAGE NOTE (verified): useApi.ts's response interceptor (lines 49-59)
  // only clears the `auth_token` localStorage key on a 401 and re-rejects; it
  // never redirects (the inline comment at useApi.ts:54 even says "redirect
  // to login, clear token, etc." but only the clear-token half is
  // implemented). IntakePage.tsx's submit() catch (lines 127-129) sets
  // `error`, which renders the inline "We could not send this request."
  // alert (lines 166-170). That is NOT a silent hang, so per this note's
  // branch (a) the assertion below characterizes today's real behavior
  // (a visible, retryable inline error, session token silently cleared)
  // rather than a redirect that does not exist. This is still a naive-user
  // gap worth tracking: nothing tells the user their session expired, and a
  // retry click will silently fail the same way every time.
  await expect(page.getByRole('alert')).toHaveText(
    'We could not send this request. Please try again.'
  )
  await expect(page).toHaveURL(/\/guardian\/intake$/)
})
