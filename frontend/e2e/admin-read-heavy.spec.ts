import { expect, test } from '@playwright/test'
import type { Route } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Backfill spec for three admin read-heavy surfaces that had no browser-level
 * coverage as of 2026-07-22: the audit log (AuditPage.tsx, filter + paging),
 * the admin library's lifecycle-status filter (AdminLibraryPage.tsx), and the
 * review version-compare panel (ReviewCompare.tsx, wired into
 * ReviewDetailPage.tsx via useVersionCompare.ts). All three are read-only or
 * read-mostly, so unlike the write-path specs elsewhere in e2e/ this file
 * leans on asserting the exact filtered/paged network request the UI fires,
 * per the mocked-tier convention, rather than only checking rendered rows.
 * The full behavioral matrix (loading/error/empty states, refetch races, the
 * 404-to-"unavailable" branch) lives in the component tests: AuditPage.test.tsx,
 * auditApi.test.ts, AdminLibraryPage.test.tsx, adminLibraryApi.test.ts, and
 * ReviewDetailPage.test.tsx's "version compare" describe block.
 */

/** Query params off a mocked request's URL, for asserting a filter/paging value fired. */
function queryParams(route: Route): URLSearchParams {
  return new URL(route.request().url()).searchParams
}

test.describe('audit log filter and paging (AuditPage)', () => {
  const PAGE_1 = {
    events: [
      {
        id: 'evt-1',
        occurred_at: '2026-07-01T12:00:00Z',
        actor_id: 'admin-1',
        actor_role: 'admin',
        entity_type: 'user',
        entity_id: 'user-2',
        event_type: 'user_managed',
        from_state: null,
        to_state: null,
        payload: { action: 'deactivate' },
      },
      {
        id: 'evt-2',
        occurred_at: '2026-07-01T11:00:00Z',
        actor_id: null,
        actor_role: 'system',
        entity_type: 'family',
        entity_id: 'fam-2',
        event_type: 'family_managed',
        from_state: null,
        to_state: null,
        payload: {},
      },
    ],
    limit: 50,
    offset: 0,
    has_more: true,
  }

  const FILTERED_PAGE = {
    events: [PAGE_1.events[0]],
    limit: 50,
    offset: 0,
    has_more: false,
  }

  const PAGE_2 = {
    events: [
      {
        id: 'evt-3',
        occurred_at: '2026-06-30T09:00:00Z',
        actor_id: 'admin-1',
        actor_role: 'admin',
        entity_type: 'storybook',
        entity_id: 's9',
        event_type: 'released',
        from_state: 'in_review',
        to_state: 'published',
        payload: {},
      },
    ],
    limit: 50,
    offset: 50,
    has_more: false,
  }

  test.beforeEach(async ({ context, page }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
  })

  test('applying the event-kind filter refetches GET /v1/admin/audit with kind set', async ({
    page,
  }) => {
    const kindsRequested: (string | null)[] = []
    await page.route('**/api/v1/admin/audit*', (route) => {
      const params = queryParams(route)
      kindsRequested.push(params.get('kind'))
      if (params.get('kind') === 'user_managed') {
        return route.fulfill({ json: FILTERED_PAGE })
      }
      return route.fulfill({ json: PAGE_1 })
    })

    await page.goto('/admin/audit')
    await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
    // Unfiltered: both the admin-attributed row and the system row render.
    await expect(page.getByRole('cell', { name: 'user: user-2' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'system' })).toBeVisible()

    await page.getByLabel('Filter by event kind').selectOption('user_managed')
    await page.getByRole('button', { name: 'Apply filters' }).click()

    // The filter form resets paging to offset 0 and refetches with kind set.
    await expect.poll(() => kindsRequested.at(-1)).toBe('user_managed')
    await expect(page.getByRole('cell', { name: 'system' })).toHaveCount(0)
    await expect(page.getByRole('cell', { name: 'user: user-2' })).toBeVisible()
  })

  test('next page fires the paged GET with offset=50', async ({ page }) => {
    const offsetsRequested: (string | null)[] = []
    await page.route('**/api/v1/admin/audit*', (route) => {
      const params = queryParams(route)
      offsetsRequested.push(params.get('offset'))
      if (params.get('offset') === '50') {
        return route.fulfill({ json: PAGE_2 })
      }
      return route.fulfill({ json: PAGE_1 })
    })

    await page.goto('/admin/audit')
    const nextPage = page.getByRole('button', { name: 'Next page' })
    await expect(nextPage).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Previous page' })).toBeDisabled()

    await nextPage.click()

    await expect.poll(() => offsetsRequested.at(-1)).toBe('50')
    await expect(page.getByRole('cell', { name: 'storybook: s9' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'in_review -> published' })).toBeVisible()
  })
})

