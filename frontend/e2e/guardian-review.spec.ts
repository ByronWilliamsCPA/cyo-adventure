import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * ADR-005 approval gate e2e. Approve is admin-only on the backend; the
 * guardian-403 case asserts the UI fails closed (error alert, no navigation,
 * no false success). Failure copy is status-agnostic by design
 * (ReviewDetailPage.runAction catches all errors identically).
 */

const SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: {
    count: 1,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
  blob: {
    title: 'The Cave',
    start_node: 'n1',
    nodes: [
      {
        id: 'n1',
        body: 'A dark cave yawned ahead.',
        choices: [{ label: 'Step inside', target: 'n2' }],
      },
      { id: 'n2', body: 'The path forked left and right.', choices: [] },
    ],
  },
  flagged_passages: [
    {
      node_id: 'n1',
      prose: 'A dark cave yawned ahead.',
      findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'n1',
          verdict: 'flag',
          score: null,
          message: 'possibly scary',
        },
      ],
    },
  ],
  story_level_findings: [],
}

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockEmptyConsole(page) // for the post-action navigation back to /admin
  await page.route('**/api/v1/storybooks/s1/review*', (route) => route.fulfill({ json: SURFACE }))
})

test('flagged passages render before the full story', async ({ page }) => {
  await mockMe(page, { role: 'admin' })
  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  const h2s = page.getByRole('heading', { level: 2 })
  await expect(h2s.first()).toHaveText('Flagged passages')
  await expect(page.getByText('possibly scary')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Full story' })).toBeVisible()
})

test('admin approve posts visibility:family by default and returns to the console (ADR-005)', async ({
  page,
}) => {
  await mockMe(page, { role: 'admin' })
  let approveBody: unknown = null
  await page.route('**/api/v1/storybooks/s1/approve', (route) => {
    approveBody = route.request().postDataJSON()
    return route.fulfill({
      json: {
        id: 's1',
        status: 'published',
        current_published_version: 1,
        approved_by: 'admin-user-id',
        published_at: '2026-07-04T00:00:00Z',
        visibility: 'family',
      },
    })
  })

  await page.goto('/admin/review/s1')
  await page.getByRole('button', { name: /^Approve$/ }).click()
  await expect(page.getByText('Approve this story?')).toBeVisible()
  // The default (untouched) approval publishes to this family only, never the
  // cross-family catalog: the PII warning stays absent until catalog is chosen.
  await expect(page.getByText(/Catalog books are visible to every family/)).toHaveCount(0)
  await page.getByRole('button', { name: 'Confirm approve' }).click()

  await expect(page).toHaveURL(/\/admin$/)
  // Assert the wire body, not just that a POST fired: 'family' is the
  // safe-by-default scope and must be what ships when the radio is untouched.
  await expect.poll(() => approveBody).toEqual({ visibility: 'family' })
})

test('approving to the catalog surfaces the PII warning and posts visibility:catalog', async ({
  page,
}) => {
  // The catalog option publishes this story to EVERY family, so it is the one
  // approve path that must warn about personal details before it ships. This
  // exercises both halves of that contract: the warning copy appears only once
  // catalog is selected, and 'catalog' is what actually goes on the wire.
  await mockMe(page, { role: 'admin' })
  let approveBody: unknown = null
  await page.route('**/api/v1/storybooks/s1/approve', (route) => {
    approveBody = route.request().postDataJSON()
    return route.fulfill({
      json: {
        id: 's1',
        status: 'published',
        current_published_version: 1,
        approved_by: 'admin-user-id',
        published_at: '2026-07-04T00:00:00Z',
        visibility: 'catalog',
      },
    })
  })

  await page.goto('/admin/review/s1')
  await page.getByRole('button', { name: /^Approve$/ }).click()
  await expect(page.getByText('Approve this story?')).toBeVisible()

  await page.getByRole('radio', { name: 'Catalog (every family)' }).check()
  await expect(
    page.getByText(
      'Catalog books are visible to every family. Confirm the story contains no names, ' +
        'photos, or personal details before sharing.'
    )
  ).toBeVisible()

  await page.getByRole('button', { name: 'Confirm approve' }).click()

  await expect(page).toHaveURL(/\/admin$/)
  await expect.poll(() => approveBody).toEqual({ visibility: 'catalog' })
})

test('a backend 403 on approve fails closed in the UI', async ({ page }) => {
  // The /admin route gate needs the capability to even load the page, so
  // the 403 under test is the backend independently rejecting the approve
  // (e.g. the capability was revoked server-side mid-session). The UI must
  // fail closed either way: error alert, no navigation, no false success.
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/storybooks/s1/approve', (route) =>
    route.fulfill({ status: 403, json: { detail: 'approval requires the admin role' } })
  )

  await page.goto('/admin/review/s1')
  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()

  await expect(
    page.getByText('We could not approve this story. It may be unscreened or no longer in review.')
  ).toBeVisible()
  // Fail closed: still on the review page, no silent success navigation.
  await expect(page).toHaveURL(/\/admin\/review\/s1$/)
})

test('send-back posts the reason and returns to the console', async ({ page }) => {
  await mockMe(page, { role: 'admin' })
  let body: unknown = null
  await page.route('**/api/v1/storybooks/s1/send-back', (route) => {
    body = route.request().postDataJSON()
    return route.fulfill({ json: { id: 's1', status: 'needs_revision', reason: 'too intense' } })
  })

  await page.goto('/admin/review/s1')
  await page.getByRole('button', { name: 'Send Back' }).click()
  await expect(page.getByText('Send back for revision')).toBeVisible()
  await page.getByLabel(/reason/i).fill('too intense for this age')
  await page.getByRole('button', { name: 'Confirm send back' }).click()

  await expect(page).toHaveURL(/\/admin$/)
  await expect.poll(() => body).toEqual({ reason: 'too intense for this age' })
})
