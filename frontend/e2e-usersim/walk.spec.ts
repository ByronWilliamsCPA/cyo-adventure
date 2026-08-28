/**
 * Leg A: the seeded random walk. One `test()` per persona (kid, guardian,
 * admin). Each walk seeds that persona's session (personas.ts), mocks the
 * API surface it can reach, then repeatedly picks a visible in-app link at
 * random (via the seeded PRNG, prng.ts) and clicks it, asserting I1-I5 at
 * every state and I6 after an occasional random back/forward step.
 *
 * This is a genuine DOM-click-driven walk, not a permutation of
 * route-manifest.ts: the manifest is a sync-checked reference for which
 * paths exist and which persona's session should reach them (and the
 * source of this tier's recognised terminals via personas.ts), not the
 * literal walk sequence. See
 * docs/testing/user-side-testing-module-proposal-2026-08-27.md, which is
 * explicit that a random walk earns its keep only over the live,
 * non-enumerable click graph.
 *
 * Determinism is the design centre: USERSIM_SEED (prng.ts) fixes the walk.
 * The same seed must reproduce the same visited-URL sequence; a different
 * seed should (in general) diverge. Every invariant failure embeds the
 * seed in its thrown message (invariants.ts's replayHint), not only in a
 * log line, so a CI reader can replay a failure from the assertion text
 * alone.
 */
import { expect, test } from '@playwright/test'

import { mockMe } from '../e2e/support/auth'
import { loadLanternStory } from '../e2e/support/fixtures'
import { assertNoHorizontalOverflow } from '../e2e/support/responsiveChecks'
import {
  assertHistoryStepInvariants,
  assertStepInvariants,
  createConsoleWatcher,
  FAMILY_B_CANARY,
  GUARDIAN_ONLY_CANARY,
  LOADING_RESOLUTION_BUDGET_MS,
  LOADING_SELECTOR,
  type StepContext,
} from './support/invariants'
import { createFindingsSink } from './support/findings'
import { PERSONAS, type Persona, type PersonaId } from './support/personas'
import { createRng, RESOLVED_SEED } from './support/prng'

/** Which usersim workflow produced these findings (findings.ts's UsersimFinding.workflow). */
const WORKFLOW = 'usersim-walk'

/** How many steps each persona's walk takes. Bounded for CI speed; large enough to reach several distinct states. */
const STEP_BUDGET = 10

/** Chance, per step, of taking a random back/forward step (I6) instead of clicking forward. */
const HISTORY_STEP_PROBABILITY = 0.2

/**
 * Movement selector: an in-app, same-origin link. Deliberately narrower than
 * invariants.ts's INTERACTIVE_SELECTOR (I2): only a real anchor with a
 * relative href is safe to click blindly, since every such link is a
 * React Router route the walk can assert against, never an external site, a
 * mailto:, or a sign-out control (those are buttons, not `a[href]`, in every
 * shell this app renders -- see GuardianShell/AdminShell/KidNav).
 */
const NAV_LINK_SELECTOR = 'a[href^="/"]:visible'

