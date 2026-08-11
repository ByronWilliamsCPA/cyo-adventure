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
 * meaningful (keyboard-trap/focus behavior is covered separately in
 * keyboard-nav.spec.ts).
 *
 * Two coverage extensions live at the bottom of this file:
 *   1. Populated + error-state admin scans. The admin scans above use empty
 *      fixtures, so the colored severity pills, content-flag/valence badges,
 *      and inline error alerts never render and never get contrast/name-role
 *      checked. The "populated admin surfaces" block seeds real rows so axe
 *      sees them.
 *   2. `/admin/review/:id`. Previously excluded because its heading is the
 *      dynamic story title (nothing fixed to assert on); an axe scan needs no
 *      fixed heading, only a stable seeded fixture, so it is scanned with a
 *      fixed review-surface fixture (its flagged-passage cards, verdict/valence
 *      badges, and alert states included).
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

// Per-PR CI stays scoped to WCAG 2.1 conformance tags only (see the comment
// below): fast and non-noisy, so it can gate every PR. The weekly
// "Accessibility Compliance" workflow (.github/workflows/
// accessibility-compliance-weekly.yml) sets A11Y_EXTENDED=1 to run this same
// suite against WCAG 2.2 (both wcag22a AND wcag22aa: axe's WCAG tags are
// additive per level, so wcag22aa alone would silently skip the 2.2 Level A
// criteria, UW-N04) plus axe's "best-practice" rules (e.g. missing
// landmark/heading structure), without adding that scope, or run time, to
// every PR.
const AXE_TAGS = process.env.A11Y_EXTENDED === '1'
  ? ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa', 'best-practice']
  : ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function assertNoViolations(page: Page) {
  // Extended-only: axe's best-practice landmark/heading rules (unlike the
  // WCAG-tagged rules the default run checks) fire against the ABSENCE of
  // structure, so they misfire if the scan lands while a lazy route chunk's
  // Suspense fallback (routeElements.tsx's "Just a sec..." <LoadingStatus
  // className="route-fallback">) is still the only thing mounted. The
  // default WCAG-tagged run never needed this: none of its rules depend on
  // page-wide structure being present, only on structure that IS present
  // being correctly formed. Resolves immediately when the fallback was never
  // mounted (the common case once a chunk is warm).
  // #ASSUME: timing dependency: 10s covers a cold lazy-chunk load on a CI
  // runner; the landing-page test additionally asserts real content first
  // (see that test) so this wait is never the only thing standing between
  // the scan and a still-loading page there. #VERIFY: if this ever times out
  // in CI, widen the timeout before suspecting a real accessibility
  // regression; a genuinely hung fallback is a build/network problem, not an
  // axe finding.
  if (AXE_TAGS.includes('best-practice')) {
    await page.waitForSelector('.route-fallback', { state: 'detached', timeout: 10_000 })
  }
  // Let any entrance animation settle before scanning. The Dialog component
  // fades and scales in (opacity 0 -> 1); axe computes color contrast from the
  // composited style, so an element scanned mid-fade reports a blended,
  // non-resting color (e.g. a primary button's ink reading as ~#796c60 at
  // 1.9:1) that trips a transient contrast finding even though the resting
  // state is compliant. Wait for finite in-flight animations to finish, capped
  // so an indefinite animation (a spinner) can never hang the scan.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const finite = document
          .getAnimations()
          .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        void Promise.race([
          Promise.all(finite.map((a) => a.finished.catch(() => undefined))),
          new Promise((r) => setTimeout(r, 1000)),
        ]).then(() => resolve())
      })
  )
  // Scoped to WCAG tags by default (see AXE_TAGS above), matching this
  // file's stated intent. axe's full default ruleset also includes
  // "best-practice" rules (e.g. requiring a <main> landmark or exactly one
  // <h1>) that are worth fixing but are not WCAG conformance failures;
  // keeping the per-PR gate to WCAG tags avoids drowning real conformance
  // regressions in opinionated-but-optional findings. The weekly extended
  // run opts into those rules via A11Y_EXTENDED.
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
}

test('landing page has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/')
  // Unlike every other test below, this one has no per-test content assertion
  // to wait on first (the landing route has no auth/route gate to clear), so
  // it is the one place a scan could otherwise land before the lazy chunk
  // mounts anything at all, not just before it replaces an already-mounted
  // fallback. Waiting on the real heading closes that gap the same way the
  // other tests' pre-existing assertions already do.
  await expect(page.getByRole('heading', { name: 'CYO Adventure' })).toBeVisible()
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

