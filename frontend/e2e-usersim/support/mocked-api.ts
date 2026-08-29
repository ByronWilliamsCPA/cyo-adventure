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
 *
 * I5 NON-VACUITY (this is the part that is easy to break by accident, so
 * read it before editing any fixture below). invariants.ts's
 * `assertRoleFamilyIsolation` checks that a kid never renders
 * GUARDIAN_ONLY_CANARY or FAMILY_B_CANARY and that a guardian never renders
 * FAMILY_B_CANARY. An earlier version of this file served both canaries
 * ONLY from the `api/v1/notifications*` and `api/v1/admin/families` route
 * mocks, two
 * routes registered after the kid persona's early return and reachable in
 * practice only by admin, so the canary payload was withheld from exactly
 * the two personas I5 checks. All three assertions were therefore
 * unfalsifiable by construction: proven with a negative control (injecting
 * both canaries into those two handlers for the kid changed nothing, because
 * the kid never calls them) and a positive control (injecting
 * GUARDIAN_ONLY_CANARY into a rendered kid library title made I5 fire at
 * step 2). The machinery was sound; its sensitivity on this tier was zero.
 *
 * Two things below now keep that from recurring:
 *
 * 1. `withLeakBait` rides an adult-only field and a cross-family field along
 *    with EVERY JSON body this module serves to the kid and the guardian,
 *    including the context-level catch-all, in keys no component reads
 *    (`guardian_only_note`, `other_family`). So whatever route a kid or
 *    guardian page fetches, the response carries something that ring must
 *    not render, and any regression that surfaces it (a shared component
 *    reused across rings, a debug dump, a new field wired into a card) puts
 *    a canary in the DOM and trips I5. The two canary-bearing adult-only
 *    endpoints are also registered for every persona now, not just admin, so
 *    a kid page that STARTS calling one is caught too.
 * 2. `CanaryDeliveryLedger` records which canary literals were actually
 *    served during the walk, and `assertCanariesReachedPersona` fails the
 *    test if a persona finished its walk without ever receiving the canaries
 *    I5 checks it for. That is the mocked-tier counterpart of
 *    real-canaries.ts's `proveRealCanariesExist`: it makes a vacuous I5 LOUD
 *    instead of green, which is the only durable defence, since any future
 *    fixture edit can otherwise quietly re-hide the canary.
 */
import { expect, type BrowserContext, type Page, type Route } from '@playwright/test'

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
 * Adult-only and cross-family values that ride along with every JSON body
 * served to a ring that must not render them. The KEY names are deliberately
 * ones no component in this app reads, so a green walk means "the UI did not
 * surface data outside its ring", not "the data was never there" (which is
 * the exact vacuity documented in this module's header).
 *
 * `guardian_only_note` stands for adult-only data (the guardian notification
 * feed is its natural home); `other_family` stands for another family's row,
 * which ADR-016 places in the admin ring only.
 */
function withLeakBait(
  personaId: PersonaId,
  body: Record<string, unknown>
): Record<string, unknown> {
  if (personaId === 'admin') {
    // Admin legitimately sees both rings' data, and assertRoleFamilyIsolation
    // deliberately checks nothing for it, so bait here would assert nothing.
    return body
  }
  const baited: Record<string, unknown> = {
    ...body,
    other_family: { id: 'fam-b', name: FAMILY_B_CANARY },
  }
  if (personaId === 'kid') {
    // A guardian may render guardian-only data; a kid may not.
    baited.guardian_only_note = GUARDIAN_ONLY_CANARY
  }
  return baited
}

/**
 * Which canary literals actually reached the browser during a walk.
 *
 * The mocked-tier counterpart of real-canaries.ts's `proveRealCanariesExist`:
 * that helper reads the canary rows out of the real database before the real
 * walk starts and fails when they are absent, because "the kid never saw it"
 * is worthless if it was never there to see. On this tier the fixtures ARE
 * the database, so the equivalent proof is recording what the fixtures
 * actually served.
 */
export interface CanaryDeliveryLedger {
  /** Canary literals observed in a body this module fulfilled during the walk. */
  delivered: Set<string>
}

export function createCanaryDeliveryLedger(): CanaryDeliveryLedger {
  return { delivered: new Set<string>() }
}

/**
 * Fulfill with a JSON body, recording any I5 canary the body carries.
 *
 * Every JSON fulfilment in this module goes through here, so the ledger
 * cannot drift from what was served: a fixture that stops carrying a canary
 * stops recording it, and `assertCanariesReachedPersona` turns that into a
 * failure rather than a silently weaker check.
 */
function fulfillJson(
  route: Route,
  body: Record<string, unknown>,
  ledger?: CanaryDeliveryLedger
): Promise<void> {
  if (ledger) {
    const serialized = JSON.stringify(body)
    for (const canary of [GUARDIAN_ONLY_CANARY, FAMILY_B_CANARY]) {
      if (serialized.includes(canary)) {
        ledger.delivered.add(canary)
      }
    }
  }
  return route.fulfill({ json: body })
}

