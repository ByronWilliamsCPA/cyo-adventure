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
 *
 * The walk loop itself (movement, I1-I6 assertion order, the detach-wait
 * navigation fix) lives in support/walk-runner.ts, not here: task B3a
 * extracted it so the real-backend walk (walk-real.spec.ts) could reuse it
 * unchanged instead of forking a second copy. The route-mocked API surface
 * (task B3b extracted it too) lives in support/mocked-api.ts, so the I7
 * axe-on-new-states walk (walk-a11y.spec.ts) can reuse the same mocked
 * fixtures without a second copy of ~180 lines of route mocks drifting from
 * this one. This file is now just the persona loop plus the workflow tag
 * that ties its findings to this specific spec.
 */
import { test } from '@playwright/test'

import { installWalkMocks } from './support/mocked-api'
import { PERSONAS } from './support/personas'
import { runWalk } from './support/walk-runner'

/** Which usersim workflow produced these findings (findings.ts's UsersimFinding.workflow). */
const WORKFLOW = 'usersim-walk'

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
    await runWalk(
      {
        persona,
        // Wrapped rather than passed by reference (`persona.setupSession`):
        // Persona declares setupSession with method syntax, and eslint's
        // unbound-method rule flags detaching a method reference from its
        // object (no `this` is used here, but the rule cannot see that
        // without a `this: void` annotation on the interface itself).
        setupSession: (context, page) => persona.setupSession(context, page),
        installMocks: installWalkMocks,
        workflow: WORKFLOW,
        // canaries omitted: defaults to invariants.ts's DEFAULT_CANARIES,
        // the same GUARDIAN_ONLY_CANARY/FAMILY_B_CANARY this file's mocks embed.
      },
      page,
      context
    )
  })
}
