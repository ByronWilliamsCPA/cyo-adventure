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
  await expect(hero).toContainText('5 pages explored')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelf).toContainText('Acorn Detectives')
  await expect(shelf).toContainText('Not started')
})

// Persistent kid-to-guardian escape hatch (product decision, 2026-08-04):
// KidNav's "Ask a grown-up" link, always visible on the library route
// alongside "Switch reader", goes to the same /guardian/login destination as
// ProfilePickerPage's PIN-failure escape hatch. Pure reachability, not a new
// door into the console: the assertion is on the link's presence/name/target,
// not on what guardian login itself does once there (covered by
// guardian-auth.spec.ts).
test('KidNav offers a persistent Ask a grown-up link to guardian login', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.goto('/library/p1')
  const askGrownup = page.getByRole('link', { name: 'Ask a grown-up' })
  await expect(askGrownup).toBeVisible()
  await askGrownup.click()
  await expect(page).toHaveURL(/\/guardian\/login$/)
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
  await expect
    .poll(() => ratingBody)
    .toEqual({
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
  // Exact copy, not a broad /ask a grown-up/i match: KidNav's persistent
  // "Ask a grown-up" link (present on every library visit, not just this
  // empty state) now also matches that looser pattern.
  await expect(page.getByText('Ask a grown-up to add one!')).toBeVisible()
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
  // Two shelf books plus the "Ask for a new story" end-cap tile, which is a
  // grid cell like any book and must obey the same no-overflow rule below.
  expect(count).toBe(3)
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

// K17 (ADR-016 rings 1-2): the recommendations feed only ever decorates a
// book already on this shelf with a warm chip; it never adds a book or
// offers any interaction beyond the card's own open-book link.
test('shows a family-ring chip on the matching book once the recommendations feed resolves (K17)', async ({
  page,
}) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/recommendations/*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            storybook_id: 's1',
            title: 'The Lantern',
            cover_url: null,
            recommender_name: 'Maya',
            rating: 5,
            ring: 'family',
          },
        ],
      },
    })
  )
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(hero.getByText('Maya loved this')).toBeVisible()
  // Acorn Detectives has no matching feed entry: no chip, absence not error.
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  const acorn = shelf.locator('.book-card', { hasText: 'Acorn Detectives' })
  await expect(acorn.getByText(/loved this/i)).toHaveCount(0)
})

test('shows a connection-ring chip with the Cousin prefix and collapses extra recommenders (K17)', async ({
  page,
}) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/recommendations/*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            storybook_id: 's3',
            title: 'Acorn Detectives',
            cover_url: null,
            recommender_name: 'Leo',
            rating: 4,
            ring: 'connection',
          },
          {
            storybook_id: 's3',
            title: 'Acorn Detectives',
            cover_url: null,
            recommender_name: 'Priya',
            rating: 5,
            ring: 'family',
          },
        ],
      },
    })
  )
  await page.goto('/library/p1')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelf.getByText('Cousin Leo loved this and 1 more')).toBeVisible()
  // Tapping the chip does nothing beyond the card's own open-book link: no
  // reply/send affordance exists anywhere on this surface (ADR-016).
  await expect(page.getByRole('button', { name: /loved this/i })).toHaveCount(0)
  await expect(page.getByRole('textbox')).toHaveCount(0)
})

test('shows no chip (never an error) when the recommendations feed fails', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/recommendations/*', (route) =>
    route.fulfill({ status: 500, json: { detail: 'boom' } })
  )
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(page.getByText(/loved this/i)).toHaveCount(0)
})

// F-6b: the offline shelf fallback (LibraryPage.tsx's `status: 'offline'`
// branch) was unit-only before this. A single route handler models the two
// phases (online, then offline) via closure state, matching this repo's
// one-handler-per-test convention (see reader-reload-resume.spec.ts):
// first a normal visit succeeds and the fire-and-forget cacheLibraryList
// write lands in the real IndexedDB `library_lists` store, then the network
// fetch is made to transport-fail (route.abort(), the same OfflineError path
// classifyApiError.ts maps to `kind: 'offline'`) and a fresh mount (a full
// reload; LibraryPage's load() only re-fires on mount or the 'online' event)
// proves the shelf still renders from the cached list rather than the "We
// lost the bookshelf" error state. The "Time to find your grown-up" consent
// gate is a different, already-covered surface; not duplicated here.
test('shelf still renders from the cached list when the network fetch fails (F-6b)', async ({
  page,
}) => {
  let libraryMode: 'online' | 'offline' = 'online'
  await page.route('**/api/v1/library*', (route) => {
    if (libraryMode === 'offline') {
      return route.abort('internetdisconnected')
    }
    return route.fulfill({ json: STORIES })
  })

  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')

  // Confirm the fire-and-forget cacheLibraryList write actually landed before
  // going offline, so the fallback below reads a real cached shelf rather
  // than racing an empty one.
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            // Versionless open: pinning a version here breaks silently on every
            // DB_VERSION bump (opening an existing v4 database at 3 rejects
            // with VersionError, and onerror's -1 just fails the poll), while a
            // versionless open attaches at whatever version the app created.
            const req = indexedDB.open('cyo-reader')
            req.onerror = () => resolve(-1)
            req.onsuccess = () => {
              try {
                const getReq = req.result
                  .transaction('library_lists', 'readonly')
                  .objectStore('library_lists')
                  .get('p1')
                getReq.onsuccess = () => resolve(getReq.result ? 1 : 0)
                getReq.onerror = () => resolve(-1)
              } catch {
                // Store missing (the app has not created it yet): report a
                // non-match so the poll retries instead of hanging.
                resolve(-1)
              }
            }
          })
      )
    )
    .toBe(1)

  libraryMode = 'offline'
  await page.reload()

  await expect(page.getByText('No internet. These books are ready to read.')).toBeVisible()
  await expect(page.getByText('We lost the bookshelf')).toHaveCount(0)
  const heroAfterOffline = page.getByRole('region', { name: 'Continue Reading' })
  await expect(heroAfterOffline).toContainText('The Lantern')
  const shelfAfterOffline = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelfAfterOffline).toContainText('Acorn Detectives')
  // Requesting a new story needs the network; the offline shelf hides both
  // request affordances rather than offering ones that could only fail.
  await expect(page.getByRole('button', { name: 'Ask for a new story' })).toHaveCount(0)
})

test('shows no chip when the recommendations feed is empty', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/recommendations/*', (route) => route.fulfill({ json: { items: [] } }))
  await page.goto('/library/p1')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  await expect(page.getByText(/loved this/i)).toHaveCount(0)
})
