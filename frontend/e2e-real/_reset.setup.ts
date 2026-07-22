import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { test as setup } from '@playwright/test'

/**
 * Resets real-backend e2e fixture state before the `real-backend` project's
 * specs run, so `npm run test:e2e:real` is deterministic on a second
 * consecutive invocation (Phase 4.2,
 * docs/planning/handoff-test-coverage-robustness-2026-07-22.md).
 *
 * `scripts/seed_dev_data.py` is idempotent by early-returning once its base
 * fixtures exist; it never undoes what a prior *test run* mutated. Two
 * mutations accumulate across runs and cause false failures on a second
 * consecutive run: `approval-flow.spec.ts` approves the seeded review story
 * for real; `kid-reads.spec.ts` / `series-continue-real.spec.ts` /
 * `offline-conflict-real.spec.ts` leave `reading_state` rows pinned at an
 * ending or a mid-conflict revision; and `authored-request.spec.ts` spends
 * real monthly story-request quota that never resets mid-month.
 * `scripts/reset_e2e_real_state.py` reverts all three; see that script's
 * module docstring for the exact fields touched.
 *
 * This file is a harness-wiring shim, not a test in its own right: it is
 * matched by the dedicated `real-backend-setup` Playwright project (see
 * `testMatch` in playwright.config.ts), which the `real-backend` project
 * declares as a `dependencies` entry. The mocked `chromium` project has no
 * backend to reset and never references either project, so this never runs
 * there. The reset itself is a Python/SQLAlchemy script (mirrors
 * `scripts/seed_dev_data.py`) rather than inline SQL here, so both scripts
 * share one source of truth for the schema they touch.
 */
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')

setup('reset e2e-real fixture state (review story, reading-state)', () => {
  try {
    execFileSync('uv', ['run', 'python', 'scripts/reset_e2e_real_state.py'], {
      cwd: REPO_ROOT,
      stdio: 'inherit',
    })
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw new Error(
      'scripts/reset_e2e_real_state.py failed (see output above). Re-run it ' +
        'manually from the repo root (uv run python ' +
        'scripts/reset_e2e_real_state.py) with CYO_ADVENTURE_DATABASE_URL set ' +
        `to the local Postgres DSN to diagnose: ${reason}`,
      { cause: error }
    )
  }
})
