/**
 * Composable invariant assertions (I1-I6) for the usersim walk tier.
 *
 * Every assertion here takes a `StepContext` (the page, the persona, the
 * seed in effect, and a findings sink) and either resolves silently or
 * records a finding through B1a's `findings.ts` AND throws, so the failing
 * Playwright step names the invariant, the URL, and the seed in one message.
 * A finding that cannot be replayed is a rumour (see prng.ts); the seed is
 * therefore embedded in the THROWN error text, not only logged, because a CI
 * reader sees the assertion failure, not the console.
 */
import { expect, type Page } from '@playwright/test'

import { isAllowlistedConsoleMessage } from './console-allowlist'
import type { FindingsSink } from './findings'
import { getPersona, type PersonaId } from './personas'

/**
 * I5 canaries. Embedded by the walk's mock fixtures (walk.spec.ts) into
 * response bodies that only a specific ring should ever render, per ADR-016's
 * three-ring boundary:
 *
 * - GUARDIAN_ONLY_CANARY sits in adult-only data (the guardian notification
 *   feed). Legitimate for the guardian/admin rings; the kid ring must never
 *   render it, since a kid session carries no guardian auth at all.
 * - FAMILY_B_CANARY sits in cross-family admin data (the admin family
 *   roster). Legitimate for the admin ring only, which is deliberately
 *   cross-family; neither the kid ring nor a plain guardian (scoped to their
 *   own family) may ever render it.
 *
 * Exported so walk.spec.ts's mock fixtures and this module's check agree on
 * one literal value each; a copy-pasted second literal is exactly how this
 * kind of trip-wire silently stops tripping.
 */
export const GUARDIAN_ONLY_CANARY = 'usersim-canary-guardian-only-4f7c'
export const FAMILY_B_CANARY = 'usersim-canary-family-b-9d21'

/** Bounded wait for a loading indicator to resolve (I3). Not a fixed sleep: the assertion polls and returns as soon as the condition holds. */
export const LOADING_RESOLUTION_BUDGET_MS = 8_000

/**
 * Matches every loading indicator this app renders. Not a literal
 * `data-testid="loading"` grep: only frontend/src/reader/ReaderPage.tsx:896
 * carries that exact testid. Every other loading state renders through the
 * shared `LoadingStatus` component (design-system/src/components/
 * LoadingStatus/LoadingStatus.tsx), whose base class `cyo-loading` is present
 * on every instance regardless of the className a call site adds, or (kid
 * library only) a bespoke `.library__loading` div that mirrors the same
 * pattern without using the component (frontend/src/library/LibraryPage.tsx).
 * `role="status"` alone is NOT used here: plenty of permanent, non-loading
 * content (banners, empty-state notices, the toast viewport) also carries
 * `role="status"`, and I3 must resolve to absent, not stay present forever.
 */
export const LOADING_SELECTOR = '.cyo-loading, .library__loading, [data-testid="loading"]'

/**
 * Broad "is this state alive" selector for I2: any visible, enabled control
 * a user could act on. Deliberately wider than the walk's own movement
 * selector (see walk.spec.ts's NAV_LINK_SELECTOR): a page whose only control
 * is a mutating button (e.g. "Retry") is not a dead end even though the walk
 * itself will not click it to move forward.
 */
export const INTERACTIVE_SELECTOR = [
  'a[href]:visible',
  'button:not([disabled]):visible',
  'input:not([disabled]):not([type="hidden"]):visible',
  'select:not([disabled]):visible',
  '[role="button"]:not([aria-disabled="true"]):visible',
  '[role="link"]:not([aria-disabled="true"]):visible',
].join(', ')

export interface StepContext {
  page: Page
  persona: PersonaId
  seed: number
  /** 1-based step counter, for a human-readable failure message. */
  step: number
  sink: FindingsSink
  /** Which usersim workflow produced this run (see findings.ts's UsersimFinding.workflow). */
  workflow: string
}

function replayHint(ctx: StepContext): string {
  return `persona=${ctx.persona} seed=${ctx.seed} step=${ctx.step} url=${ctx.page.url()} (replay: USERSIM_SEED=${ctx.seed} npx playwright test --project=usersim -g ${JSON.stringify(ctx.persona)})`
}

function recordAndThrow(
  ctx: StepContext,
  invariant: string,
  severity: 'critical' | 'high',
  detail: string
): never {
  ctx.sink.record({
    leg: 'A',
    persona: ctx.persona,
    scenario_or_seed: ctx.seed,
    url: ctx.page.url(),
    invariant_or_verdict: invariant,
    severity,
    // No screenshot is captured here: invariants.ts has no test-output
    // directory of its own to write into. walk.spec.ts's failure handler
    // (test.afterEach) attaches a screenshot to a persona-scoped evidence
    // path when a test fails, keyed by the same seed/step this message
    // carries, so the JSONL row and the image are joinable after the fact.
    evidence_path: '',
    workflow: ctx.workflow,
  })
  throw new Error(`${invariant}: ${detail} [${replayHint(ctx)}]`)
}

/** A live console/pageerror listener pair, buffering messages since the last drain. */
export interface ConsoleWatcher {
  /** Return and clear every non-allowlisted error message seen since the last call. */
  drain(): string[]
  /** Stop listening. Call once the walk is done with this page. */
  dispose(): void
}

/**
 * I1 substrate: attach BEFORE the first navigation, per the task brief, so no
 * console activity from the initial load is missed. Buffers rather than
 * asserting immediately, so a caller can drain and assert once per step and
 * name the failing step precisely, instead of one assertion covering the
 * whole walk.
 */