/**
 * #ASSUME: timing-dependencies: every route transition in this app is a
 * client-side React Router navigation, not a real browser navigation, so
 * `page.waitForLoadState('domcontentloaded')` resolves immediately and does
 * NOT wait for the destination page to finish rendering. Two settling
 * strategies were tried and rejected before the one below:
 *
 * 1. `page.waitForLoadState('domcontentloaded')` -- a no-op for a client-side
 *    transition, so it does not wait at all (see above).
 * 2. `page.waitForLoadState('networkidle')` -- waits for the mocked API calls
 *    a new route fires to settle, which sounds right, but this app keeps a
 *    persistent SSE connection open on every guardian/admin page
 *    (notifications/stream, mocked here as a fulfilled, never-closing
 *    text/event-stream body). Playwright's own docs call this out:
 *    'networkidle' never resolves against a page with an open streaming
 *    connection. A guardian-persona run of this walk hit exactly that: the
 *    call hung for the full 30s test timeout on the very first post-click
 *    wait, every single run, on a page the kid persona (no SSE consumer)
 *    never visited.
 *
 * The fix below needs no network signal at all. `target.waitFor({state:
 * 'detached'})` at the click site (see below) is the one thing that
 * observably distinguishes "the click navigated" from "the click's target
 * is still on screen": a React Router v7 `<Link>` navigation is wrapped in
 * startTransition, so `page.url()` can already report the destination while
 * the SOURCE page's DOM is still fully mounted and interactive; an early run
 * of this walk read hrefs from that stale, still-mounted page and re-clicked
 * a link whose destination had no matching outgoing link once the deferred
 * transition finally committed underneath it, hanging on a target that could
 * never reattach. Waiting for the clicked element itself to detach is a
 * direct DOM-observed signal of that commit, not a proxy for it.
 * settleAfterNavigation below then covers the remaining case (the new
 * page's own initial data has not yet rendered) by reusing I3's own
 * loading-indicator poll: a DOM-state wait, not a network-state one, so it
 * is immune to the same open-connection problem.
 * #VERIFY: the seed-replay verification (this task's requirement 4)
 * demonstrates both fixes together: the same seed reproduces an identical
 * visited-URL sequence for every persona, kid included, across repeated
 * runs.
 */
async function settleAfterNavigation(page: Parameters<Persona['setupSession']>[1]): Promise<void> {
  // Best-effort only: this is not itself an invariant check (a loading
  // indicator that is still present after the budget is I3's job to catch,
  // on the very next assertStepInvariants call), just a settle point before
  // this step's own hrefs are read.
  await expect(page.locator(LOADING_SELECTOR))
    .toHaveCount(0, { timeout: LOADING_RESOLUTION_BUDGET_MS })
    .catch(() => undefined)
}

