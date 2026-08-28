/**
 * Mocked API surface for the usersim tier's mocked-backend walks.
 *
 * Extracted out of walk.spec.ts (task B3b) so a second mocked-tier spec file
 * (walk-a11y.spec.ts, the I7 axe-on-new-states walk) can reuse the exact same
 * route mocks instead of forking a second copy of them. walk.spec.ts is a
 * Playwright spec file (it calls `test()` at module scope for every
 * persona), so importing it directly from another spec file would re-run
 * those `test()` registrations a second time under a different project; this
 * module holds only the non-test mock-installation logic, safe to import
 * from any number of spec files.
 */
import type { BrowserContext, Page } from '@playwright/test'

import { mockMe } from '../../e2e/support/auth'
import { loadLanternStory } from '../../e2e/support/fixtures'
import { FAMILY_B_CANARY, GUARDIAN_ONLY_CANARY } from './invariants'
import type { PersonaId } from './personas'

// Mirrors route-manifest.ts's own PROFILE_ID/STORYBOOK_ID/STORYBOOK_VERSION
// (not exported from that module, so restated here) so mocked fixtures line
// up with the same profile/storybook the manifest and personas.ts assume.
export const PROFILE_ID = 'p1'
export const STORYBOOK_ID = 'sb-1'

/**
 * Generic catch-all for every unmocked `/api/v1/**` call, modelled directly
 * on e2e/a11y.spec.ts's `mockApiForScan`: a superset envelope covering every
 * list-shaped key this codebase's console pages read, defaulted empty, plus
 * every scalar/summary key seen in the existing mocked E2E tier's fixtures
 * (moderation.spec.ts, authoring-queue.spec.ts, provider-allowlist.spec.ts,
 * admin-audit.spec.ts, budgetApi.ts, progressApi.ts). Registered at the
 * CONTEXT level so every page-level override below (registered per persona,
 * always AFTER this call) wins regardless of registration order: Playwright
 * tries page-scoped routes before context-scoped ones.
 */
function genericEnvelope(): Record<string, unknown> {
  return {
    items: [],
    jobs: [],
    profiles: [],
    books: [],
    stories: [],
    requests: [],
    notifications: [],
    connections: [],
    grants: [],
    downloads: [],
    users: [],
    families: [],
    entries: [],
    events: [],
    children: [],
    rows: [],
    insights: [],
    recent_changes: [],
    suggestions: [],
    known_categories: [],
    default_min_verdict: 'flag',
    has_more: false,
    total: 0,
    limit: 50,
    offset: 0,
    count: 0,
    value: 0.2,
    quota: 0,
    spent_this_month: 0,
    remaining: 0,
    used_this_month: 0,
    min_decided_versions: 0,
    min_override_rate: 0,
    // ReadingHistoryView (src/client/types.gen.ts): { profile_id, books }.
    // `books` is already covered above; `profile_id` completes that shape.
    profile_id: PROFILE_ID,
    summary: {},
  }
}

/**
 * Install this persona's mocked API surface. Context-level catch-all first
 * (genericEnvelope), then page-level overrides for the specific endpoints
 * each persona's session actually drives, so a click into an unanticipated
 * corner of the console still gets a clean 200 instead of a 404/proxy error
 * that would trip I1 through logApiError (src/hooks/logApiError.ts).
 */
