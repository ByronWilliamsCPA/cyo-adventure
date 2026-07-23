import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedDeviceGrant, seedGuardianSession } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * Visual regression baselines across every top-level shell and modal
 * surface: landing, kid picker, kid library, reader (+ its conflict
 * dialog), guardian console/intake/requests/books (+ assign dialog)/
 * profiles (+ profile-form dialog), admin console/requests/moderation-
 * thresholds/moderation-dashboard. Screenshots are viewport-only (not
 * full-page) and use fixed, mocked data with no cover_url (falls back to a
 * deterministic CSS gradient rather than loading an external image), so a
 * rerun with unchanged UI produces a pixel-identical result. Animations are
 * disabled via the `animations: 'disabled'` screenshot option, which
 * freezes CSS transitions/animations at their end state.
 *
 * Baselines live in visual.spec.ts-snapshots/ (Playwright's default
 * location), keyed by project name and platform, and must be regenerated
 * with `npx playwright test visual.spec.ts --update-snapshots` whenever a
 * deliberate visual change lands; a diff here on an unrelated change is a
 * regression signal, not noise to suppress.
 *
 * CI-only (P4-1): the committed baselines are generated on the Linux CI
 * runner. A developer's host (macOS/Windows/WSL) renders fonts with a
 * different rasterizer, so every screenshot drifts by a few sub-pixel anti-
 * aliased edges on a local run. That is host noise, not a UI regression, and
 * it drowned out real signal in `npm run test:e2e` (all 18 "failed" locally,
 * 0 in CI). The chromium project's `testIgnore` therefore skips this file when
 * `process.env.CI` is unset (see playwright.config.ts), so a local
 * `npm run test:e2e` never runs it, while CI (GitHub Actions always sets
 * `CI=true`) still runs and enforces the baselines on the platform they were
 * captured on, and the update-visual-snapshots workflow still regenerates
 * them. Run locally on demand with `CI=1 npm run test:e2e -- visual.spec.ts`
 * after regenerating snapshots for your platform. The gating is structural, in
 * the config, not a per-test skip marker that would silence a real failure.
 */

test('the landing page matches its visual baseline', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: /Grown-ups/ })).toBeVisible()
  await expect(page).toHaveScreenshot('landing-page.png', { animations: 'disabled' })
})

const PICKER_PROFILES = {
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

test('the kid picker page matches its visual baseline', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PICKER_PROFILES }))
  await page.goto('/kids')
  await expect(page.getByRole('heading', { name: "Who's reading?" })).toBeVisible()
  await expect(page).toHaveScreenshot('kid-picker-page.png', { animations: 'disabled' })
})

test('the guardian console matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'guardian' })
  await mockEmptyConsole(page)
  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  await expect(page).toHaveScreenshot('guardian-console-page.png', { animations: 'disabled' })
})

test('the admin console matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  // AdminConsolePage stamps its "Updated HH:MM" label with the real
  // wall-clock `new Date()` at fetch time, not a mocked/fixed value. A
  // baseline screenshot therefore bakes in whatever minute it was
  // regenerated in; freezing the clock before navigation keeps this
  // deterministic regardless of how long the rest of the suite runs
  // before reaching this test (a real, pre-existing gap this file's
  // docblock note about pixel-identical reruns did not account for).
  await page.clock.install({ time: new Date('2026-01-01T12:00:00Z') })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page).toHaveScreenshot('admin-console-page.png', { animations: 'disabled' })
})

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

const INTAKE_PROFILE = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '8-11',
      reading_level_cap: 4,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

test('the guardian intake page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: INTAKE_PROFILE }))
  // IntakePage loads profiles AND jobs concurrently (Promise.all); a missing
  // jobs mock rejects and replaces the page with its error state a moment
  // after the initial render, racing with when the screenshot is taken.
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  await page.goto('/guardian/intake')
  await expect(page.getByRole('heading', { name: 'Request a story' })).toBeVisible()
  await expect(page).toHaveScreenshot('guardian-intake-page.png', { animations: 'disabled' })
})

test('the guardian requests page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  // RequestsPage also embeds RequestStoryForm (guardian mode), which fetches
  // /v1/profiles on its own; a missing mock here races the same way the
  // jobs fetch does on the intake page above.
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))
  await page.goto('/guardian/requests')
  await expect(page.getByRole('heading', { name: 'Story requests' })).toBeVisible()
  await expect(page).toHaveScreenshot('guardian-requests-page.png', { animations: 'disabled' })
})

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

