import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

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

// KidNav (mounted by KidShell on every /library/:profileId route) fetches
// GET /api/v1/profiles unconditionally, same as the picker (see
// profiles.spec.ts). Every test in this file navigates to /library/p1, so the
// mock lives in beforeEach alongside the auth token init script.
const PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Remy',
      age_band: '6-8',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context, page }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /library/* redirects to guardian login.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
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
  await shelf.getByRole('button', { name: 'Rate 5 stars' }).click()
  await expect.poll(() => ratingBody).toEqual({
    profile_id: 'p1',
    storybook_id: 's3',
    value: 5,
  })
  await expect(shelf.getByRole('button', { name: 'Rate 5 stars' })).toHaveAttribute(
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

test('shelf shows a cover image when set and the letter-tile fallback when absent (K8)', async ({
  page,
}) => {
  // Coverage for K8 (Covers on the shelf): a book with cover_url renders the
  // AI cover art image; a book without one falls back to the deterministic
  // letter tile (coverPalette.ts) instead of a broken-image icon or blank tile.
  const stories = {
    stories: [
      { ...STORIES.stories[0], cover_url: 'https://cdn.example/covers/lantern.webp' },
      { ...STORIES.stories[1], cover_url: null },
    ],
  }
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))
  // The <img> issues a real (mocked) request for its src; without this route
  // the request fails and BookCard's onError falls back to the letter tile,
  // which would defeat the point of this test. A 1x1 transparent PNG is
  // enough for the browser to decode and render the <img> successfully.
  const onePixelPng = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64'
  )
  await page.route('https://cdn.example/covers/lantern.webp', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: onePixelPng })
  )
  await page.goto('/library/p1')

  // The Lantern (in-progress) renders in the Continue Reading hero, with a
  // real <img> for its cover.
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  const heroCover = hero.locator('img.book-card__cover')
  await expect(heroCover).toHaveAttribute('src', 'https://cdn.example/covers/lantern.webp')
  await expect(hero.locator('.book-card__tile--painted')).toHaveCount(0)

  // Acorn Detectives (no cover_url) renders on the shelf with the painted
  // letter-tile fallback: no <img>, the title's first letter instead.
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  const shelfCard = shelf.locator('.book-card', { hasText: 'Acorn Detectives' })
  await expect(shelfCard.locator('img.book-card__cover')).toHaveCount(0)
  await expect(shelfCard.locator('.book-card__tile--painted')).toBeVisible()
  await expect(shelfCard.locator('.book-card__letter')).toHaveText('A')
})

test('shelf grid does not overflow the viewport on a phone screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const stories = {
    stories: [
      ...STORIES.stories,
      {
        id: 's4',
        title: 'Moonlit Meadow',
        version: 1,
        age_band: '6-8',
        tier: 1,
        reading_level_target: 2,
        node_count: 6,
        rating: null,
        progress: null,
      },
    ],
  }
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))
  await page.goto('/library/p1')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelf).toContainText('Acorn Detectives')
  await expect(shelf).toContainText('Moonlit Meadow')

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  )
  expect(overflow).toBe(0)

  const shelfCards = page.locator('.library__shelf > li')
  const count = await shelfCards.count()
  expect(count).toBe(2)
  for (let i = 0; i < count; i += 1) {
    const box = await shelfCards.nth(i).boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  }
})

test('shows the endings tracker on a started book once reading-history resolves (K6)', async ({
  page,
}) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/reading-history/*', (route) =>
    route.fulfill({
      json: {
        profile_id: 'p1',
        books: [
          {
            storybook_id: 's1',
            title: 'The Lantern',
            endings_found: 2,
            ending_ids: ['e1', 'e2'],
            total_endings: 5,
            in_progress: true,
            last_activity_at: '2026-07-01T10:00:00Z',
          },
        ],
      },
    })
  )
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(hero.getByText('2 of 5 endings found')).toBeVisible()
  // Acorn Detectives (not started, no completion yet) has no history row and
  // shows no badge: absence, not an error, for the not-yet-tracked case.
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  const acorn = shelf.locator('.book-card', { hasText: 'Acorn Detectives' })
  await expect(acorn.getByText(/endings found/i)).toHaveCount(0)
})

test('shows no endings tracker (never an error) when the reading-history fetch fails', async ({
  page,
}) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/reading-history/*', (route) =>
    route.fulfill({ status: 500, json: { detail: 'boom' } })
  )
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(page.getByText(/endings found/i)).toHaveCount(0)
})