test.describe('admin library lifecycle filter (AdminLibraryPage)', () => {
  const PUBLISHED = {
    storybook_id: 's1',
    title: 'The Lantern',
    status: 'published',
    version: 2,
    age_band: '6-8',
    family_id: 'fam-1',
    current_published_version: 2,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
  }

  const ARCHIVED = {
    storybook_id: 's2',
    title: 'Old Tale',
    status: 'archived',
    version: 1,
    age_band: null,
    family_id: 'fam-1',
    current_published_version: null,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: null,
  }

  test.beforeEach(async ({ context, page }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
  })

  test('selecting a lifecycle-status chip refetches GET /v1/admin/storybooks with status set', async ({
    page,
  }) => {
    const statusesRequested: (string | null)[] = []
    await page.route('**/api/v1/admin/storybooks*', (route) => {
      const params = queryParams(route)
      statusesRequested.push(params.get('status'))
      if (params.get('status') === 'archived') {
        return route.fulfill({ json: { items: [ARCHIVED] } })
      }
      return route.fulfill({ json: { items: [PUBLISHED, ARCHIVED] } })
    })

    await page.goto('/admin/library')
    await expect(page.getByRole('heading', { name: 'Story library' })).toBeVisible()
    // Unfiltered load passes no status param at all (adminLibraryApi.ts sends
    // `params: undefined`, not `params: { status: undefined }`).
    await expect.poll(() => statusesRequested.at(-1)).toBeNull()
    await expect(page.getByRole('link', { name: /The Lantern/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /Old Tale/ })).toBeVisible()

    await page.getByRole('button', { name: 'Archived' }).click()

    await expect.poll(() => statusesRequested.at(-1)).toBe('archived')
    await expect(page.getByRole('link', { name: /The Lantern/ })).toHaveCount(0)
    await expect(page.getByRole('link', { name: /Old Tale/ })).toBeVisible()
  })
})

test.describe('review version-compare panel (ReviewCompare via ReviewDetailPage)', () => {
  // Two-version fixture: version 2 changes n1's body, drops n3, and adds n4,
  // so the single compare exercises all three diff outcomes (changed, added,
  // removed) at once, mirroring ReviewDetailPage.test.tsx's compare fixture.
  const BASE_SURFACE = {
    storybook_id: 's1',
    version: 1,
    status: 'in_review',
    screened: true,
    summary: {
      count: 0,
      hard_block: false,
      soft_flag: false,
      repaired: false,
      reviewer_independent: true,
    },
    blob: {
      title: 'The Cave',
      start_node: 'n1',
      nodes: [
        { id: 'n1', body: 'Original opening.', choices: [{ label: 'Go on', target: 'n2' }] },
        { id: 'n2', body: 'Middle passage.', choices: [{ label: 'Finish', target: 'n3' }] },
        {
          id: 'n3',
          body: 'The old ending.',
          choices: [],
          is_ending: true,
          ending: { kind: 'success', valence: 'positive' },
        },
      ],
    },
    flagged_passages: [],
    story_level_findings: [],
  }

  const CURRENT_SURFACE = {
    ...BASE_SURFACE,
    version: 2,
    blob: {
      title: 'The Cave',
      start_node: 'n1',
      nodes: [
        { id: 'n1', body: 'Revised opening.', choices: [{ label: 'Go on', target: 'n2' }] },
        { id: 'n2', body: 'Middle passage.', choices: [{ label: 'Finish', target: 'n3' }] },
        {
          id: 'n4',
          body: 'A brand new twist.',
          choices: [],
          is_ending: true,
          ending: { kind: 'success', valence: 'positive' },
        },
      ],
    },
  }

  test.beforeEach(async ({ context, page }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
    // reviewApi.surface() calls GET /v1/storybooks/:id/review with no params
    // for the current version, and { version: N } for the compare fetch; the
    // Route glob matches either, so branch on the query param like
    // ReviewDetailPage.test.tsx's mockCompareRoutes.
    await page.route('**/api/v1/storybooks/s1/review*', (route) => {
      const version = queryParams(route).get('version')
      if (version === '1') return route.fulfill({ json: BASE_SURFACE })
      return route.fulfill({ json: CURRENT_SURFACE })
    })
  })

  test('opening the compare panel loads the previous version and renders the diff', async ({
    page,
  }) => {
    await page.goto('/admin/review/s1')
    await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()

    const toggle = page.getByRole('button', { name: 'Compare with version 1' })
    await expect(toggle).toBeVisible()
    await toggle.click()

    const panel = page.locator('.review-compare__panel')
    await expect(panel.getByText('1 passage added, 1 changed, 1 removed')).toBeVisible()
    await expect(panel.getByText('Added: passage n4')).toBeVisible()
    await expect(panel.getByText('Removed: passage n3')).toBeVisible()

    // The changed passage (n1) is collapsed behind <details>; opening it
    // shows both versions' bodies side by side.
    await panel.getByText('Passage n1 changed').click()
    await expect(
      panel.locator('.review-compare__before').getByText('Original opening.')
    ).toBeVisible()
    await expect(
      panel.locator('.review-compare__after').getByText('Revised opening.')
    ).toBeVisible()
  })
})