test('the guardian books page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/guardian/books', (route) => route.fulfill({ json: ASSIGN_BOOKS }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: ASSIGN_PROFILES }))
  await page.route('**/api/v1/storybooks/story-1/content-summary', (route) =>
    route.fulfill({ json: ASSIGN_CONTENT_SUMMARY })
  )
  await page.goto('/guardian/books')
  await expect(page.getByText('The Brave Little Fox')).toBeVisible()
  await expect(page).toHaveScreenshot('guardian-books-page.png', { animations: 'disabled' })
})

test('the assign-children dialog matches its visual baseline', async ({ page, context }) => {
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
  await expect(page).toHaveScreenshot('assign-children-dialog.png', { animations: 'disabled' })
})

test('the guardian profiles page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: ASSIGN_PROFILES }))
  await page.goto('/guardian/profiles')
  await expect(page.getByRole('heading', { name: 'Profiles' })).toBeVisible()
  await expect(page).toHaveScreenshot('guardian-profiles-page.png', { animations: 'disabled' })
})

test('the profile-form dialog matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))
  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page).toHaveScreenshot('profile-form-dialog.png', { animations: 'disabled' })
})

test('the admin requests page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=pending', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  // AdminRequestsPage also embeds RequestStoryForm (admin mode), which
  // fetches /v1/admin/families on its own; a missing mock here races the
  // same way the jobs/profiles fetches do on the guardian pages above.
  await page.route('**/api/v1/admin/families', (route) => route.fulfill({ json: { families: [] } }))
  await page.goto('/admin/requests')
  await expect(page.getByRole('heading', { name: 'Story requests' })).toBeVisible()
  await expect(page).toHaveScreenshot('admin-requests-page.png', { animations: 'disabled' })
})

const EMPTY_THRESHOLDS = {
  default_min_verdict: 'flag',
  rows: [] as {
    age_band: string
    category: string
    min_verdict: string
    min_score: number | null
  }[],
  known_categories: ['violence', 'language'],
}

test('the admin moderation thresholds page matches its visual baseline', async ({
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
  await expect(page).toHaveScreenshot('admin-moderation-thresholds-page.png', {
    animations: 'disabled',
  })
})

test('the admin moderation dashboard matches its visual baseline', async ({ page, context }) => {
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
  await expect(page).toHaveScreenshot('admin-moderation-dashboard-page.png', {
    animations: 'disabled',
  })
})

test('the admin provider allowlist page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: { rows: [] } })
  )
  await page.goto('/admin/provider-allowlist')
  await expect(page.getByRole('heading', { name: 'Provider allowlist' })).toBeVisible()
  await expect(page).toHaveScreenshot('admin-provider-allowlist-page.png', {
    animations: 'disabled',
  })
})

const AUTHORING_QUEUE_REQUEST = {
  id: 'req-1',
  profile_id: 'p1',
  status: 'approved',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: 'short',
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const AUTHORING_QUEUE_ALLOWLIST = {
  rows: [
    {
      id: 'a1',
      provider: 'anthropic',
      model_id: 'claude-sonnet-4-6',
      enabled: true,
      display_name: 'Claude Sonnet 4.6 (direct)',
    },
  ],
}

test('the admin authoring queue page matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=approved', (route) =>
    route.fulfill({ json: { requests: [AUTHORING_QUEUE_REQUEST] } })
  )
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: AUTHORING_QUEUE_ALLOWLIST })
  )
  await page.goto('/admin/authoring-queue')
  await expect(page.getByRole('heading', { name: 'Authoring queue' })).toBeVisible()
  await expect(page).toHaveScreenshot('admin-authoring-queue-page.png', { animations: 'disabled' })
})

test('the authoring plan dialog matches its visual baseline', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=approved', (route) =>
    route.fulfill({ json: { requests: [AUTHORING_QUEUE_REQUEST] } })
  )
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: AUTHORING_QUEUE_ALLOWLIST })
  )
  await page.goto('/admin/authoring-queue')
  await page.getByRole('button', { name: 'Build authoring plan' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page).toHaveScreenshot('authoring-plan-dialog.png', { animations: 'disabled' })
})
