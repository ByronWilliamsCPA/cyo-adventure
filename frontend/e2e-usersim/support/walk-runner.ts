/**
 * Shared walk loop for the usersim tier (task B3a extraction).
 *
 * This is the one place the seeded-random-walk algorithm lives. It was
 * originally inline in walk.spec.ts (the mocked tier); task B3a pulled it
 * out into this module, parameterized by session setup / mock installation
 * / I5 canaries / workflow name, so the real-tier walk (walk-real.spec.ts)
 * can reuse the exact same click-and-assert loop against a real backend
 * instead of forking a second copy of it. A duplicated walk loop is two
 * things to keep in sync, and the mocked and real walks diverging silently
 * (a fixed race condition patched in one copy but not the other, say) is
 * exactly the failure mode this extraction avoids.
 *
 * Everything below is unchanged in substance from the original walk.spec.ts
 * loop; only the mock-installation and session-setup steps became
 * parameters, and the canaries a StepContext carries became an explicit
 * option instead of always being invariants.ts's default constants.
 */
import { expect, type BrowserContext, type Page } from '@playwright/test'

import {
  assertHistoryStepInvariants,
  assertStepInvariants,
  createConsoleWatcher,
  LOADING_RESOLUTION_BUDGET_MS,
  LOADING_SELECTOR,
  type RoleFamilyCanaries,
  type StepContext,
} from './invariants'
import { createFindingsSink } from './findings'
import type { Persona, PersonaId } from './personas'
import { createRng, RESOLVED_SEED } from './prng'
import { assertNoHorizontalOverflow } from '../../e2e/support/responsiveChecks'

/** How many steps each persona's walk takes. Bounded for CI speed; large enough to reach several distinct states. */
export const STEP_BUDGET = 10

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
 *    (notifications/stream). Playwright's own docs call this out:
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
 * the SOURCE page's DOM is still fully mounted and interactive. Waiting for
 * the clicked element itself to detach is a direct DOM-observed signal of
 * that commit. settleAfterNavigation below then covers the remaining case
 * (the new page's own initial data has not yet rendered) by reusing I3's own
 * loading-indicator poll: a DOM-state wait, not a network-state one, so it
 * is immune to the same open-connection problem, and applies identically
 * whether the loading indicator is resolving a mocked fixture or a real
 * backend response.
 */
async function settleAfterNavigation(page: Page): Promise<void> {
  // Best-effort only: this is not itself an invariant check (a loading
  // indicator that is still present after the budget is I3's job to catch,
  // on the very next assertStepInvariants call), just a settle point before
  // this step's own hrefs are read.
  await expect(page.locator(LOADING_SELECTOR))
    .toHaveCount(0, { timeout: LOADING_RESOLUTION_BUDGET_MS })
    .catch(() => undefined)
}

/** One entry in a visited-sequence, for the seed-replay verification. */
export interface VisitedStep {
  step: number
  url: string
}

/** A session-setup routine: seed whatever auth state this persona needs before the walk's first navigation. */
export type SessionSetup = (context: BrowserContext, page: Page) => Promise<void>

export interface WalkOptions {
  persona: Persona
  /**
   * How to seed this persona's session before the walk starts. Distinct
   * from `persona.setupSession` (personas.ts) so a caller can supply a
   * real-backend variant (real-canaries.ts / walk-real.spec.ts) without
   * personas.ts itself needing two divergent copies of the same persona.
   */
  setupSession: SessionSetup
  /**
   * Install this persona's mocked API surface, or omit entirely for the
   * real tier (zero route mocks, matching e2e-real's own convention).
   */
  installMocks?: (context: BrowserContext, page: Page, personaId: PersonaId) => Promise<void>
  /** I5 canary values in effect; omitted uses invariants.ts's DEFAULT_CANARIES (the mocked tier's literals). */
  canaries?: RoleFamilyCanaries
  /** Which usersim workflow produced this run (findings.ts's UsersimFinding.workflow). */
  workflow: string
}

/**
 * Run one persona's seeded random walk: seed its session, optionally
 * install mocks, then repeatedly pick a visible in-app link at random (via
 * the seeded PRNG, prng.ts) and click it, asserting I1-I5 at every state and
 * I6 after an occasional random back/forward step.
 */
export async function runWalk(
  options: WalkOptions,
  page: Page,
  context: BrowserContext
): Promise<VisitedStep[]> {
  const { persona, setupSession, installMocks, canaries, workflow } = options
  const rng = createRng(RESOLVED_SEED)
  const visited: VisitedStep[] = []
  const findingsLines: string[] = []
  const sink = createFindingsSink((line) => findingsLines.push(line))

  // Attach BEFORE the first navigation (I1's requirement), so console
  // activity from the initial load is not missed.
  const watcher = createConsoleWatcher(page)

  await setupSession(context, page)
  if (installMocks) {
    await installMocks(context, page, persona.id)
  }

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
      workflow,
      canaries,
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
    // See the module doc comment on settleAfterNavigation above for why this
    // wait exists and why 1s (not LOADING_RESOLUTION_BUDGET_MS) is enough: a
    // click into a shared shell nav or a same-route link never detaches at
    // all, so this must not fail the step; settleAfterNavigation below still
    // gates the next iteration's read either way.
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
