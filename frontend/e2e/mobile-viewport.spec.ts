import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedDeviceGrant, seedGuardianSession } from './support/auth'

/**
 * Task A12 (mobile-web readiness, Phase A): narrow-width horizontal-overflow
 * sweep, run under the `mobile-safari` project (npm run test:e2e:mobile).
 * Depends on A1/A7 (already landed), so this exercises the already-fixed
 * fluid layouts and no-breakpoint stylesheets at real phone widths.
 *
 * NOTE: Playwright device profiles do not emulate env(safe-area-inset-*).
 * This tier guards fluid-layout horizontal overflow only; notch/home-indicator
 * overlap (Task A8) needs a real device or the Capacitor build.
 *
 * Coverage:
 * - Covered (reachable with the auth/mocking helpers the surfaces' own specs
 *   already use, per landing.spec.ts / profiles.spec.ts / library.spec.ts /
 *   guardian-profiles.spec.ts / guardian-console.spec.ts):
 *   - landing (`/`, no auth)
 *   - kid profile picker (`/kids`, seedDeviceGrant + mocked /api/v1/profiles)
 *   - kid library (`/library/p1`, seedDeviceGrant + mocked profiles/library)
 *   - guardian profiles (`/guardian/profiles`, seedGuardianSession + mockMe
 *     + mocked /api/v1/profiles). The 320px case documents a genuine,
 *     pre-existing bug this sweep found (GuardianShell's header has no
 *     flex-wrap fallback and overflows at 320px, unlike its nav just below
 *     it); marked with `test.fail()` and a full explanation inline rather
 *     than silently dropped, since fixing guardian.css is out of scope for
 *     this test-infrastructure-only task.
 *   - admin console (`/admin`, seedGuardianSession + mockMe admin +
 *     mockEmptyConsole)
 * - Deferred (not covered here, to avoid inventing new brittle seeding
 *   infrastructure for a smoke sweep):
 *   - the reader (`/read/:profileId/:storybookId/:version`): needs the full
 *     Lantern Cave storybook fixture plus the player state machine wired up
 *     (see reader.spec.ts's loadLanternStory), which is materially heavier
 *     setup than a layout smoke check warrants.
 *   - guardian sub-pages beyond /guardian/profiles (books, assignments,
 *     connections, intake, story-requests) and admin sub-pages beyond the
 *     console home (users/kids/families/connections tabs, audit, provider
 *     allowlist, moderation dashboard/thresholds): each already has its own
 *     functional spec, and admin-touch-targets.spec.ts already asserts a
 *     phone-width 44px tap floor across all of them (Task A7); duplicating a
 *     document-overflow assertion on every one of them here would multiply
 *     this file's mock setup for marginal incremental signal beyond what A7
 *     and this file's console-home check already establish.
 */

const WIDTHS = [320, 375, 414]

async function assertNoHorizontalOverflow(page: import('@playwright/test').Page, width: number) {
  await page.setViewportSize({ width, height: 800 })
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  )
  expect(overflow, `overflow at ${width}px`).toBe(false)
}

for (const width of WIDTHS) {
  test(`landing has no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 })
    await page.goto('/')
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    )
    expect(overflow, `overflow at ${width}px`).toBe(false)
  })
}

const KID_PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Remy',
      age_band: '6-8',
      reading_level_cap: 3,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

test.describe('kid profile picker (/kids)', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: KID_PROFILES }))
  })

  for (const width of WIDTHS) {
    test(`has no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/kids')
      await expect(page.getByText('Remy')).toBeVisible()
      await assertNoHorizontalOverflow(page, width)
    })
  }
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

test.describe('kid library (/library/:profileId)', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: KID_PROFILES }))
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: LIBRARY_STORIES }))
  })

  for (const width of WIDTHS) {
    test(`has no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/library/p1')
      await expect(page.getByText('The Lantern')).toBeVisible()
      await assertNoHorizontalOverflow(page, width)
    })
  }
})

test.describe('guardian profiles (/guardian/profiles)', () => {
  test.beforeEach(async ({ context, page }) => {
    await seedGuardianSession(context)
    await mockMe(page)
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({
        json: {
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
          ],
        },
      })
    )
  })

  for (const width of WIDTHS) {
    test(`has no horizontal overflow at ${width}px`, async ({ page }) => {
      // #EDGE: real bug this sweep discovered, not a test bug: at 320px
      // `.guardian-shell__header` (guardian.css) overflows because it has no
      // flex-wrap fallback, unlike `.guardian-shell__nav` just below it in
      // the same file. The `justify-content: space-between` header packs the
      // brand text on the left against `.guardian-shell__header-actions`
      // (NotificationBell + Sign out button) on the right; at 320px the two
      // sides do not fit and `.guardian-shell__header-actions` is pushed to
      // right=342px in a 320px viewport instead of wrapping to a second row.
      // Fixing GuardianShell/guardian.css is out of scope for Task A12 (test
      // infrastructure only, three named files); flagging via test.fail so a
      // future header fix (a natural follow-up alongside A1's reader-chrome
      // wrap and A2's shell-height work) turns this into an "unexpectedly
      // passed" signal instead of silently staying green forever.
      // #VERIFY: file a follow-up task to add flex-wrap to
      // .guardian-shell__header (and re-check the brand/actions min-width)
      // then delete this test.fail() call.
      test.fail(
        width === 320,
        'known bug: GuardianShell header overflows at 320px, out of scope for A12'
      )
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/guardian/profiles')
      await expect(page.getByText('Reader A')).toBeVisible()
      await assertNoHorizontalOverflow(page, width)
    })
  }
})

test.describe('admin console (/admin)', () => {
  test.beforeEach(async ({ context, page }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
    await mockEmptyConsole(page)
  })

  for (const width of WIDTHS) {
    test(`has no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/admin')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await assertNoHorizontalOverflow(page, width)
    })
  }
})
