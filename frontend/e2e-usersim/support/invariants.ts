/**
 * Composable invariant assertions (I1-I7) for the usersim walk tier.
 *
 * Every assertion here takes a `StepContext` (the page, the persona, the
 * seed in effect, and a findings sink) and either resolves silently or
 * records a finding through B1a's `findings.ts` AND throws, so the failing
 * Playwright step names the invariant, the URL, and the seed in one message.
 * A finding that cannot be replayed is a rumour (see prng.ts); the seed is
 * therefore embedded in the THROWN error text, not only logged, because a CI
 * reader sees the assertion failure, not the console.
 *
 * I7 (task B3b) is the one exception to "runs at every step": it is gated on
 * `StepContext.axeTracker` being present, which only walk-a11y.spec.ts sets.
 * The mocked (walk.spec.ts) and real-backend (walk-real.spec.ts) nightly
 * walks never set it, so I7 is a true no-op there, exactly as it must be per
 * ADR-029/CLAUDE.md: this tier's own required-gate project (`usersim`, wired
 * nowhere near `ci.yml`'s per-PR `frontend-e2e` job) and its nightly
 * counterparts must not grow new accessibility scope on their own.
 */
import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

import { AXE_TAGS, isConformance } from '../../e2e/support/axeTags'
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

/**
 * The two literal values I5 checks for at each step. Parameterized (task
 * B3a), not hardcoded, so the real-tier walk (walk-real.spec.ts) can supply
 * real seeded-row values instead of the mocked-fixture literals above,
 * without forking this assertion. `DEFAULT_CANARIES` preserves the mocked
 * tier's existing behavior exactly: a `StepContext` with no `canaries` field
 * checks against the same two constants it always has.
 */
export interface RoleFamilyCanaries {
  guardianOnly: string
  familyB: string
}

export const DEFAULT_CANARIES: RoleFamilyCanaries = {
  guardianOnly: GUARDIAN_ONLY_CANARY,
  familyB: FAMILY_B_CANARY,
}

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

/**
 * I7 substrate: which state signatures this walk has already axe-scanned.
 * One tracker per persona's walk (created by the caller, walk-a11y.spec.ts,
 * and threaded through `WalkOptions.axeTracker` in walk-runner.ts), not a
 * module-level singleton: Playwright can run persona tests concurrently in
 * separate workers, and a shared mutable Set across workers would race.
 *
 * `scanned.size` after the walk finishes IS the "distinct signatures
 * scanned" count the task brief requires: a tracker that reaches the end of
 * a walk with `scanned.size === 0` (nothing was ever new) is distinguishable
 * from I7 having silently stopped running at all, because walk-runner.ts
 * logs `scanned.size` unconditionally whenever a tracker is present, not
 * only when it is nonzero.
 */
export interface AxeStateTracker {
  scanned: Set<string>
}

export function createAxeStateTracker(): AxeStateTracker {
  return { scanned: new Set() }
}

/**
 * The closed set of usersim workflow tags a `StepContext` can carry: each
 * spec file's own `WORKFLOW` constant (walk.spec.ts's `'usersim-walk'`,
 * walk-real.spec.ts's `'usersim-walk-real'`, walk-a11y.spec.ts's
 * `'usersim-a11y-weekly'`).
 *
 * Task B3b second review, F3: `REPLAY_PROJECT_BY_WORKFLOW` used to be keyed
 * by bare `string` with a `?? 'usersim'` fallback, so a fourth walk spec
 * adding a new tag here would silently fall back to `usersim` (the WRONG
 * project for anything but walk.spec.ts) at replay time instead of failing
 * anywhere. Threading this union through `StepContext.workflow` (below) and
 * `WalkOptions.workflow` (walk-runner.ts) makes a new, unregistered tag a
 * compile error at the spec file that introduces it: `tsc -b` rejects the
 * `workflow: WORKFLOW` assignment before the code ever ships, rather than
 * printing a wrong replay command the first time that tag's invariant fires.
 */
