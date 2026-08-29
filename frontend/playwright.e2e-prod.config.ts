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
 *
 * The `json` reporter writes outside `frontend/test-results/` on purpose. That
 * directory is where Playwright's own per-failure artifacts land, this
 * repository is public, and the credential-bearing ones are described under
 * `use.trace` below; keeping the report out of it means nothing this
 * workflow's alert-composing step reads can ever be swept up with them, and
 * means the report survives even if that directory is deleted wholesale.
 * `list` stays first so human-readable CI console output is unchanged.
 */
const JSON_REPORT_PATH =
  process.env.PLAYWRIGHT_JSON_REPORT_PATH ?? 'playwright-json-report/e2e-prod.json'

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
  // #EDGE: concurrency: e2e-support/rate-limit.ts paces navigations through
  // per-worker module state, so one instance paces a whole run only while this
  // stays at 1. Multi-worker would let each worker pace independently and the
  // aggregate rate could still exceed the 60 rpm/IP ceiling.
  // #VERIFY: raising this requires moving the pacing floor to shared state.
  workers: 1,
  reporter: [['list'], ['json', { outputFile: JSON_REPORT_PATH }]],
  use: {
    baseURL: PROD_BASE_URL,
    // #CRITICAL: security: off, matching playwright.e2e-staging-sweep.config.ts
    // and playwright.e2e-staging.config.ts. This tier signs a REAL production
    // account in through the real login form
    // (e2e-prod/support/auth.ts::signInAsProdTestAdmin does
    // `page.getByLabel('Password').fill(password)` with
    // E2E_PROD_TEST_PASSWORD), and a Playwright trace records that value in
    // plain text. Verified by extracting a trace from a deliberately failing
    // run whose credential came only from the environment, exactly as this
    // tier's does: the password appears in the `Fill "..."` step title in
    // `test.trace`, in the `fill` action's `params.value` in `0-trace.trace`,
    // and, unmasked, in the accessibility snapshot as
    // `textbox "Password": <value>`; an `Authorization: Bearer ...` header
    // appears in `0-trace.network`. The "password inputs are masked"
    // intuition does not hold for traces. This repository is PUBLIC, so any
    // workflow artifact carrying one is world-readable for its whole
    // retention window.
    //
    // #CRITICAL: security: these three settings are NECESSARY BUT NOT
    // SUFFICIENT, and must never be mistaken for the control that closes the
    // leak. Measured against live GitHub Actions artifacts on 2026-08-29:
    // `playwright.e2e-staging-sweep.config.ts` has had all three set to 'off'
    // for some time, and three of its published `e2e-staging-traces`
    // artifacts still each held exactly one file, an `error-context.md`, whose
    // accessibility snapshot rendered `textbox "Password" ...: <value>` in
    // plain text. Playwright writes `error-context.md` as part of its error
    // reporting, governed by the reporter and the output directory, NOT by
    // these `use` options. The control that actually closes it is at the
    // UPLOAD boundary: this tier's workflow publishes no artifact at all, and
    // `frontend/scripts/check-artifact-upload-safety.mjs` fails CI if any
    // workflow that injects a repository secret starts publishing a
    // Playwright output directory again.
    // #VERIFY: do not turn this on to debug a prod failure; reproduce it
    // locally against staging instead. The same #VERIFY as the sweep config,
    // for the same reason.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'e2e-prod', use: { ...devices['Desktop Chrome'] } }],
})
