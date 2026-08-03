import { defineConfig, devices } from '@playwright/test'

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
 * arithmetic (21 units x 30s) untouched, so the tier's 20-minute job budget
 * still means what its comment says.
 */
export default defineConfig({
  testDir: './e2e-staging-sweep',
  // One test, one sign-in. 60s rather than the tier's 30s because the sign-in
  // helper's own rate-limit retry can spend two backoff cycles before
  // succeeding, and this step is the last thing between a leak and a green job.
  timeout: 60_000,
  fullyParallel: false,
  // #CRITICAL: security: no retry. A retry here would be a fresh sign-in
  // against the same 60 rpm/IP limiter, and, worse, a "flaky" verdict on the
  // one check whose whole purpose is to be un-swallowable. This spec must
  // either pass or fail the job.
  // #VERIFY: keep this at 0 in CI as well as locally.
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: requireStagingBaseUrl(),
    // #CRITICAL: security: traces off, unlike the tier's 'retain-on-failure'.
    // This repo is PUBLIC, so a workflow artifact is downloadable by anyone
    // for its retention window, and a trace of this spec would carry the real
    // staging guardian bearer plus DOM snapshots of the sign-in form. The
    // failure message alone (grant ids and labels) is enough to act on.
    // #VERIFY: do not turn this on to debug a sweep failure; reproduce it
    // locally against staging instead.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'e2e-staging-sweep', use: { ...devices['Desktop Chrome'] } }],
})
