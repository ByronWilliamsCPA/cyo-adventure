import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian preview-as-child (`/guardian/preview/:profileId`,
 * PreviewAsChildPage.tsx): a guardian's read-only look at a child's real
 * LibraryPage shelf, reached from ProfilesPage's "Preview as child" link.
 * Had no browser-level coverage before this file: the read-only contract
 * (no rating, no request affordances, the exit link) is otherwise only
 * asserted against a mocked axios instance, not a real routed page.
 */

const REMY = {
  id: 'p1',
  display_name: 'Remy',
  age_band: '6-8',
  reading_level_cap: 99,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-01-01T00:00:00Z',
}

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

/**
 * Seeds a signed-in guardian session and every endpoint the preview route
 * touches: the guardian shell's fan-out (pending-request nav badge,
 * notification poll, same as guardian-connections.spec.ts's helper), the
 * page's own profile lookup, and LibraryPage's shelf/history/recommendations/
 * progress fetches underneath it. Deliberately NOT a `test.beforeEach`: the
 * unauthenticated-redirect test below must reach `/guardian/preview/p1` with
 * no session seeded at all.
 */
async function setUpAuthenticatedPreview(context: BrowserContext, page: Page): Promise<void> {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/story-requests**', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications**', (route) =>
    route.fulfill({ json: { notifications: [], unread_count: 0 } })
  )
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [REMY] } }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: STORIES }))
  await page.route('**/api/v1/recommendations/*', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/reading-history/*', (route) =>
    route.fulfill({ json: { profile_id: 'p1', books: [] } })
  )
  // #ASSUME: security: the child-principal-only progress endpoint 403s for a
  // guardian's own bearer in real usage (PreviewAsChildPage.tsx's docstring);
  // mirror that here rather than letting the request fall through unmocked.
  await page.route('**/api/v1/me/progress', (route) =>
    route.fulfill({ status: 403, json: { detail: 'forbidden' } })
  )
}

test('renders the previewed child shelf read-only with a named banner', async ({
  page,
  context,
}) => {
  await setUpAuthenticatedPreview(context, page)

  await page.goto('/guardian/preview/p1')

  await expect(page.locator('.preview-as-child__banner')).toContainText(
    'Previewing as Remy (read-only)'
  )
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  await expect(hero).toContainText('The Lantern')
  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await expect(shelf).toContainText('Acorn Detectives')
})

test('read-only preview suppresses rating and story-request affordances', async ({
  page,
  context,
}) => {
  await setUpAuthenticatedPreview(context, page)

  await page.goto('/guardian/preview/p1')

  await expect(page.getByRole('region', { name: 'More to Explore' })).toContainText(
    'Acorn Detectives'
  )
  await expect(page.getByRole('button', { name: /Rate \d stars?/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Ask for a new story' })).toHaveCount(0)
})

test('the exit-preview link returns to the guardian profiles page', async ({ page, context }) => {
  await setUpAuthenticatedPreview(context, page)

  await page.goto('/guardian/preview/p1')
  await page.getByRole('link', { name: 'Exit preview' }).click()

  await expect(page).toHaveURL(/\/guardian\/profiles$/)
})

test('an unauthenticated visit to the preview route redirects to guardian login', async ({
  page,
}) => {
  await page.goto('/guardian/preview/p1')

  await expect(page).toHaveURL(/\/guardian\/login$/)
})
