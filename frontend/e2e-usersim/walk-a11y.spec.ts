/**
 * I7 (task B3b): the same seeded random walk as walk.spec.ts, over the same
 * mocked-tier fixtures (support/mocked-api.ts), but with an axe accessibility
 * scan of each NEWLY reached state (invariants.ts's assertNoNewStateAxeViolations)
 * added on top of I1-I6. This is a SEPARATE spec file, testDir, and Playwright
 * project (`usersim-a11y` in playwright.config.ts), never a tag or grep
 * filter added to walk.spec.ts itself, per this repo's tier-separation rule
 * and so the I1-I6-only nightly tiers (usersim.yml, e2e-real-nightly.yml)
 * never pick this file up.
 *
 * Owner decision (docs/testing/user-side-testing-module-proposal-2026-08-27.md,
 * I7 section): I7 runs in `.github/workflows/accessibility-compliance-weekly.yml`
 * behind that workflow's existing `A11Y_EXTENDED=1` flag, NOT in a new
 * standalone workflow of its own, and NEVER inside `ci.yml`'s required
 * `frontend-e2e` job (ADR-029's per-PR scope constraint). `test.skip` below
 * enforces the flag requirement structurally: running this project without
 * `A11Y_EXTENDED=1` set (e.g. an accidental future wiring into another
 * workflow, or a bare local `npx playwright test --project=usersim-a11y`)
 * skips rather than silently running an unintended WCAG-2.1-only scan that
 * would duplicate e2e/a11y.spec.ts's own per-PR job for no reason.
 *
 * Reuses the mocked-tier fixtures (support/mocked-api.ts), not a real
 * backend: the weekly workflow's existing a11y.spec.ts step already scans
 * "the mocked-tier build" (see that workflow's own header comment), and I7
 * widens that same known gap (coverage-matrix.md: "each remaining page/
 * dialog is still checked in one fixed mock state") rather than opening a
 * new, unrelated real-backend surface.
 */
import { expect, test } from '@playwright/test'

import { createAxeStateTracker } from './support/invariants'
import { installWalkMocks } from './support/mocked-api'
import { PERSONAS } from './support/personas'
import { runWalk } from './support/walk-runner'

/** Which usersim workflow produced these findings (findings.ts's UsersimFinding.workflow). */
const WORKFLOW = 'usersim-a11y-weekly'

test.afterEach(async ({ page }, testInfo) => {
  // Same evidence-joining rationale as walk.spec.ts's identical hook: a
  // failure's JSONL row (seed, step, url/signature) and this screenshot are
  // joinable by seed + step, both embedded in the thrown assertion message.
  if (testInfo.status !== testInfo.expectedStatus) {
    const path = testInfo.outputPath('failure.png')
    await page.screenshot({ path }).catch(() => undefined)
  }
})

for (const persona of PERSONAS) {
  test(persona.id, async ({ page, context }) => {
    test.skip(
      process.env.A11Y_EXTENDED !== '1',
      "I7 runs only behind A11Y_EXTENDED=1, the weekly accessibility slot's flag " +
        "(accessibility-compliance-weekly.yml, task B3b); see this file's header comment."
    )

    const axeTracker = createAxeStateTracker()

    await runWalk(
      {
        persona,
        setupSession: (context, page) => persona.setupSession(context, page),
        installMocks: installWalkMocks,
        workflow: WORKFLOW,
        // canaries omitted: defaults to invariants.ts's DEFAULT_CANARIES, the
        // same literals support/mocked-api.ts's fixtures embed, matching
        // walk.spec.ts.
        axeTracker,
      },
      page,
      context
    )

    // Task B3b review, Important 2(a): this whole spec exists to run I7, so a
    // walk that reached the end having scanned NOTHING must fail loudly
    // rather than pass green. Without this, dropping `axeTracker:` from the
    // options above (or any future refactor that stops threading it into
    // every StepContext) would still produce 3 green tests: I1-I6 do not
    // depend on it, and `assertNoNewStateAxeViolations` is a documented
    // no-op whenever `ctx.axeTracker` is absent. `axeTracker` (this file's
    // own local variable, not a value re-read off `runWalk`'s return) is the
    // ground truth here: it is the exact same object threaded into every
    // step's `StepContext`, so its `scanned` Set only grows if I7 actually
    // ran.
    expect(
      axeTracker.scanned.size,
      `I7 never axe-scanned any state for persona=${persona.id}: axeTracker.scanned is empty. ` +
        "This spec's entire purpose is running I7; either the walk found no " +
        "reachable state (unlikely; check personas.ts's entryPath) or " +
        "axeTracker was dropped from runWalk's options."
    ).toBeGreaterThan(0)
  })
}