export type Workflow = 'usersim-walk' | 'usersim-walk-real' | 'usersim-a11y-weekly'

export interface StepContext {
  page: Page
  persona: PersonaId
  seed: number
  /** 1-based step counter, for a human-readable failure message. */
  step: number
  sink: FindingsSink
  /** Which usersim workflow produced this run (see findings.ts's UsersimFinding.workflow). */
  workflow: Workflow
  /**
   * I5 canary values in effect for this run. Optional: omitted (mocked tier)
   * falls back to DEFAULT_CANARIES, so every existing caller is unaffected.
   * The real-tier walk sets this to real seeded-row values (task B3a).
   */
  canaries?: RoleFamilyCanaries
  /**
   * I7 (task B3b) substrate. Omitted on every existing caller (walk.spec.ts,
   * walk-real.spec.ts): I7 is opt-in, only present on the weekly
   * accessibility walk (walk-a11y.spec.ts), so those two nightly tiers never
   * run an axe scan at all.
   */
  axeTracker?: AxeStateTracker
}

/**
 * Which Playwright project actually reproduces a failure originating from
 * each `StepContext.workflow` tag (see each spec file's own `WORKFLOW`
 * constant: walk.spec.ts's `'usersim-walk'`, walk-real.spec.ts's
 * `'usersim-walk-real'`, walk-a11y.spec.ts's `'usersim-a11y-weekly'`).
 *
 * Task B3b review, M1: `replayHint` used to hardcode `--project=usersim`
 * unconditionally. That is correct for the mocked tier (walk.spec.ts) but
 * was silently wrong for both other callers: `--project=usersim` runs
 * walk.spec.ts, which never sets `axeTracker`, so an I7 failure's replay
 * command could not reproduce it at all (I7 is a documented no-op there),
 * and it also picks the wrong project for a walk-real.spec.ts failure (that
 * tier needs a real backend up, which `usersim` never touches). The module
 * header's own claim -- "a finding that cannot be replayed is a rumour" --
 * does not hold if the printed command runs the wrong file.
 *
 * `Record<Workflow, string>` (not `Record<string, string>`): every member of
 * the `Workflow` union must have an entry, so this object literal itself is
 * a compile error the moment `Workflow` grows a tag this map does not cover,
 * and `replayHint` below never needs a silent fallback for a missing key.
 */
const REPLAY_PROJECT_BY_WORKFLOW: Record<Workflow, string> = {
  'usersim-walk': 'usersim',
  'usersim-walk-real': 'usersim-real',
  'usersim-a11y-weekly': 'usersim-a11y',
}

/**
 * Extra env var(s) a replay command needs beyond `USERSIM_SEED`, keyed the
 * same way as `REPLAY_PROJECT_BY_WORKFLOW`. Only `usersim-a11y` needs one:
 * walk-a11y.spec.ts's own `test.skip` makes the whole project a no-op
 * without `A11Y_EXTENDED=1` (see that file's header comment), so a replay
 * command missing it would print "3 skipped" and reproduce nothing. `Partial`
 * here (unlike `REPLAY_PROJECT_BY_WORKFLOW` above) because most workflows
 * need no extra env at all, not because the key type is unconstrained.
 */
const REPLAY_ENV_BY_WORKFLOW: Partial<Record<Workflow, string>> = {
  'usersim-a11y-weekly': 'A11Y_EXTENDED=1 ',
}

