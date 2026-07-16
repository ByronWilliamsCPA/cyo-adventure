import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * Visual regression baselines for the two highest-value pages named in the
 * original testing-infrastructure proposal: the reader and the library.
 * Screenshots are viewport-only (not full-page) and use fixed, mocked data
 * with no cover_url (falls back to a deterministic CSS gradient rather than
 * loading an external image), so a rerun with unchanged UI produces a
 * pixel-identical result. Animations are disabled via the `animations:
 * 'disabled'` screenshot option, which freezes CSS transitions/animations at
 * their end state.
 *
 * Baselines live in visual.spec.ts-snapshots/ (Playwright's default
 * location), keyed by project name and platform, and must be regenerated
 * with `npx playwright test visual.spec.ts --update-snapshots` whenever a
 * deliberate visual change lands; a diff here on an unrelated change is a
 * regression signal, not noise to suppress.
 */

const lantern = loadLanternStory()

test('the reader page matches its visual baseline', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    return route.fulfill({ status: 200, json: { current_node: 'n_entrance', state_revision: 1 } })
  })

  await page.goto('/read/child-a/s_lantern_cave/1')
  await expect(page.getByTestId('reader')).toBeVisible()

  await expect(page).toHaveScreenshot('reader-page.png', { animations: 'disabled' })
})

const LIBRARY_STORIES = {
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

const LIBRARY_PROFILE = {
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

test('the library page matches its visual baseline', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'p1')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: LIBRARY_PROFILE }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: LIBRARY_STORIES }))

  await page.goto('/library/p1')
  await expect(page.getByRole('heading', { name: 'My Books' })).toBeVisible()

  await expect(page).toHaveScreenshot('library-page.png', { animations: 'disabled' })
})