export function createConsoleWatcher(page: Page): ConsoleWatcher {
  let buffer: string[] = []

  function onConsole(msg: { type(): string; text(): string }): void {
    if (msg.type() !== 'error') return
    if (isAllowlistedConsoleMessage(msg.text())) return
    buffer.push(`console.error: ${msg.text()}`)
  }

  function onPageError(err: Error): void {
    // Chromium reports both uncaught exceptions and unhandled promise
    // rejections through 'pageerror'; no separate listener is needed for
    // "unhandled rejection" in the task brief's I1 wording.
    if (isAllowlistedConsoleMessage(err.message)) return
    buffer.push(`pageerror: ${err.message}`)
  }

  page.on('console', onConsole)
  page.on('pageerror', onPageError)

  return {
    drain(): string[] {
      const drained = buffer
      buffer = []
      return drained
    },
    dispose(): void {
      page.off('console', onConsole)
      page.off('pageerror', onPageError)
    },
  }
}

/** I1: no buffered console.error/pageerror/unhandled-rejection since the last drain. */
export function assertCleanConsole(watcher: ConsoleWatcher, ctx: StepContext): void {
  const messages = watcher.drain()
  if (messages.length === 0) return
  recordAndThrow(ctx, 'I1', 'critical', `unexpected console activity: ${messages.join(' | ')}`)
}

/**
 * I2: this state offers an enabled interactive element, or is a recognised
 * terminal for this persona (personas.ts). Do NOT widen the terminal list to
 * make a walk pass; report a suspected false dead end instead.
 */
export async function assertNotDeadEnd(ctx: StepContext): Promise<void> {
  const count = await ctx.page.locator(INTERACTIVE_SELECTOR).count()
  if (count > 0) return

  const url = new URL(ctx.page.url())
  const persona = getPersona(ctx.persona)
  const isTerminal = persona.terminals.some((terminal) => terminal.path === url.pathname)
  if (isTerminal) return

  recordAndThrow(
    ctx,
    'I2',
    'high',
    `dead end: no enabled interactive element at ${url.pathname}, and it is not a recognised terminal for ${ctx.persona}`
  )
}

/** I3: any loading indicator present at this state resolves within budget, no fixed sleep. */
export async function assertLoadingResolves(ctx: StepContext): Promise<void> {
  try {
    await expect(ctx.page.locator(LOADING_SELECTOR)).toHaveCount(0, {
      timeout: LOADING_RESOLUTION_BUDGET_MS,
    })
  } catch {
    recordAndThrow(
      ctx,
      'I3',
      'high',
      `a loading indicator did not resolve within ${LOADING_RESOLUTION_BUDGET_MS}ms`
    )
  }
}

/** I4: zero page-level horizontal overflow, via the hoisted, shared helper. */
export async function assertNoOverflow(
  ctx: StepContext,
  assertNoHorizontalOverflow: (page: Page, label: string) => Promise<void>
): Promise<void> {
  try {
    await assertNoHorizontalOverflow(ctx.page, `usersim/${ctx.persona}`)
  } catch (err) {
    recordAndThrow(
      ctx,
      'I4',
      'high',
      err instanceof Error ? err.message : 'page scrolls horizontally'
    )
  }
}

/**
 * I5, highest severity: role and family isolation. A kid session must never
 * render guardian-only content; neither the kid nor a plain guardian may
 * ever render cross-family (admin-only) content. See the canary doc comment
 * above for which ring each canary belongs to.
 */
export async function assertRoleFamilyIsolation(ctx: StepContext): Promise<void> {
  const html = await ctx.page.content()

  if (
    ctx.persona === 'kid' &&
    (html.includes(GUARDIAN_ONLY_CANARY) || html.includes(FAMILY_B_CANARY))
  ) {
    recordAndThrow(
      ctx,
      'I5',
      'critical',
      'kid session rendered guardian-only or cross-family content (ADR-016 three-ring boundary)'
    )
  }

  if (ctx.persona === 'guardian' && html.includes(FAMILY_B_CANARY)) {
    recordAndThrow(
      ctx,
      'I5',
      'critical',
      "guardian session rendered another family's data (ADR-016 three-ring boundary)"
    )
  }

  // The admin persona is deliberately not checked here: ADR-016 places admin
  // at the top of the ring hierarchy, so cross-family content is legitimate
  // on admin surfaces and neither canary denotes a violation for it.
}

/**
 * Run I1-I5 at a normal walk step (a fresh navigation or an in-page click).
 */
export async function assertStepInvariants(
  ctx: StepContext,
  watcher: ConsoleWatcher,
  assertNoHorizontalOverflow: (page: Page, label: string) => Promise<void>
): Promise<void> {
  await assertLoadingResolves(ctx)
  assertCleanConsole(watcher, ctx)
  await assertNotDeadEnd(ctx)
  await assertNoOverflow(ctx, assertNoHorizontalOverflow)
  await assertRoleFamilyIsolation(ctx)
}

/**
 * I6: run only I1-I4 after a random back/forward step, per the task brief's
 * table ("lands in a state still satisfying I1 to I4"). I2/I5 are
 * deliberately excluded: a back/forward step can legitimately land on a page
 * this walk has already judged (or will judge) on its own forward visit, and
 * re-asserting dead-end/isolation there adds no new coverage over what the
 * forward pass already checks.
 */
export async function assertHistoryStepInvariants(
  ctx: StepContext,
  watcher: ConsoleWatcher,
  assertNoHorizontalOverflow: (page: Page, label: string) => Promise<void>
): Promise<void> {
  await assertLoadingResolves(ctx)
  assertCleanConsole(watcher, ctx)
  await assertNoOverflow(ctx, assertNoHorizontalOverflow)
}
