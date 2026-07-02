import { expect, test } from '@playwright/test'

/**
 * Coverage for the C4a-3 kid library page (`/library/:profileId`): the
 * Continue Reading hero, the More to Explore shelf, tap-to-rate stars, and
 * the empty-book state. Mirrors profiles.spec.ts's convention: `page.route`
 * mocks against `**\/api/v1/...`, no live backend, and an `addInitScript`
 * auth token so `useApi`'s request interceptor attaches an Authorization
 * header (the mocked routes don't check it, but it matches the real app's
 * request shape).
 */

const STORIES = {
  stories: [
    {
      id: 's1',
      title: 'The Lantern',
      version: 2,
      age_band: '6-8',
      tier: 1,
      reading_level_target: 2,
      node_count: 10,
      rating: null,
      progress: { current_node: 'n2', nodes_visited: 5, updated_at: '2026-07-01T10:00:00Z' },
    },
    {
      id: 's3',
      title: 'Acorn Detectives',
      version: 1,
      age_band: '6-8',
      tier: 1,
      reading_level_target: 2,
      node_count: 8,
      rating: 3,
      progress: null,
    },
  ],
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
})

test('hero shows the in-progress book and shelf shows the rest', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(hero).toContainText('5 of 10 pages explored')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelf).toContainText('Acorn Detectives')
  await expect(shelf).toContainText('Not started')
})

test('tapping the hero opens the reader route', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/storybooks/**', (route) =>
    route.fulfill({ status: 404, json: { detail: 'not needed for this test' } })
  )
  await page.goto('/library/p1')
  await page.getByRole('link', { name: /the lantern/i }).click()
  await expect(page).toHaveURL(/\/read\/p1\/s1\/2$/)
})

test('rating a book posts the upsert and fills the stars', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  let ratingBody: unknown = null
  await page.route('**/api/v1/ratings', (route) => {
    ratingBody = route.request().postDataJSON()
    return route.fulfill({
      json: {
        child_profile_id: 'p1',
        storybook_id: 's3',
        value: 5,
        rated_at: '2026-07-02T00:00:00Z',
        updated_at: '2026-07-02T00:00:00Z',
      },
    })
  })
  await page.goto('/library/p1')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await shelf.getByRole('button', { name: '5 stars' }).click()
  await expect.poll(() => ratingBody).toEqual({
    profile_id: 'p1',
    storybook_id: 's3',
    value: 5,
  })
  await expect(shelf.getByRole('button', { name: '5 stars' })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
})

test('empty library shows the no-books state', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
  await page.goto('/library/p1')
  await expect(page.getByText('No books yet')).toBeVisible()
  await expect(page.getByText(/ask a grown-up/i)).toBeVisible()
})
