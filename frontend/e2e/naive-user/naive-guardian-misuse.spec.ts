import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from '../support/auth'

/**
 * Naive guardian misuse: concurrent approval races and zero-profile empty
 * states. Targets POST /story-requests/{id}/approve specifically (guarded
 * server-side by a SELECT ... FOR UPDATE row lock in
 * story_requests.py::_load_scoped_request), not the ADR-005 storybook
 * approve in approval.py (see naive-admin-misuse.spec.ts for that gap).
 */

test('two guardian sessions approving the same request: the second gets 409, not a silent double-approve', async ({
  browser,
}) => {
  let approved = false
  let secondCallStatus: number | null = null

  const contextA = await browser.newContext()
  const contextB = await browser.newContext()
  try {
    await seedGuardianSession(contextA)
    await seedGuardianSession(contextB)
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()

    for (const page of [pageA, pageB]) {
      await mockMe(page)
      await page.route('**/api/v1/story-requests?status=pending', (route) =>
        route.fulfill({
          json: {
            requests: [
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
            ],
          },
        })
      )
      await page.route('**/api/v1/story-requests/req-1/approve', (route) => {
        if (approved) {
          secondCallStatus = 409
          return route.fulfill({
            status: 409,
            json: { detail: "story request 'req-1' is not pending" },
          })
        }
        approved = true
        return route.fulfill({
          json: { id: 'req-1', status: 'approved', concept_id: 'concept-1', job_id: 'job-1' },
        })
      })
    }

    await pageA.goto('/guardian/requests')
    await pageB.goto('/guardian/requests')

    await pageA.getByTestId('request-req-1').getByLabel('Story length').selectOption('medium')
    await pageB.getByTestId('request-req-1').getByLabel('Story length').selectOption('medium')

    await Promise.all([
      pageA.getByTestId('request-req-1').getByRole('button', { name: 'Approve' }).click(),
      pageB.getByTestId('request-req-1').getByRole('button', { name: 'Approve' }).click(),
    ])

    // The second approve hits the mock's 409 branch...
    await expect.poll(() => secondCallStatus).toBe(409)

    // ...and, crucially, that 409 must SURFACE to the losing guardian rather
    // than be silently swallowed (the failure mode this test is named for). On
    // a failed approve, RequestsPage keeps the row and renders a visible per-row
    // alert (runRowAction's catch sets rowErrors -> "Could not update the
    // request. Try again."). The winner/loser split between the two pages is
    // racy, so assert the alert appears on whichever page received the 409; a
    // regression that discards the 409 without a notice drops the count to 0 and
    // turns this red.
    const rowError = (page: (typeof pageA)) =>
      page.getByRole('alert').filter({ hasText: 'Could not update the request. Try again.' })
    await expect
      .poll(async () => (await rowError(pageA).count()) + (await rowError(pageB).count()))
      .toBeGreaterThanOrEqual(1)
  } finally {
    await contextA.close()
    await contextB.close()
  }
})

test.describe('zero-child-profile empty states', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))
  })

  test('visiting Requests with zero children shows a coherent empty state', async ({ page }) => {
    await page.route('**/api/v1/story-requests?status=pending', (route) =>
      route.fulfill({ json: { requests: [] } })
    )
    await page.goto('/guardian/requests')
    await expect(page.getByText('No requests to review')).toBeVisible()
  })

  test('visiting Books with zero children shows a coherent empty state', async ({ page }) => {
    await page.route('**/api/v1/guardian/books', (route) =>
      route.fulfill({ json: { books: [] } })
    )
    await page.goto('/guardian/books')
    await expect(page.getByText('No published books yet')).toBeVisible()
  })
})