test('kid library (populated) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
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

test('kid library (empty) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
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

test('the guardian intake page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  // IntakePage loads profiles AND jobs concurrently (Promise.all); a missing
  // jobs mock rejects and replaces the page with its error state a moment
  // after the initial render, racing with when axe scans the page.
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  await page.goto('/guardian/intake')
  await expect(page.getByRole('heading', { name: 'Request a story' })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian requests page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
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
  await expect(page.getByRole('heading', { name: 'Requests from your kids' })).toBeVisible()
  await assertNoViolations(page)
})

test('the guardian books page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
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

test('the guardian profiles page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/guardian/profiles')
  await expect(page.getByRole('heading', { name: 'Profiles' })).toBeVisible()
  await assertNoViolations(page)
})

test('the admin requests page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
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
  await assertNoViolations(page)
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

test('the admin provider allowlist page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: { rows: [] } })
  )
  await page.goto('/admin/provider-allowlist')
  await expect(page.getByRole('heading', { name: 'Provider allowlist' })).toBeVisible()
  await assertNoViolations(page)
})

const APPROVED_REQUEST = {
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

const ONE_ALLOWLIST_ROW = {
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

test('the admin authoring queue page has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=approved', (route) =>
    route.fulfill({ json: { requests: [APPROVED_REQUEST] } })
  )
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: ONE_ALLOWLIST_ROW })
  )
  await page.goto('/admin/authoring-queue')
  await expect(page.getByRole('heading', { name: 'Authoring queue' })).toBeVisible()
  await assertNoViolations(page)
})

test('the authoring plan dialog has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=approved', (route) =>
    route.fulfill({ json: { requests: [APPROVED_REQUEST] } })
  )
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: ONE_ALLOWLIST_ROW })
  )
  await page.goto('/admin/authoring-queue')
  await page.getByRole('button', { name: 'Build authoring plan' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
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

// --- Populated admin surfaces ------------------------------------------
//
// The admin scans earlier in this file use empty fixtures, so the colored
// severity pills, verdict/valence badges, table rows, and inline alerts never
// render and are never contrast/name-role-value checked. These scans seed real
// rows (mirroring the fixtures moderation.spec.ts / provider-allowlist.spec.ts /
// admin-read-heavy.spec.ts already define) so axe sees the populated UI.

const POPULATED_THRESHOLDS = {
  default_min_verdict: 'flag',
  rows: [
    { age_band: '5-8', category: 'violence', min_verdict: 'block', min_score: null },
    { age_band: '8-11', category: 'language', min_verdict: 'advisory', min_score: 0.4 },
  ],
  known_categories: ['violence', 'language'],
}

test('the admin moderation thresholds page (populated) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/moderation-thresholds', (route) =>
    route.fulfill({ json: POPULATED_THRESHOLDS })
  )
  await page.route('**/api/v1/admin/moderation/noise-floor', (route) =>
    route.fulfill({ json: { value: 0.2 } })
  )
  await page.goto('/admin/moderation-thresholds')
  await expect(page.getByRole('cell', { name: 'violence', exact: true })).toBeVisible()
  await assertNoViolations(page)
})

const POPULATED_DASHBOARD = {
  insights: [
    {
      age_band: '5-8',
      category: 'violence',
      advisory_findings: 3,
      flag_findings: 5,
      decided_versions: 10,
      released_versions: 6,
      // At/above the 0.5 gate: renders the emphasized (at-gate) row styling.
      override_rate: 0.6,
      last_seen: '2026-07-20T10:00:00Z',
    },
    {
      age_band: '8-11',
      category: 'language',
      advisory_findings: 1,
      flag_findings: 0,
      decided_versions: 4,
      released_versions: 1,
      override_rate: 0.25,
      last_seen: '2026-07-19T10:00:00Z',
    },
  ],
  recent_changes: [
    {
      event_type: 'noise_floor_changed',
      entity_id: 'global',
      occurred_at: '2026-07-20T09:00:00Z',
      payload: { value: 0.2 },
    },
  ],
}

const POPULATED_SUGGESTIONS = {
  min_decided_versions: 5,
  min_override_rate: 0.5,
  suggestions: [
    {
      age_band: '5-8',
      category: 'violence',
      decided_versions: 10,
      released_versions: 6,
      override_rate: 0.6,
      current_min_verdict: 'advisory',
      current_min_score: null,
      suggested_min_verdict: 'flag',
    },
  ],
}

test('the admin moderation dashboard (populated) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/moderation/dashboard', (route) =>
    route.fulfill({ json: POPULATED_DASHBOARD })
  )
  await page.route('**/api/v1/admin/moderation/suggestions', (route) =>
    route.fulfill({ json: POPULATED_SUGGESTIONS })
  )
  await page.goto('/admin/moderation-dashboard')
  await expect(page.getByRole('heading', { name: 'Threshold suggestions' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'violence' }).first()).toBeVisible()
  await assertNoViolations(page)
})

const POPULATED_ALLOWLIST = {
  rows: [
    {
      id: 'a1',
      provider: 'anthropic',
      model_id: 'claude-sonnet-4-6',
      enabled: true,
      display_name: 'Claude Sonnet 4.6 (direct)',
    },
    {
      id: 'a2',
      provider: 'ollama',
      model_id: 'qwen2.5:14b',
      enabled: false,
      display_name: null,
    },
  ],
}