// Mirrors route-manifest.ts's own PROFILE_ID/STORYBOOK_ID/STORYBOOK_VERSION
// (not exported from that module, so restated here) so mocked fixtures line
// up with the same profile/storybook the manifest and personas.ts assume.
const PROFILE_ID = 'p1'
const STORYBOOK_ID = 'sb-1'

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
async function installWalkMocks(
  context: Parameters<Persona['setupSession']>[0],
  page: Parameters<Persona['setupSession']>[1],
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

/** One entry in a visited-sequence, for the seed-replay verification. */
interface VisitedStep {
  step: number
  url: string
}

async function walkPersona(
  persona: Persona,
  page: Parameters<Persona['setupSession']>[1],
  context: Parameters<Persona['setupSession']>[0]
): Promise<VisitedStep[]> {
  const rng = createRng(RESOLVED_SEED)
  const visited: VisitedStep[] = []
  const findingsLines: string[] = []
  const sink = createFindingsSink((line) => findingsLines.push(line))

  // Attach BEFORE the first navigation (I1's requirement), so console
  // activity from the initial load is not missed.
  const watcher = createConsoleWatcher(page)

  await persona.setupSession(context, page)
  await installWalkMocks(context, page, persona.id)

  await page.goto(persona.entryPath)
  await settleAfterNavigation(page)
  visited.push({ step: 0, url: page.url() })

  for (let step = 1; step <= STEP_BUDGET; step++) {
    const ctx: StepContext = {
      page,
      persona: persona.id,
      seed: RESOLVED_SEED,
      step,
      sink,
      workflow: WORKFLOW,
    }

    if (visited.length > 1 && rng.next() < HISTORY_STEP_PROBABILITY) {
      // I6: a random back or forward step must still land in a state
      // satisfying I1-I4.
      if (rng.next() < 0.5) {
        await page.goBack()
      } else {
        await page.goForward()
      }
      await settleAfterNavigation(page)
      visited.push({ step, url: page.url() })
      await assertHistoryStepInvariants(ctx, watcher, assertNoHorizontalOverflow)
      continue
    }

    await assertStepInvariants(ctx, watcher, assertNoHorizontalOverflow)

    // Read every candidate link's href in one round trip, then pick and
    // click by that href value rather than by positional index. An early
    // run of this walk hit a real race with index-based selection: a
    // background fetch settling between the count() and the click() calls
    // (KidNav's progress fetch, on the kid persona) could shift what sat at
    // a given index between the two round trips, leaving `nth(idx)`
    // pointing at a stale/detached node and the click hanging until
    // Playwright's timeout. Re-resolving by href at click time always finds
    // whatever currently represents that destination, so a same-href
    // re-render in between is harmless.
    const hrefs = await page
      .locator(NAV_LINK_SELECTOR)
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('href')))
    const validHrefs = hrefs.filter((href): href is string => Boolean(href))
    if (validHrefs.length === 0) {
      // assertStepInvariants already confirmed this is a recognised
      // terminal (I2), not a dead end; nothing left to click.
      break
    }
    const chosenHref = rng.pick(validHrefs)
    const target = page.locator(`a[href="${chosenHref}"]:visible`).first()
    await target.click()
    // #ASSUME: timing-dependencies: React Router v7 wraps a <Link> navigation
    // in startTransition, so `location.pathname`/`page.url()` can update
    // BEFORE the outgoing page's own DOM actually unmounts: a run of this
    // walk caught step N+1 reading hrefs from step N's stale, still-mounted
    // page (page.url() already showed the destination) and re-clicking a
    // link whose destination page has no matching outgoing link once the
    // deferred transition finally committed underneath it, which then hung
    // Playwright's actionability wait on a permanently-detached element
    // until timeout. Waiting for the CLICKED element itself to detach is a
    // direct, app-DOM-observed signal that the transition has actually
    // committed, unlike relying on the URL or on network activity alone.
    // Bounded and non-fatal: a click into a shared shell nav (guardian/admin's
    // GuardianShell/AdminShell wrap an Outlet, so the sidebar's own links are
    // outside it and persist across a route change) never detaches at all,
    // and a link to the page already on screen (a same-route link) likewise
    // never detaches, so this must not fail the step; settleAfterNavigation
    // below still runs either way and is what actually gates the next
    // iteration's read. 1s (not the 8s LOADING_RESOLUTION_BUDGET_MS used
    // elsewhere) keeps a non-detaching step cheap: this fires on most of a
    // guardian/admin walk's steps (a shared nav is most of what there is to
    // click there), and even a doubled per-project timeout (playwright.
    // config.ts's `usersim` project) could not absorb every step paying an
    // 8s toll that never resolves to anything.
    // #VERIFY: the seed-replay verification (this task's requirement 4)
    // demonstrates this closes the race: the same seed now reproduces an
    // identical visited-URL sequence across repeated runs.
    await target.waitFor({ state: 'detached', timeout: 1_000 }).catch(() => undefined)
    await settleAfterNavigation(page)
    visited.push({ step, url: page.url() })
  }

  watcher.dispose()

  // The seed must reach the failure OUTPUT, not just a log line (task
  // brief); this console.log is the seed-replay verification's evidence for
  // a PASSING run; a failing run's evidence is invariants.ts's thrown
  // message, which already embeds the same seed.
  console.log(
    `[usersim] persona=${persona.id} seed=${RESOLVED_SEED} visited=${JSON.stringify(visited.map((v) => v.url))}`
  )
  for (const line of findingsLines) {
    console.log(`[usersim-finding] ${line}`)
  }

  return visited
}

test.afterEach(async ({ page }, testInfo) => {
  // Load-bearing for invariants.ts's recordAndThrow comment: a failure's
  // JSONL row (seed, step, url) and this screenshot are joinable by seed +
  // step, since both are embedded in the thrown assertion message that
  // Playwright's own report already carries alongside this attachment.
  if (testInfo.status !== testInfo.expectedStatus) {
    const path = testInfo.outputPath('failure.png')
    await page.screenshot({ path }).catch(() => undefined)
  }
})

for (const persona of PERSONAS) {
  test(persona.id, async ({ page, context }) => {
    await walkPersona(persona, page, context)
  })
}
