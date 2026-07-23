import { test as setup } from '@playwright/test'

import { resetRealState } from './real-stack'

/**
 * Resets real-backend e2e fixture state before the `real-backend` project's
 * specs run, so `npm run test:e2e:real` is deterministic on a second
 * consecutive invocation (Phase 4.2,
 * docs/planning/handoff-test-coverage-robustness-2026-07-22.md).
 *
 * `scripts/seed_dev_data.py` is idempotent by early-returning once its base
 * fixtures exist; it never undoes what a prior *test run* mutated. Five
 * mutations accumulate across runs and cause false failures on a second
 * consecutive run: `approval-flow.spec.ts` approves the seeded review story
 * for real; `kid-reads.spec.ts` / `series-continue-real.spec.ts` /
 * `offline-conflict-real.spec.ts` leave `reading_state` rows pinned at an
 * ending or a mid-conflict revision; `authored-request.spec.ts` spends real
 * monthly story-request quota that never resets mid-month;
 * `full-pipeline-real.spec.ts` (plus `authored-request.spec.ts`, under the
 * hood) drives the real RQ worker to persist a fresh worker-generated
 * storybook every run; and `kid-flag-real.spec.ts` accumulates real
 * `kid_flag` rows whose `kid_flagged` notifications never stop resurfacing
 * as guardian-console toasts. `scripts/reset_e2e_real_state.py` reverts all
 * five; see that script's module docstring for the exact fields/tables
 * touched.
 *
 * This file is a harness-wiring shim, not a test in its own right: it is
 * matched by the dedicated `real-backend-setup` Playwright project (see
 * `testMatch` in playwright.config.ts), which the `real-backend` project
 * declares as a `dependencies` entry. The mocked `chromium` project has no
 * backend to reset and never references either project, so this never runs
 * there. The reset itself is a Python/SQLAlchemy script (mirrors
 * `scripts/seed_dev_data.py`) rather than inline SQL here, so both scripts
 * share one source of truth for the schema they touch.
 *
 * The actual shell-out lives in `resetRealState()` (real-stack.ts), the same
 * helper individual spec files call from their own `test.beforeAll` when they
 * need a pristine baseline regardless of what ran earlier in the same
 * full-suite invocation; this file is just that helper's once-per-invocation
 * caller.
 */
setup('reset e2e-real fixture state (review story, reading-state)', () => {
  resetRealState()
})
