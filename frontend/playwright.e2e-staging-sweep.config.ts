import { defineConfig, devices } from '@playwright/test'

import { stagingStorageStatePath } from './e2e-staging/support/auth-storage'
import { requireStagingBaseUrl } from './e2e-staging/support/staging-env'

/**
 * Config for the post-run device-grant sweep, deliberately separate from
 * playwright.e2e-staging.config.ts rather than a spec inside that tier.
 *
 * Separate because the sweep must run AFTER the tier and must run even when
 * the tier failed (`if: always()` in .github/workflows/e2e-staging.yml). A
 * spec inside the tier could not do either: Playwright gives no cross-file
 * ordering guarantee that survives a failure, and a leaked grant is created
 * by the very failures that would skip it.
 *
 * Keeping it out of `e2e-staging/` also leaves that config's timeout-unit
 * arithmetic (28 units x 30s) untouched, so the tier's 25-minute job budget
 * still means what its comment says.
 *
 * This project performs NO sign-in of its own. It restores the guardian
 * `storageState` that `playwright.e2e-staging.config.ts`'s `staging-auth-setup`
 * project wrote to disk during the SAME job's earlier `npm run test:e2e:staging`
 * step (see `e2e-staging/support/auth-storage.ts`). This is the change that
 * closes the cross-process half of the tier's self-inflicted 429s: pacing
 * inside `e2e-support/rate-limit.ts` is per-process module state, so this
 * sweep's own sign-in previously started with no memory of the budget the main
 * tier step had just spent against the same server-side per-IP window. Reading
 * an already-authenticated session from disk removes that sign-in, and the
 * request budget it used to spend, entirely.
 * #CRITICAL: external-resources: if `staging-auth-setup`'s guardian test never
 * ran or failed (a persistent 429, a wrong password, staging down), the file
 * this project reads does not exist, and Playwright fails this project's
 * context creation before the spec body runs. That is the correct outcome:
 * device-grant-sweep.spec.ts's own contract is "an unlistable family is an
 * unproven family", and a missing credential file is exactly that, reported
 * through a different error shape than before but not through a different
 * verdict.
 * #VERIFY: `device-grant-sweep.spec.ts` no longer imports
 * `signInAsStagingTestUser`; if it ever needs a role this file's
 * `storageState` does not cover, add a role-specific setup test rather than
 * signing in from inside the sweep again.
 *
 * One caveat on the budget claim above, so it is not read as stronger than it
 * is: the sweep does still make exactly ONE navigation. `storageState` seeds
 * an origin's localStorage but does not visit it, so the `page` fixture starts
 * on `about:blank`, whose opaque origin makes `window.localStorage` throw
 * `SecurityError`; the spec therefore opens `/guardian` through
 * `gotoResilient` before reading the token. What this config removed is the
 * SIGN-IN (a login form submit plus its Supabase round trip and post-login
 * fan-out), not every request. See the spec's own #CRITICAL note on that
 * navigation.
 *
 * The `json` reporter writes outside `frontend/test-results/`, matching
 * playwright.e2e-staging.config.ts: this project's own config already keeps
 * traces/screenshots/video off below (nothing under test-results/ for this
 * project to begin with), and the JSON report must stay off that path
 * regardless, since e2e-staging.yml's alert-composing step reads it. `list`
 * stays first so human-readable CI console output is unchanged.
 */
const JSON_REPORT_PATH =
  process.env.PLAYWRIGHT_JSON_REPORT_PATH ?? 'playwright-json-report/e2e-staging-sweep.json'

export default defineConfig({
  testDir: './e2e-staging-sweep',
  // One test, no sign-in of its own (see above). Kept at 60s rather than
  // trimmed to the tier's 30s: the two-backoff-cycle margin this used to hold
  // for the sign-in helper's own retry loop no longer applies here, but this
  // step is the last thing between a leak and a green job, and unused
  // headroom in a 60s timeout on a single fetch-and-assert test costs nothing.
  timeout: 60_000,
  fullyParallel: false,
  // #CRITICAL: security: no retry. A retry here would produce a "flaky"
  // verdict on the one check whose whole purpose is to be un-swallowable, and
  // would spend a second GET against the same 60 rpm/IP limiter the fetch
  // itself is still subject to even with no sign-in. This spec must either
  // pass or fail the job.
  // #VERIFY: keep this at 0 in CI as well as locally.
  retries: 0,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: JSON_REPORT_PATH }]],
  use: {
    baseURL: requireStagingBaseUrl(),
    // #CRITICAL: security: the guardian bearer this project authenticates
    // with, restored from `stagingStorageStatePath('guardian')`'s
    // pre-authenticated storageState file rather than a fresh sign-in.
    // #VERIFY: this path must stay inside the gitignored
    // `frontend/e2e-staging/.auth/` directory (see `frontend/.gitignore`) and
    // outside `frontend/test-results/`, which is the only directory the
    // staging workflow uploads as an artifact. Re-check both if either the
    // path helper or an `upload-artifact` glob changes.
    storageState: stagingStorageStatePath('guardian'),
    // #CRITICAL: security: traces off, unlike the tier's 'retain-on-failure'.
    // This repo is PUBLIC, so a workflow artifact is downloadable by anyone
    // for its retention window, and a trace of this spec would carry the real
    // staging guardian bearer this context was restored with, plus the
    // request(s) made using it. The failure message alone (grant ids and
    // labels) is enough to act on.
    // #VERIFY: do not turn this on to debug a sweep failure; reproduce it
    // locally against staging instead.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'e2e-staging-sweep', use: { ...devices['Desktop Chrome'] } }],
})