/**
 * Fail the test when a persona's walk finished without ever being served the
 * canaries invariants.ts's I5 checks it for.
 *
 * #CRITICAL: data-integrity: this is the guard that keeps I5 falsifiable. I5
 * is a "this string must not appear" assertion, and such an assertion passes
 * for two completely different reasons: the boundary held, or the string was
 * never in play. Only this call distinguishes them. Deleting it, or letting a
 * fixture edit stop serving a canary, returns the tier to reporting a green
 * three-ring result it never actually tested.
 * #VERIFY: the mutation that must stay red is removing the canaries from the
 * bodies a persona fetches; this must fail with the message below, not pass.
 */
export function assertCanariesReachedPersona(
  ledger: CanaryDeliveryLedger,
  personaId: PersonaId
): void {
  // Mirrors assertRoleFamilyIsolation's own per-persona logic: kid is checked
  // for both canaries, guardian for the cross-family one, admin for neither
  // (it sits at the top of ADR-016's ring hierarchy, so nothing here is a
  // violation for it and there is correspondingly nothing to prove).
  const required =
    personaId === 'kid'
      ? [GUARDIAN_ONLY_CANARY, FAMILY_B_CANARY]
      : personaId === 'guardian'
        ? [FAMILY_B_CANARY]
        : []
  const missing = required.filter((canary) => !ledger.delivered.has(canary))
  expect(
    missing,
    `usersim/${personaId}: I5 was vacuous for this walk. The canaries it checks for ` +
      `(${missing.join(', ')}) were never served to the browser, so its "the ring boundary held" ` +
      'verdict was a check that could not fail. Restore the canary-bearing fixtures in ' +
      "mocked-api.ts (see withLeakBait and this module's header comment); do not delete this " +
      'assertion to make the walk green.'
  ).toEqual([])
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
  personaId: PersonaId,
  ledger?: CanaryDeliveryLedger
): Promise<void> {
  await context.route('**/api/v1/**', (route) =>
    fulfillJson(route, withLeakBait(personaId, genericEnvelope()), ledger)
  )

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
  //
  // Not routed through fulfillJson: this is not a JSON body, and it carries
  // no canary by design (an event-stream body is not rendered as data).
  await page.route('**/api/v1/notifications/stream', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  )
  // Bare arrays, so withLeakBait (which adds object keys) does not apply:
  // baiting a list would mean pushing a canary-bearing ROW into a collection
  // the app legitimately renders, which would fire I5 on correct behaviour.
  await page.route('**/api/v1/device-grants', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/device-downloads', (route) => route.fulfill({ json: [] }))

  // The two canary-bearing adult-only endpoints, registered for EVERY
  // persona rather than only for the rings that legitimately call them. A
  // kid or guardian page that starts fetching adult-only or cross-family
  // data is itself the ADR-016 regression I5 exists to catch, and it can
  // only be caught if the mocked universe answers that call with the real
  // payload instead of the empty catch-all envelope. Registering them here
  // costs nothing for a persona that never calls them.
  //
  // GUARDIAN_ONLY_CANARY sits in the notification feed (adult-only data both
  // adult rings legitimately see); FAMILY_B_CANARY sits in the admin-only
  // cross-family roster.
  await page.route('**/api/v1/notifications*', (route) =>
    fulfillJson(
      route,
      withLeakBait(personaId, {
        items: [
          {
            id: 'n1',
            title: `Reminder: ${GUARDIAN_ONLY_CANARY}`,
            read: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        has_more: false,
      }),
      ledger
    )
  )
  await page.route('**/api/v1/admin/families', (route) =>
    fulfillJson(
      route,
      withLeakBait(personaId, {
        families: [{ id: 'fam-b', name: FAMILY_B_CANARY, created_at: '2026-01-01T00:00:00Z' }],
      }),
      ledger
    )
  )

  if (personaId === 'kid') {
    await page.route('**/api/v1/profiles', (route) =>
      fulfillJson(
        route,
        withLeakBait(personaId, {
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
        }),
        ledger
      )
    )
    await page.route('**/api/v1/library*', (route) =>
      fulfillJson(
        route,
        withLeakBait(personaId, {
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
        }),
        ledger
      )
    )
    const lantern = loadLanternStory()
    // The storybook blob is parsed by the player engine, not rendered as a
    // generic envelope, so it is served unbaited: an unexpected top-level key
    // in a story document is a different (schema) question from a ring leak,
    // and the kid's other three routes above already carry the bait.
    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        return fulfillJson(route, withLeakBait(personaId, { state: null }), ledger)
      }
      return fulfillJson(
        route,
        withLeakBait(personaId, { current_node: 'n_entrance', state_revision: 1 }),
        ledger
      )
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
  // ReviewSurface for GET /v1/storybooks/{id}/review, reached by clicking
  // the review-queue row above into /admin/review/:storybookId (and, per
  // route-manifest.ts, potentially /guardian/review/:storybookId). Modelled
  // on guardian-review.spec.ts's own SURFACE fixture: a generic empty body
  // here would leave `blob` undefined, and ReviewDetailPage's
  // usePassageEdit hook dereferences `blob.nodes` unconditionally, crashing
  // the whole page into its error boundary (found by an early run of this
  // walk, before this mock existed).
  await page.route('**/api/v1/storybooks/*/review*', (route) =>
    fulfillJson(
      route,
      withLeakBait(personaId, {
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
      }),
      ledger
    )
  )
  await page.route('**/api/v1/review-queue', (route) =>
    fulfillJson(
      route,
      withLeakBait(personaId, {
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
      }),
      ledger
    )
  )
}
