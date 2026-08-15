import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian concept-intake surface (C4a-5): unauthenticated-redirect smoke
 * plus the signed-in submit / no-PII / status-pill polling matrix.
 *
 * support/auth.ts seeds a GoTrue session directly into localStorage (the
 * pattern proven in assignments.spec.ts), so the signed-in surface below
 * mounts without driving the real login form. The fuller pill-mapping and
 * error-path matrix still lives in Vitest (src/guardian/IntakePage.test.tsx);
 * this spec covers what Vitest cannot: a real submit round trip through
 * mocked network routes and the live 8s poll transition.
 */

test('unauthenticated visit to intake redirects to guardian sign-in', async ({
  page,
}) => {
  await page.goto('/guardian/intake')
  await expect(page).toHaveURL(/\/guardian\/login$/)
  await expect(page.getByRole('heading', { name: 'Sign in or create your account' })).toBeVisible()
})

const PROFILE = {
  id: 'p1',
  display_name: 'Reader A',
  age_band: '8-11',
  reading_level_cap: 4,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-07-02T00:00:00Z',
}

test.describe('signed-in intake', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page)
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ json: { profiles: [PROFILE] } })
    )
  })

  test('submits a request without PII and shows Generating, then the poll transition', async ({
    page,
  }) => {
    let brief: Record<string, unknown> | null = null
    // jobs endpoint state machine: empty -> queued -> waiting for review ->
    // approved (published). Phase 3 exercises P-6a: an Approved row with no
    // assignments yet must offer "Assign to a child", not a presumptuous
    // "Assign more".
    let jobsPhase = 0
    const JOB = (status: string, storybookStatus: string | null) => ({
      id: 'j1',
      status,
      storybook_status: storybookStatus,
      storybook_id: storybookStatus ? 's-new' : null,
      version: storybookStatus ? 1 : null,
      error: null,
      title: 'A tide pool adventure',
      premise_snippet: 'tide pools',
      age_band: '8-11',
      created_at: '2026-07-04T00:00:00Z',
    })
    await page.route('**/api/v1/generation-jobs', (route) => {
      if (jobsPhase === 0) return route.fulfill({ json: { jobs: [] } })
      if (jobsPhase === 1) return route.fulfill({ json: { jobs: [JOB('queued', null)] } })
      if (jobsPhase === 2) return route.fulfill({ json: { jobs: [JOB('passed', 'in_review')] } })
      return route.fulfill({ json: { jobs: [JOB('passed', 'published')] } })
    })
    await page.route('**/api/v1/concepts', (route) => {
      brief = (route.request().postDataJSON() as { brief: Record<string, unknown> }).brief
      jobsPhase = 1
      return route.fulfill({ status: 201, json: { concept_id: 'c1' } })
    })
    await page.route('**/api/v1/concepts/c1/generate', (route) =>
      route.fulfill({ status: 202, json: { job_id: 'j1', status: 'queued' } })
    )
    // P-6a: AssignChildrenDialog's onAssigned tail calls this same GET on
    // open; here it only backs the Approved row's assign-button label.
    await page.route('**/api/v1/storybooks/s-new/assignments', (route) =>
      route.fulfill({ json: { storybook_id: 's-new', profile_ids: [] } })
    )

    await page.goto('/guardian/intake')
    await page.getByTestId('child-chip-p1').click()
    await page.getByLabel(/What's it about/).fill('tide pools and brave crabs')
    await page.getByRole('button', { name: 'Request Story' }).click()

    // The brief derives from the profile, never from the display name (no PII).
    await expect.poll(() => brief).not.toBeNull()
    expect(brief).toMatchObject({
      age_band: '8-11',
      tone: 'gentle',
      reading_level_target: 4,
      premise: 'tide pools and brave crabs',
    })
    expect(JSON.stringify(brief)).not.toContain('Reader A')

    await expect(page.getByTestId('request-status-j1')).toHaveText('Generating')

    // Next poll (POLL_MS = 8000 in IntakePage.tsx) flips the pill. 12s leaves
    // the poll interval a full render's worth of slack on a loaded CI runner.
    jobsPhase = 2
    await expect(page.getByTestId('request-status-j1')).toHaveText('Waiting for review', {
      timeout: 12_000,
    })

    // Approval (publishing) happens out-of-band (an admin acts on the review
    // queue), so the job's own status stays 'passed' and the live poll never
    // observes it (isActive gates polling on status queued/running); the
    // guardian sees it on the next full load instead. Simulate that with a
    // reload rather than a further live poll tick. The Approved row must
    // offer "Assign to a child" (P-6a), not "Assign more", since nothing has
    // been assigned to it yet.
    jobsPhase = 3
    await page.reload()
    await expect(page.getByTestId('request-status-j1')).toHaveText('Approved')
    await expect(page.getByRole('button', { name: 'Assign to a child' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Assign more' })).toHaveCount(0)
  })
})
