import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * Coverage for A16 (Cover generation, register capability): the admin
 * ReviewDetailPage's "Generate cover" button is present and its click fires
 * the mocked POST to the cover endpoint (src/admin/ReviewDetailPage.tsx's
 * generateCover -> guardian/coverApi.ts's CoverApi.generate). Mock plumbing
 * (mockMe, mockEmptyConsole, seedGuardianSession, the storybooks/:id/review*
 * route) mirrors naive-user/naive-admin-misuse.spec.ts's existing
 * /admin/review/:id coverage, so this needed no new support-file additions.
 */

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

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.route('**/api/v1/storybooks/s1/review*', (route) =>
    route.fulfill({ json: REVIEW_SURFACE })
  )
})

test('the Generate cover button is present and its click fires the cover POST (A16)', async ({
  page,
}) => {
  let getCount = 0
  let postCount = 0
  await page.route('**/api/v1/storybooks/s1/versions/1/cover', (route) => {
    if (route.request().method() === 'POST') {
      postCount += 1
      return route.fulfill({ json: { cover_status: 'generating', cover_url: null } })
    }
    getCount += 1
    return route.fulfill({ json: { cover_status: 'none', cover_url: null } })
  })

  await page.goto('/admin/review/s1')
  const generateButton = page.getByRole('button', { name: 'Generate cover' })
  await expect(generateButton).toBeVisible()
  // The status GET fires on mount to seed the button's state, before any click.
  await expect.poll(() => getCount).toBeGreaterThan(0)

  await generateButton.click()
  await expect.poll(() => postCount).toBe(1)
  await expect(page.getByRole('button', { name: 'Generating cover…' })).toBeVisible()
})
