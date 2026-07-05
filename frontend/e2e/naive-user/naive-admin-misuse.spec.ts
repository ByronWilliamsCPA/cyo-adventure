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

  // The admin never learns the job id; they navigate cold to the console.
  await page.goto('/guardian')
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

test('two admin sessions approving the same storybook concurrently both succeed silently (known gap, no server-side lock)', async ({
  browser,
}) => {
  // Characterizes CURRENT behavior, confirmed by reading approval.py and
  // publishing/service.py during planning: approve_storybook loads the row
  // with a plain session.get, no SELECT FOR UPDATE and no version check, so
  // two concurrent admin approvals both silently succeed (last write wins on
  // approved_by / published_at). This is the OPPOSITE of the guarded request-
  // approve path in naive-guardian-misuse.spec.ts. Not a bug in this test:
  // it locks in today's actual behavior so a future fix (the same
  // for_update pattern story_requests.py already uses) has a test to flip
  // from "both succeed" to "second one 409s". The fix itself is out of
  // scope here; Task 11 files the tracking issue.
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

  await pageA.goto('/guardian/review/s1')
  await pageB.goto('/guardian/review/s1')

  await Promise.all(
    [pageA, pageB].map(async (page) => {
      await page.getByRole('button', { name: /^Approve$/ }).click()
      await page.getByRole('button', { name: 'Confirm approve' }).click()
    })
  )

  await expect(pageA).toHaveURL(/\/guardian$/)
  await expect(pageB).toHaveURL(/\/guardian$/)
  expect(approveCount).toBe(2) // both succeeded: today's undesired gap

  await contextA.close()
  await contextB.close()
})