test('the admin provider allowlist page (populated) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: POPULATED_ALLOWLIST })
  )
  await page.goto('/admin/provider-allowlist')
  await expect(page.getByRole('cell', { name: 'Enabled', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Disabled', exact: true })).toBeVisible()
  await assertNoViolations(page)
})

const REVIEW_QUEUE_ITEMS = {
  items: [
    {
      storybook_id: 'sb-block',
      title: 'The Stormy Night',
      status: 'in_review',
      version: 1,
      screened: true,
      flagged_count: 2,
      // hard_block renders the danger "Hard block" pill; repaired stacks the
      // "Repaired" pill alongside it.
      summary: {
        count: 2,
        hard_block: true,
        soft_flag: false,
        repaired: true,
        reviewer_independent: true,
      },
      age_band: '8-11',
      waiting_since: '2026-07-20T08:00:00Z',
    },
    {
      storybook_id: 'sb-flag',
      title: 'The Quiet Meadow',
      status: 'in_review',
      version: 1,
      screened: true,
      flagged_count: 1,
      summary: {
        count: 1,
        hard_block: false,
        soft_flag: true,
        repaired: false,
        reviewer_independent: true,
      },
      age_band: '5-8',
      waiting_since: '2026-07-21T08:00:00Z',
    },
    {
      storybook_id: 'sb-unscreened',
      title: 'The Unscreened Tale',
      status: 'in_review',
      version: 1,
      // Renders the "Unscreened" pill (the not-screened severity badge).
      screened: false,
      flagged_count: 0,
      summary: null,
      age_band: null,
      waiting_since: null,
    },
  ],
}

test('the admin review queue (populated) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: REVIEW_QUEUE_ITEMS }))
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
  await page.goto('/admin')
  await expect(page.getByRole('link', { name: /The Stormy Night/ })).toBeVisible()
  await expect(page.getByText('Hard block')).toBeVisible()
  await assertNoViolations(page)
})

// --- /admin/review/:id review detail, with flags + alert states --------
//
// screened+flagged renders the flagged-passage cards and verdict-strip badges;
// a classifier_degraded story-level finding renders the degraded alert; the
// ending node's kind/valence renders the "Ending: success, positive" badge.

const REVIEW_DETAIL_SURFACE = {
  storybook_id: 'sb-detail',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: {
    count: 2,
    hard_block: true,
    soft_flag: false,
    repaired: true,
    reviewer_independent: false,
  },
  blob: {
    title: 'The Hidden Grove',
    start_node: 'n1',
    nodes: [
      {
        id: 'n1',
        body: 'A dark cave yawned ahead of the two friends.',
        choices: [{ id: 'c1', label: 'Step inside', target: 'n2' }],
      },
      {
        id: 'n2',
        body: 'Sunlight spilled across a hidden grove.',
        choices: [],
        is_ending: true,
        ending: { kind: 'success', valence: 'positive' },
      },
    ],
  },
  flagged_passages: [
    {
      node_id: 'n1',
      prose: 'A dark cave yawned ahead of the two friends.',
      findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'n1',
          verdict: 'flag',
          score: null,
          message: 'possibly scary for the younger band',
        },
      ],
    },
  ],
  story_level_findings: [
    {
      stage: 2,
      source: 'openai_moderation',
      category: 'classifier_degraded',
      node_id: null,
      verdict: 'advisory',
      score: null,
      message: 'classifier unavailable at screening time',
    },
  ],
}

async function seedReviewDetailScan(page: Page): Promise<void> {
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.route('**/api/v1/storybooks/sb-detail/review*', (route) =>
    route.fulfill({ json: REVIEW_DETAIL_SURFACE })
  )
  await page.route('**/api/v1/storybooks/sb-detail/versions/1/cover', (route) =>
    route.fulfill({ json: { cover_status: 'none', cover_url: null } })
  )
}

test('the admin review detail page (flagged) has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await seedReviewDetailScan(page)
  await page.goto('/admin/review/sb-detail')
  await expect(page.getByRole('heading', { name: 'The Hidden Grove' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Flagged passages' })).toBeVisible()
  await assertNoViolations(page)
})

test('the admin review detail approve-failure alert has no detectable accessibility violations', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await seedReviewDetailScan(page)
  // The approve POST fails, so the approve dialog renders its inline error
  // alert (role="alert", cyo-text-error): an error state reached via route-mock.
  await page.route('**/api/v1/storybooks/sb-detail/approve', (route) =>
    route.fulfill({ status: 500, json: { detail: 'boom' } })
  )
  await page.goto('/admin/review/sb-detail')
  await expect(page.getByRole('heading', { name: 'The Hidden Grove' })).toBeVisible()
  await page.getByRole('button', { name: 'Approve' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  // Scope to the dialog's own alert: the page also carries the standing
  // classifier_degraded alert, so a page-wide getByRole('alert') is ambiguous.
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText(
    'We could not approve this story'
  )
  await assertNoViolations(page)
})
