import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from '../support/auth'

/**
 * Naive admin misuse. The spec's third scenario, "attempt approve as a
 * guardian session," is intentionally NOT repeated here: it is a pure
 * duplicate of guardian-review.spec.ts's existing
 * 'guardian approve gets 403 and the UI fails closed' case; adding an
 * identical test under a different filename would violate DRY without
 * adding coverage.
 */

test('a generation job is locatable from the console by content, without its job id', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/generation-jobs', (route) =>
    route.fulfill({
      json: {
        jobs: [
          {
            id: 'j-forgotten',
            status: 'running',
            title: 'A tide pool adventure',
            premise_snippet: 'tide pools',
          },
        ],
      },
    })
  )

  // The admin never learns the job id; they navigate cold to the admin console.
  await page.goto('/admin')
  await expect(page.getByRole('heading', { level: 2 })).toContainText('Still processing')
  await expect(page.getByText('A tide pool adventure')).toBeVisible()
})

const REVIEW_SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
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
}

test('two admin sessions approving the same storybook concurrently both reach the network with no client-side guard blocking either', async ({
  browser,
}) => {
  // This test verifies FRONTEND behavior only: the UI has no cross-session
  // guard that locks or disables the Approve action based on another
  // session's in-flight or completed approval, so both sessions' clicks
  // reach the network layer unblocked. The `/storybooks/s1/approve` route
  // below is a mock that unconditionally returns 200 for every request, so
  // `approveCount === 2` shows only that the frontend issued two requests,
  // not that the backend safely handled two concurrent approvals.
  //
  // It does NOT characterize or regression-test the real server-side gap
  // tracked in issue #129 (approve_storybook in approval.py uses a plain
  // session.get, no SELECT FOR UPDATE and no version check). Because the
  // route here is mocked to always return 200, fixing #129 in approval.py
  // would never make this test start failing: a mocked test cannot serve as
  // a regression sentinel for server-side concurrency behavior, the same
  // reason the real cross-family-authorization check lives in
  // frontend/e2e-real/ instead of this mocked tier. Real backend
  // concurrency coverage for #129 belongs there, not here.
  let approveCount = 0

  const contextA = await browser.newContext()
  const contextB = await browser.newContext()
  await seedGuardianSession(contextA)
  await seedGuardianSession(contextB)
  const pageA = await contextA.newPage()
  const pageB = await contextB.newPage()

  for (const page of [pageA, pageB]) {
    await mockMe(page, { role: 'admin' })
    await mockEmptyConsole(page)
    await page.route('**/api/v1/storybooks/s1/review*', (route) =>
      route.fulfill({ json: REVIEW_SURFACE })
    )
    await page.route('**/api/v1/storybooks/s1/approve', (route) => {
      approveCount += 1
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
  }

  await pageA.goto('/admin/review/s1')
  await pageB.goto('/admin/review/s1')

  await Promise.all(
    [pageA, pageB].map(async (page) => {
      await page.getByRole('button', { name: /^Approve$/ }).click()
      await page.getByRole('button', { name: 'Confirm approve' }).click()
    })
  )

  await expect(pageA).toHaveURL(/\/admin$/)
  await expect(pageB).toHaveURL(/\/admin$/)
  expect(approveCount).toBe(2) // both requests reached the mock: no client-side guard blocked either

  await contextA.close()
  await contextB.close()
})
