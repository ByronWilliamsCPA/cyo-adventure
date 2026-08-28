/**
 * Leg A, real-backend tier (task B3a): the same seeded random walk as
 * walk.spec.ts, run against the REAL stack instead of route-mocked
 * fixtures. Reuses the shared walk loop in support/walk-runner.ts unchanged
 * (see that module's header comment for why this is a parameterization, not
 * a fork); the only things that differ from walk.spec.ts are how each
 * persona's session is established (support/real-session-setup.ts's
 * REAL_SESSION_SETUP, real backend calls instead of localStorage fixtures)
 * and which I5 canary values are checked for (support/real-canaries.ts,
 * real seeded rows instead of mocked-fixture literals). Zero route mocks:
 * every `/api/v1/**` call this walk makes hits the real uvicorn started by
 * .github/workflows/e2e-real-nightly.yml, matching every other project in
 * frontend/e2e-real/.
 *
 * #CRITICAL: external-resources: this walk is meaningless, and fails in an
 * illegible way, without a real backend already up at E2E_BACKEND_URL
 * (default http://localhost:8000), already migrated and seeded
 * (scripts/seed_dev_data.py). `requireBackend()` below turns "the backend
 * is not running" into one named, actionable assertion failure BEFORE the
 * first persona's walk starts, instead of the first persona's walk timing
 * out 30s later with no indication of why. See real-stack.ts's own
 * docstring for the same pattern used by every frontend/e2e-real/ spec.
 * #VERIFY: playwright.config.ts's `usersim-real` project declares
 * `dependencies: ['real-backend-setup']`, so scripts/reset_e2e_real_state.py
 * has already run (reverting the review story to in_review) before this
 * file's test.beforeAll below even starts.
 */
import { test } from '@playwright/test'

import { requireBackend } from '../e2e-real/real-stack'
import { PERSONAS } from './support/personas'
import { proveRealCanariesExist, REAL_CANARIES } from './support/real-canaries'
import { REAL_SESSION_SETUP } from './support/real-session-setup'
import { runWalk } from './support/walk-runner'

/** Which usersim workflow produced these findings (findings.ts's UsersimFinding.workflow). */
const WORKFLOW = 'usersim-walk-real'

test.beforeAll(async () => {
  await requireBackend()
  // I5's proof-of-existence step (task B3a brief): assert both canary rows
  // are real and reachable from the side that legitimately sees each one,
  // BEFORE any persona's walk runs. A missing canary here is a broken
  // seed/reset pipeline, not an I5 finding; see real-canaries.ts's own
  // doc comment for why that distinction matters to whoever reads a red run.
  await proveRealCanariesExist()
})

test.afterEach(async ({ page }, testInfo) => {
  // Same evidence-joining rationale as walk.spec.ts's identical hook: a
  // failure's JSONL row (seed, step, url) and this screenshot are joinable
  // by seed + step, both embedded in the thrown assertion message.
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
        // REAL_SESSION_SETUP's per-persona functions take only `context`
        // (no mocked page-level route to install); walk-runner.ts's
        // `SessionSetup` type accepts a 2-arg function, and a function
        // declared with fewer parameters is assignable to it.
        setupSession: REAL_SESSION_SETUP[persona.id],
        // installMocks omitted: zero route mocks on this tier, matching
        // every other frontend/e2e-real/ spec.
        canaries: REAL_CANARIES,
        workflow: WORKFLOW,
      },
      page,
      context
    )
  })
}