export async function installWalkMocks(
  context: BrowserContext,
  page: Page,
  personaId: PersonaId
): Promise<void> {
  await context.route('**/api/v1/**', (route) => route.fulfill({ json: genericEnvelope() }))

  // SSE notification stream: fulfilled with a real (empty) event-stream
  // response rather than aborted. a11y.spec.ts's mockApiForScan aborts this
  // request, which is fine for an axe scan that does not check console
  // output, but I1 (this tier's clean-console invariant) DOES: Chromium logs
  // its own "Failed to load resource: net::ERR_FAILED" console.error for an
  // aborted request, and notificationsStream.ts's onError handler adds a
  // second "notification stream error" console.error on top of that. A
  // fulfilled, immediately-closed text/event-stream response ends the fetch
  // cleanly (no error path, no reconnect loop) and is what a real backend's
  // connection close looks like on the wire.
  await page.route('**/api/v1/notifications/stream', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  )
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/device-downloads', (route) => route.fulfill({ json: [] }))

  if (personaId === 'kid') {
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({
        json: {
          profiles: [
            {
              id: PROFILE_ID,
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
              id: STORYBOOK_ID,
              title: 'The Lantern',
              version: 1,
              age_band: '6-8',
              tier: 1,
              reading_level_target: 2,
              node_count: 10,
              rating: null,
              progress: null,
            },
          ],
        },
      })
    )
    const lantern = loadLanternStory()
    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ status: 200, json: { state: null } })
      }
      return route.fulfill({ status: 200, json: { current_node: 'n_entrance', state_revision: 1 } })
    })
    return
  }

  // guardian/admin: /v1/me. The admin persona's own setupSession
  // (personas.ts) already mocks it with role: 'admin'; the guardian persona's
  // setupSession does not (seedGuardianSession only seeds the Supabase
  // session + onboarding), so it is mocked here instead. A page-level route
  // registered a second time simply replaces the first for that same page,
  // so calling this unconditionally for admin too is harmless.
  if (personaId === 'guardian') {
    await mockMe(page, { role: 'guardian' })
  }

  // Review queue: populated (not mockEmptyConsole's empty list) so the admin
  // console's review-queue row is a real, clickable a[href] leading into
  // /admin/review/:storybookId (AdminConsolePage.tsx / AdminLibraryPage.tsx),
  // giving the walk somewhere real to go instead of only nav-chrome links.
  // I5's GUARDIAN_ONLY_CANARY sits in the notification feed (adult-only data
  // both roles legitimately see); FAMILY_B_CANARY sits in the admin-only
  // cross-family roster (`/admin/families`), which neither the kid nor
  // guardian persona's session can ever reach through this app's own UI.
  // ReviewSurface for GET /v1/storybooks/{id}/review, reached by clicking
  // the review-queue row above into /admin/review/:storybookId (and, per
  // route-manifest.ts, potentially /guardian/review/:storybookId). Modelled
  // on guardian-review.spec.ts's own SURFACE fixture: a generic empty body
  // here would leave `blob` undefined, and ReviewDetailPage's
  // usePassageEdit hook dereferences `blob.nodes` unconditionally, crashing
  // the whole page into its error boundary (found by an early run of this
  // walk, before this mock existed).
  await page.route('**/api/v1/storybooks/*/review*', (route) =>
    route.fulfill({
      json: {
        storybook_id: STORYBOOK_ID,
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
          title: 'The Lantern',
          start_node: 'n1',
          nodes: [
            {
              id: 'n1',
              body: 'A dark cave yawned ahead.',
              choices: [{ label: 'Step inside', target: 'n2' }],
            },
            { id: 'n2', body: 'The path forked left and right.', choices: [] },
          ],
        },
        flagged_passages: [],
        story_level_findings: [],
      },
    })
  )
  await page.route('**/api/v1/review-queue', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            storybook_id: STORYBOOK_ID,
            title: 'The Lantern',
            status: 'in_review',
            version: 1,
            screened: true,
            flagged_count: 0,
            summary: {
              count: 0,
              hard_block: false,
              soft_flag: false,
              repaired: false,
              reviewer_independent: true,
            },
          },
        ],
      },
    })
  )
  await page.route('**/api/v1/notifications*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: 'n1',
            title: `Reminder: ${GUARDIAN_ONLY_CANARY}`,
            read: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        has_more: false,
      },
    })
  )
  if (personaId === 'admin') {
    await page.route('**/api/v1/admin/families', (route) =>
      route.fulfill({
        json: {
          families: [{ id: 'fam-b', name: FAMILY_B_CANARY, created_at: '2026-01-01T00:00:00Z' }],
        },
      })
    )
  }
}
