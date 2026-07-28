import { defineConfig, devices } from '@playwright/test'

import { PROD_BASE_URL } from './e2e-prod/support/prod-env'

/**
 * Third e2e tier, deliberately kept in its own config file rather than a
 * project entry in playwright.config.ts: this one targets LIVE production,
 * not a locally-built preview server, so it has no webServer block.
 *
 * Runs two ways. Ad hoc via `npm run test:e2e:prod` (see
 * frontend/.env.e2e-prod.example for credential setup), and unattended on a
 * daily cron via .github/workflows/e2e-prod.yml. The scheduled run is a
 * deliberate, owner-directed override of the CI guard in
 * e2e-prod/support/prod-env.ts, not an accident: that workflow clears CI to an
 * empty string for its test-run step. Every run still authenticates a real
 * account against a live system, so treat any change here as production-facing.
 */
export default defineConfig({
  testDir: './e2e-prod',
  // Sized against the job budget, not just the happy path. The scheduled
  // workflow allows `timeout-minutes: 15` (900s) for checkout, npm ci,
  // playwright install, AND the run, and Playwright applies this timeout to
  // each of the tier's 16 timeout-bearing units (14 tests plus 2 beforeAll
  // sign-in hooks). 16 x 45s = 720s keeps a fully-degraded run inside the job
  // budget so the `if: failure()` trace-upload and issue-alert steps still
  // fire; at 60s the job would be killed mid-run and report nothing.
  //
  // 45s is still ample headroom over the resilience budget in
  // e2e-support/rate-limit.ts. A single gotoResilient that exhausts all three
  // attempts costs roughly 20s (the pacing floor, three settle waits, and two
  // backoffs of 2s and 4s), not the backoff alone. Kept at the tier level
  // rather than per-test so the beforeAll sign-in, which runs its own retry
  // loop, shares the same headroom.
  timeout: 45_000,
  fullyParallel: false,
  // Left at 0 deliberately: the rate-limit handling lives inside the helpers
  // (backoff-and-retry per navigation/sign-in), so a Playwright-level retry
  // would re-run whole specs and re-authenticate, adding MORE prod requests
  // rather than fewer. Absorb rate limits in-test, not by replaying the spec.
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: PROD_BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'e2e-prod', use: { ...devices['Desktop Chrome'] } }],
})
