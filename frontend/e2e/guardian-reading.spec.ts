import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * G9 guardian engagement-visibility page (route-mocked): sign in as a
 * guardian, open Reading from the nav, see a per-child summary card, and
 * expand it to fetch that profile's per-book reading history.
 */

const SUMMARY = {
  children: [
    {
      profile_id: 'p1',
      display_name: 'Reader A',
      books_started: 2,
      books_finished: 1,
      total_endings_found: 2,
      last_activity_at: '2026-07-15T12:00:00Z',
    },
  ],
}

const HISTORY = {
  profile_id: 'p1',
  books: [
    {
      storybook_id: 'story-1',
      title: 'The Brave Little Fox',
      endings_found: 1,
      ending_ids: ['end-a'],
      total_endings: 3,
      in_progress: true,
      last_activity_at: '2026-07-15T11:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('guardian opens Reading from the nav and expands a child card', async ({ page }) => {
  await mockMe(page)
  await page.route('**/api/v1/story-requests*', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications*', (route) =>
    route.fulfill({ json: { notifications: [] } })
  )
  await page.route('**/api/v1/families/me/reading-summary', (route) =>
    route.fulfill({ json: SUMMARY })
  )
  await page.route('**/api/v1/reading-history/p1', (route) =>
    route.fulfill({ json: HISTORY })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/generation-jobs', (route) =>
    route.fulfill({ json: { jobs: [] } })
  )

  await page.goto('/guardian')
  await page.getByRole('link', { name: 'Reading', exact: true }).click()
  await expect(page).toHaveURL(/\/guardian\/reading$/)

  await expect(page.getByText('Reader A')).toBeVisible()
  await expect(page.getByText('2', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: /Reader A/ }).click()
  await expect(page.getByText('The Brave Little Fox')).toBeVisible()
  await expect(page.getByText(/1 of 3 endings found/)).toBeVisible()
  await expect(page.getByText('Still reading')).toBeVisible()
})

test('shows the Books link in the empty state for a childless family', async ({ page }) => {
  await mockMe(page)
  await page.route('**/api/v1/story-requests*', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications*', (route) =>
    route.fulfill({ json: { notifications: [] } })
  )
  await page.route('**/api/v1/families/me/reading-summary', (route) =>
    route.fulfill({ json: { children: [] } })
  )

  await page.goto('/guardian/reading')
  await expect(page.getByText('No reading yet')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Go to Books' })).toHaveAttribute(
    'href',
    '/guardian/books'
  )
})
