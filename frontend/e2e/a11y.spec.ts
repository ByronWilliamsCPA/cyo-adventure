import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedDeviceGrant, seedGuardianSession } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * Automated accessibility smoke, WCAG 2.1 A/AA rules via axe-core, across
 * every top-level page: landing, kid picker, kid library (populated/empty),
 * reader, guardian login/console/intake/requests/books/profiles, and admin
 * console/requests/moderation-thresholds/moderation-dashboard. This is a
 * floor, not a substitute for manual testing: axe catches programmatically
 * detectable issues (missing labels, contrast, ARIA misuse) but not things
 * like keyboard-trap logic or whether an alternative text is actually
 * meaningful. `/admin/review/:id` is deliberately excluded, same reasoning
 * as e2e-prod/guardian-admin-smoke.spec.ts: it needs a real storybook id and
 * its heading is the dynamic story title, not a fixed one to assert on.
 */

const lantern = loadLanternStory()

const TWO_PROFILES = {
  profiles: [
    {
      id: 'child-fox',
      display_name: 'Remy',
      age_band: '5-8',
      reading_level_cap: 3,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

const ONE_STORY = {
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
      progress: null,
    },
  ],
}

async function assertNoViolations(page: Page) {
  // Scoped to WCAG 2.1 A/AA, matching this file's stated intent. axe's full
  // default ruleset also includes "best-practice" rules (e.g. requiring a
  // <main> landmark or exactly one <h1>) that are worth fixing but are not
  // WCAG conformance failures; keeping the gate to WCAG tags avoids drowning
  // real conformance regressions in opinionated-but-optional findings.
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
}

test('landing page has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/')
  await assertNoViolations(page)
})

test('kid profile picker has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/kids')
  await expect(page.getByRole('heading', { name: "Who's reading?" })).toBeVisible()
  await assertNoViolations(page)
})

test('kid library (populated) has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: ONE_STORY }))
  await page.goto('/library/child-fox')
  await expect(page.getByRole('heading', { name: 'My Books' })).toBeVisible()
  await assertNoViolations(page)
})

test('kid library (empty) has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
  await page.goto('/library/child-fox')
  await expect(page.getByRole('heading', { name: 'No books yet' })).toBeVisible()
  await assertNoViolations(page)
})

test('guardian console has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'guardian' })
  await mockEmptyConsole(page)
  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  await assertNoViolations(page)
})

test('admin console has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await assertNoViolations(page)
})

test('the reader page has no detectable accessibility violations', async ({ page, context }) => {
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
  await assertNoViolations(page)
})

test('the guardian login page has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/guardian/login')
  await expect(page.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian intake page has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/guardian/intake')
  await expect(page.getByRole('heading', { name: 'Request a story' })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian requests page has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.goto('/guardian/requests')
  await expect(page.getByRole('heading', { name: 'Story requests' })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian books page has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/guardian/books', (route) => route.fulfill({ json: { books: [] } }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/guardian/books')
  // exact: true, else this also matches the empty state's "No published
  // books yet" heading (substring match on role name).
  await expect(page.getByRole('heading', { name: 'Books', exact: true })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian profiles page has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/guardian/profiles')
  await expect(page.getByRole('heading', { name: 'Profiles' })).toBeVisible()
  await assertNoViolations(page)
})

test('the admin requests page has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.goto('/admin/requests')
  await expect(page.getByRole('heading', { name: 'Story requests' })).toBeVisible()
  await assertNoViolations(page)
})

const EMPTY_THRESHOLDS = {
  default_min_verdict: 'flag',
  rows: [] as { age_band: string; category: string; min_verdict: string; min_score: number | null }[],
  known_categories: ['violence', 'language'],
}

test('the admin moderation thresholds page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/moderation-thresholds', (route) =>
    route.fulfill({ json: EMPTY_THRESHOLDS })
  )
  await page.route('**/api/v1/admin/moderation/noise-floor', (route) =>
    route.fulfill({ json: { value: 0.2 } })
  )
  await page.goto('/admin/moderation-thresholds')
  await expect(page.getByRole('heading', { name: 'Moderation thresholds' })).toBeVisible()
  await assertNoViolations(page)
})

test('the admin moderation dashboard has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/moderation/dashboard', (route) =>
    route.fulfill({ json: { insights: [], recent_changes: [] } })
  )
  await page.route('**/api/v1/admin/moderation/suggestions', (route) =>
    route.fulfill({ json: { min_decided_versions: 5, min_override_rate: 0.5, suggestions: [] } })
  )
  await page.goto('/admin/moderation-dashboard')
  await expect(page.getByRole('heading', { name: 'Moderation dashboard' })).toBeVisible()
  await assertNoViolations(page)
})

// --- Modal/dialog surfaces ---------------------------------------------

const ASSIGN_BOOKS = {
  books: [
    {
      storybook_id: 'story-1',
      title: 'The Brave Little Fox',
      version: 1,
      age_band: '10-13',
      screened: true,
      flagged_count: 0,
      assigned_profile_ids: ['p1'],
      visibility: 'family',
    },
  ],
}

const ASSIGN_PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '10-13',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
    {
      id: 'p2',
      display_name: 'Reader A2',
      age_band: '8-11',
      reading_level_cap: 99,
      avatar: 'owl',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

const ASSIGN_CONTENT_SUMMARY = {
  storybook_id: 'story-1',
  version: 1,
  screened: true,
  summary: null,
  flagged_count: 0,
  findings: [],
}

test('the assign-children dialog has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/guardian/books', (route) => route.fulfill({ json: ASSIGN_BOOKS }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: ASSIGN_PROFILES }))
  await page.route('**/api/v1/storybooks/story-1/content-summary', (route) =>
    route.fulfill({ json: ASSIGN_CONTENT_SUMMARY })
  )
  await page.route('**/api/v1/storybooks/story-1/assignments', (route) =>
    route.fulfill({ json: { storybook_id: 'story-1', profile_ids: ['p1'] } })
  )

  await page.goto('/guardian/books')
  await page.getByRole('button', { name: /^Assign The Brave Little Fox$/ }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await assertNoViolations(page)
})

test('the profile-form dialog has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))

  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await assertNoViolations(page)
})

const CONFLICT_SERVER_ROW = {
  current_node: 'n_cave_fork',
  var_state: {},
  path: ['n_entrance', 'n_cave_fork'],
  visit_set: ['n_entrance', 'n_cave_fork'],
  version: 1,
  state_revision: 5,
  save_slots: {},
}

test('the reader conflict dialog has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
  let puts = 0
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    puts += 1
    if (puts === 1) {
      return route.fulfill({ status: 409, json: { current_row: CONFLICT_SERVER_ROW } })
    }
    return route.fulfill({ status: 200, json: CONFLICT_SERVER_ROW })
  })

  await page.goto('/read/child-a/s_lantern_cave/1')
  await expect(page.getByTestId('conflict-dialog')).toBeVisible()
  await assertNoViolations(page)
})
