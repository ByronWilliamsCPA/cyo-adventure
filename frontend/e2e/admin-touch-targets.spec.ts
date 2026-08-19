import { expect, test, type Page } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Mocked-tier E2E regression for Task A7 (mobile-web readiness, Phase A):
 * every action button in the six migrated admin CRUD files (FamiliesTab,
 * KidsTab, ConnectionsTab, UsersTab, ProviderAllowlistPage, AuditPage) plus
 * the trigger/submit buttons on the two moderation pages now renders through
 * the `@ds` `Button` component, which guarantees a 44px minimum height
 * (WCAG 2.5.5). This spec asserts that floor holds at a phone viewport.
 *
 * The assertion is scoped per-container rather than page-wide. The
 * UserManagementPage.tsx tab-nav switcher (the "Users / Kids / Families /
 * Family connections" buttons) was migrated to the `@ds` `Button` in a later
 * follow-up, so it now clears the 44px floor too; scoping to `main section`
 * (the tab-content wrapper each migrated component renders into) is therefore
 * defensive rather than required. It keeps this regression pinned to the
 * buttons Task A7 migrated, independent of chrome outside the content area.
 */

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active',
  guardian_count: 2,
  kid_count: 1,
  created_at: '2026-01-01T00:00:00Z',
}

const PROFILE_A = {
  id: 'profile-a',
  family_id: 'fam-a',
  display_name: 'Kid A',
  age_band: '5-8',
  reading_level_cap: 2,
  avatar: null,
  tts_enabled: false,
  has_pin: true,
  status: 'active',
}

const USER_A = {
  id: 'user-1',
  family_id: 'fam-a',
  email: 'guardian@example.com',
  role: 'guardian',
  is_admin: false,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
}

const CONNECTION_A = {
  id: 'conn-1',
  family_id: 'fam-a',
  family_name: 'Family A',
  connected_family_id: 'fam-b',
  connected_family_name: 'Family B',
}

test.beforeEach(async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
})

/**
 * Asserts every visible button within `scopeSelector` meets the WCAG 2.5.5
 * 44x44 CSS-px tap floor on BOTH axes (height and width). Fails loudly
 * (count > 0) if the scope selector matched nothing, so a route/selector typo
 * cannot silently pass an empty check.
 */
async function expectAllButtonsMeetTapFloor(page: Page, scopeSelector: string) {
  const buttons = page.locator(`${scopeSelector} button:visible`)
  const count = await buttons.count()
  expect(count, `expected at least one visible button in "${scopeSelector}"`).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    const box = await buttons.nth(i).boundingBox()
    expect(box?.height ?? 0, `button ${i} in "${scopeSelector}" height`).toBeGreaterThanOrEqual(44)
    expect(box?.width ?? 0, `button ${i} in "${scopeSelector}" width`).toBeGreaterThanOrEqual(44)
  }
}

test.describe('admin CRUD tab touch targets (Task A7)', () => {
  test('user management tabs (Users/Kids/Families/Connections) meet the 44px floor', async ({
    page,
  }) => {
    await page.route('**/api/v1/admin/users*', (route) =>
      route.fulfill({ json: { users: [USER_A] } })
    )
    await page.route('**/api/v1/admin/profiles*', (route) =>
      route.fulfill({ json: { profiles: [PROFILE_A] } })
    )
    await page.route('**/api/v1/admin/families', (route) =>
      route.fulfill({ json: { families: [FAMILY_A] } })
    )
    await page.route('**/api/v1/admin/family-connections', (route) =>
      route.fulfill({ json: { connections: [CONNECTION_A] } })
    )

    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { name: 'User management' })).toBeVisible()

    // Users tab is the default.
    await expectAllButtonsMeetTapFloor(page, 'main section')

    await page.getByRole('button', { name: 'Kids' }).click()
    await expectAllButtonsMeetTapFloor(page, 'main section')

    await page.getByRole('button', { name: 'Families' }).click()
    await expectAllButtonsMeetTapFloor(page, 'main section')

    await page.getByRole('button', { name: 'Family connections' }).click()
    await expectAllButtonsMeetTapFloor(page, 'main section')
  })

  test('provider allowlist page buttons meet the 44px floor', async ({ page }) => {
    await page.route('**/api/v1/admin/provider-allowlist', (route) =>
      route.fulfill({
        json: {
          rows: [
            {
              id: 'a1',
              provider: 'modal',
              model_id: 'google/gemma-4-26b-a4b-it',
              enabled: true,
              display_name: null,
            },
          ],
        },
      })
    )

    await page.goto('/admin/provider-allowlist')
    await expect(page.getByRole('heading', { name: 'Provider allowlist' })).toBeVisible()
    await expectAllButtonsMeetTapFloor(page, 'main')
  })

  test('audit page buttons meet the 44px floor', async ({ page }) => {
    await page.route('**/api/v1/admin/audit*', (route) =>
      route.fulfill({
        json: {
          events: [
            {
              id: 'e1',
              occurred_at: '2026-07-01T00:00:00Z',
              actor_id: 'user-1',
              actor_role: 'admin',
              entity_type: 'story_request',
              entity_id: 'req-1',
              event_type: 'request_created',
              from_state: null,
              to_state: 'pending',
              payload: {},
            },
          ],
          limit: 50,
          offset: 0,
          has_more: false,
        },
      })
    )

    await page.goto('/admin/audit')
    await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
    await expectAllButtonsMeetTapFloor(page, 'main')
  })

  test('moderation thresholds trigger buttons meet the 44px floor', async ({ page }) => {
    await page.route('**/api/v1/admin/moderation-thresholds', (route) =>
      route.fulfill({
        json: {
          default_min_verdict: 'flag',
          rows: [{ age_band: '5-8', category: 'violence', min_verdict: 'block', min_score: null }],
          known_categories: ['violence', 'language'],
        },
      })
    )
    await page.route('**/api/v1/admin/moderation/noise-floor', (route) =>
      route.fulfill({ json: { value: 0.2 } })
    )

    await page.goto('/admin/moderation-thresholds')
    await expect(page.getByRole('heading', { name: 'Moderation thresholds' })).toBeVisible()
    await expectAllButtonsMeetTapFloor(page, 'main')
  })

  test('moderation dashboard trigger button meets the 44px floor', async ({ page }) => {
    await page.route('**/api/v1/admin/moderation/dashboard', (route) =>
      route.fulfill({ json: { insights: [], recent_changes: [] } })
    )
    await page.route('**/api/v1/admin/moderation/suggestions', (route) =>
      route.fulfill({
        json: {
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
        },
      })
    )

    await page.goto('/admin/moderation-dashboard')
    await expect(page.getByRole('heading', { name: 'Moderation dashboard' })).toBeVisible()
    await expectAllButtonsMeetTapFloor(page, 'main')
  })
})
