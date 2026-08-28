import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedDeviceGrant, seedGuardianSession } from './auth'
import { loadLanternStory } from './fixtures'

/**
 * The seven per-page structural checks shared by responsive.spec.ts (one
 * chromium run per breakpoint: desktop/tablet/mobile viewport, via
 * `test.use({ viewport })`) and cross-device.spec.ts (one run per real
 * device/browser project, at that project's own native viewport/UA/engine).
 * Declared as a function rather than at each file's top level so the same
 * `test(...)` bodies run under both callers without duplicating the
 * mocks -- Playwright supports calling `test()` from inside a shared
 * function, as long as it happens during the synchronous test-collection
 * pass (i.e. call this directly inside a describe/file body, never inside
 * an async callback).
 */
/**
 * Zero page-level horizontal overflow, for a given breakpoint/label. Hoisted
 * to module scope (out of defineResponsiveChecks) and exported so the usersim
 * walk tier's I4 invariant (frontend/e2e-usersim/support/invariants.ts) can
 * reuse this exact check instead of duplicating the overflow logic; every
 * caller inside this file goes through defineResponsiveChecks() unchanged.
 */
export async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(
    scrollWidth - clientWidth,
    `${label}: page should not scroll horizontally`
  ).toBeLessThanOrEqual(1)
}

export function defineResponsiveChecks(): void {
  test('landing page has no horizontal overflow', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /Grown-ups/ })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'landing')
  })

  test('kid picker has no horizontal overflow', async ({ page, context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({
        json: {
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
        },
      })
    )
    await page.goto('/kids')
    await expect(page.getByRole('heading', { name: "Who's reading?" })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'kid-picker')
  })

  test('library page has no horizontal overflow, including a single-book shelf', async ({
    page,
    context,
  }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'p1')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({
        json: {
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
        },
      })
    )
    await page.route('**/api/v1/library*', (route) =>
      route.fulfill({
        json: {
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
              progress: {
                current_node: 'n2',
                nodes_visited: 5,
                updated_at: '2026-07-01T10:00:00Z',
              },
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
        },
      })
    )
    await page.goto('/library/p1')
    await expect(page.getByRole('heading', { name: 'My Books' })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'library')

    // Regression guard for the auto-fill/auto-fit shelf bug: the grid's
    // cells (a lone book plus the "Ask for a new story" end-cap tile) must
    // collectively span the shelf's own width, not leave a
    // reserved-but-empty track beside them. Asserted via the edges: the
    // first cell starts at the shelf's left edge and the last cell ends at
    // its right edge, which holds whether the two cells share one row
    // (tablet/desktop) or stack (phone).
    const shelf = page.locator('.library__shelf')
    const cells = shelf.locator('> li')
    const first = cells.first()
    const last = cells.last()
    const [shelfBox, firstBox, lastBox] = await Promise.all([
      shelf.boundingBox(),
      first.boundingBox(),
      last.boundingBox(),
    ])
    if (shelfBox && firstBox && lastBox) {
      expect(
        Math.abs(firstBox.x - shelfBox.x),
        'the first shelf cell should start at the shelf left edge'
      ).toBeLessThan(2)
      expect(
        lastBox.x + lastBox.width,
        'the last shelf cell should reach the shelf right edge'
      ).toBeGreaterThan(shelfBox.x + shelfBox.width * 0.98 - 1)
    }
  })

  test('reader page has no horizontal overflow', async ({ page, context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-a')
    })
    await seedDeviceGrant(context)
    const lantern = loadLanternStory()
    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ status: 404, json: { error: 'not found' } })
      }
      return route.fulfill({ status: 200, json: { current_node: 'n_entrance', state_revision: 1 } })
    })
    await page.goto('/read/child-a/s_lantern_cave/1')
    await expect(page.getByTestId('reader')).toBeVisible()
    await assertNoHorizontalOverflow(page, 'reader')
  })

  test('guardian console has no horizontal overflow', async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'guardian' })
    await mockEmptyConsole(page)
    await page.goto('/guardian')
    await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'guardian-console')
  })

  test('admin console has no horizontal overflow', async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
    await mockEmptyConsole(page)
    await page.clock.install({ time: new Date('2026-01-01T12:00:00Z') })
    await page.goto('/admin')
    await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'admin-console')
  })

  test('admin user-management table has no horizontal overflow', async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
    await page.route('**/api/v1/admin/families', (route) =>
      route.fulfill({
        json: {
          families: [
            { id: 'fam-1', name: 'The Example Family', created_at: '2026-01-01T00:00:00Z' },
          ],
        },
      })
    )
    await page.route('**/api/v1/admin/profiles*', (route) =>
      route.fulfill({ json: { profiles: [] } })
    )
    await page.route('**/api/v1/admin/family-connections', (route) =>
      route.fulfill({ json: { connections: [] } })
    )
    await page.route('**/api/v1/admin/users*', (route) =>
      route.fulfill({
        json: {
          users: [
            {
              id: 'u1',
              email: 'someone.with.a.rather.long.email@example.com',
              family_id: 'fam-1',
              role: 'guardian',
              is_admin: false,
              status: 'active',
            },
            {
              id: 'u2',
              email: 'admin.person@example.com',
              family_id: 'fam-1',
              role: 'admin',
              is_admin: true,
              status: 'active',
            },
          ],
        },
      })
    )
    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: 'Guardians & admins' })).toBeVisible()
    await assertNoHorizontalOverflow(page, 'admin-users-table')
  })
}