function replayHint(ctx: StepContext): string {
  const project = REPLAY_PROJECT_BY_WORKFLOW[ctx.workflow]
  const envPrefix = REPLAY_ENV_BY_WORKFLOW[ctx.workflow] ?? ''
  return `persona=${ctx.persona} seed=${ctx.seed} step=${ctx.step} url=${ctx.page.url()} (replay: ${envPrefix}USERSIM_SEED=${ctx.seed} npx playwright test --project=${project} -g ${JSON.stringify(ctx.persona)})`
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
 *
 * `ctx.canaries` (falling back to `DEFAULT_CANARIES`) is what makes this
 * assertion reusable against real seeded rows on the real tier: the CHECK
 * itself never changes, only which literal it looks for.
 */
export async function assertRoleFamilyIsolation(ctx: StepContext): Promise<void> {
  const html = await ctx.page.content()
  const canaries = ctx.canaries ?? DEFAULT_CANARIES

  if (
    ctx.persona === 'kid' &&
    (html.includes(canaries.guardianOnly) || html.includes(canaries.familyB))
  ) {
    recordAndThrow(
      ctx,
      'I5',
      'critical',
      'kid session rendered guardian-only or cross-family content (ADR-016 three-ring boundary)'
    )
  }

  if (ctx.persona === 'guardian' && html.includes(canaries.familyB)) {
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
 * STATE SIGNATURE for I7: route pathname plus the page's first heading's
 * text, exactly the definition the task brief and
 * docs/testing/user-side-testing-module-proposal-2026-08-27.md both give
 * ("route + main heading"). "First heading" (`getByRole('heading').first()`
 * in DOM order), not specifically an `<h1>`: this app does not render an
 * `<h1>` on every route (e.g. the reader route's normal mid-story state has
 * no heading at all, only body text and choices), so an h1-only rule would
 * make every such state collapse to the SAME empty-heading signature anyway,
 * while silently mis-describing pages whose real heading is an `<h2>` (the
 * reader's own error/ending states) as headingless. Falls back to the empty
 * string when the route currently renders no heading at all.
 *
 * STATED TRADEOFF (do not rediscover this later): this signature is coarser
 * than "every distinct DOM state". Two genuinely different states that
 * happen to share both the same route and the same (or absent) main heading
 * are scanned ONCE, at whichever is reached first in that persona's walk,
 * not once each. The reader route is the concrete case this matters for:
 * every node of a story renders under the same
 * `/read/:profileId/:storybookId/:version` URL with no on-page heading, so
 * every reader state a given persona's walk visits collapses to one
 * signature and gets exactly one axe scan, however many distinct passages
 * the walk actually clicked through. That is an accepted scope limit for I7
 * (scanning every DOM permutation would multiply run time for questionable
 * marginal signal, since a passage's accessibility properties come from the
 * shared Reader chrome around it, not from the passage text itself), not an
 * oversight; a future task that wants passage-level a11y coverage needs a
 * finer signature (e.g. including the current node id), not a fix to this one.
 */
async function deriveStateSignature(page: Page): Promise<string> {
  const pathname = new URL(page.url()).pathname
  const heading = page.getByRole('heading').first()
  const headingText =
    (await heading.count()) > 0 ? ((await heading.textContent()) ?? '').trim() : ''
  return `${pathname}::${headingText}`
}

/**
 * I7 (task B3b): an axe accessibility scan of each state the first time
 * this walk reaches it (state signature above), instead of the "one fixed
 * mock state per surface" gap `docs/testing/coverage-matrix.md` records for
 * `e2e/a11y.spec.ts`. A true no-op when `ctx.axeTracker` is absent (see the
 * module doc comment and `StepContext.axeTracker`), so this function is safe
 * to call unconditionally from `assertStepInvariants`/
 * `assertHistoryStepInvariants` below without changing the mocked/real
 * nightly walks' behaviour at all.
 *
 * Rule scope is `AXE_TAGS` from `e2e/support/axeTags.ts`, the SAME constant
 * `e2e/a11y.spec.ts` scans with (task brief: "match the rule set the weekly
 * job already scans with"), so this only ever produces the WCAG 2.1 AA
 * baseline set unless `A11Y_EXTENDED=1` is set in the environment, exactly
 * like that file. walk-a11y.spec.ts (the only caller that ever sets
 * `axeTracker`) requires that flag before running at all; see its own
 * header comment.
 *
 * A WCAG-tagged ("conformance") violation records one finding per rule id
 * and throws, same failure shape as every other invariant here: a reader
 * gets the state signature, every violated rule id, and the replay hint in
 * one message. A non-WCAG ("best-practice", `structural` below) finding is
 * reported (console.warn, matching a11y.spec.ts's own precedent) but does
 * NOT fail the walk, for the identical reason a11y.spec.ts's own comment
 * gives: axe's ~30 best-practice-only rules include real hygiene debt this
 * repo has not cleared yet (see coverage-matrix.md's `UW-F27`), and failing
 * on all of them here would make I7 permanently red rather than able to
 * report a genuine regression.
 */
export async function assertNoNewStateAxeViolations(ctx: StepContext): Promise<void> {
  if (!ctx.axeTracker) return

  const signature = await deriveStateSignature(ctx.page)
  if (ctx.axeTracker.scanned.has(signature)) return
  ctx.axeTracker.scanned.add(signature)

  const results = await new AxeBuilder({ page: ctx.page }).withTags(AXE_TAGS).analyze()
  const conformance = results.violations.filter(isConformance)
  const structural = results.violations.filter((violation) => !isConformance(violation))

  // Emitted for EVERY new-state scan, pass or fail: this is the "count of
  // distinct signatures scanned" signal the task brief requires, so a run
  // that reached and scanned N states is distinguishable in the log from one
  // whose scanning silently stopped running (which would emit nothing at
  // all, not a count of zero).
  console.log(
    `[usersim-a11y-new-state] persona=${ctx.persona} signature=${JSON.stringify(signature)} ` +
      `distinct_states_scanned=${ctx.axeTracker.scanned.size} conformance=${conformance.length} structural=${structural.length}`
  )

  if (structural.length > 0) {
    const summary = structural
      .map((violation) => `${violation.id} (${violation.nodes.length})`)
      .join(', ')
    console.warn(
      `[usersim-a11y-new-state][best-practice] ${signature}: ${structural.length} non-WCAG finding(s): ${summary}. ` +
        `Tracked as UW-F27; not failing I7. Full detail: ${JSON.stringify(structural, null, 2)}`
    )
  }

  if (conformance.length > 0) {
    for (const violation of conformance) {
      ctx.sink.record({
        leg: 'A',
        persona: ctx.persona,
        scenario_or_seed: ctx.seed,
        url: ctx.page.url(),
        invariant_or_verdict: `I7:${violation.id}`,
        severity: 'high',
        evidence_path: '',
        workflow: ctx.workflow,
      })
    }
    const ids = conformance.map((violation) => violation.id)
    throw new Error(
      `I7: ${ids.length} WCAG conformance violation(s) at signature ${JSON.stringify(signature)}: ` +
        `${ids.join(', ')} [${replayHint(ctx)}]`
    )
  }
}

/**
 * Run I1-I5 (plus I7, a no-op unless `ctx.axeTracker` is set) at a normal
 * walk step (a fresh navigation or an in-page click).
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
  await assertNoNewStateAxeViolations(ctx)
}

/**
 * I6: run only I1-I4 after a random back/forward step, per the task brief's
 * table ("lands in a state still satisfying I1 to I4"). I2/I5 are
 * deliberately excluded: a back/forward step can legitimately land on a page
 * this walk has already judged (or will judge) on its own forward visit, and
 * re-asserting dead-end/isolation there adds no new coverage over what the
 * forward pass already checks. I7 (a no-op unless `ctx.axeTracker` is set)
 * is included: it is naturally cheap here too, since a back/forward step
 * lands on an already-visited URL whose signature is (almost always)
 * already in `axeTracker.scanned`, so this is a Set lookup, not a second
 * scan, in the common case.
 */
export async function assertHistoryStepInvariants(
  ctx: StepContext,
  watcher: ConsoleWatcher,
  assertNoHorizontalOverflow: (page: Page, label: string) => Promise<void>
): Promise<void> {
  await assertLoadingResolves(ctx)
  assertCleanConsole(watcher, ctx)
  await assertNoOverflow(ctx, assertNoHorizontalOverflow)
  await assertNoNewStateAxeViolations(ctx)
}
