import { defineConfig, devices } from '@playwright/test'

import { requireStagingBaseUrl } from './e2e-staging/support/staging-env'

/**
 * Fourth e2e tier, targeting the shared STAGING Supabase project (see
 * docs/testing/README.md for why dev and staging share one backend on the
 * Supabase free plan). Kept in its own config file, like
 * playwright.e2e-prod.config.ts: no webServer block, since this targets an
 * already-deployed staging frontend, not a locally-built preview server.
 * Unlike the prod tier, this one IS intended to run in CI (scheduled +
 * manual dispatch, see .github/workflows/e2e-staging.yml): the staging
 * project holds only the disposable fixtures scripts/seed_staging.py
 * creates, never real family data.
 */
export default defineConfig({
  testDir: './e2e-staging',
  // Left at 30s, unlike the prod tier's deliberately-sized 45s. The arithmetic
  // is different, not overlooked: this tier has 21 timeout-bearing units (16
  // tests plus 5 beforeAll sign-in hooks), so a fully-hung first pass costs
  // 630s against the workflow's 1200s budget, with room for checkout, npm ci,
  // and playwright install. The prod tier exceeded its (then-identical 900s)
  // budget on the first pass, which is why only that one was resized. Adding
  // a spec? Recount the units and redo this arithmetic plus the retry note
  // below; the workflow budget was already raised once (15 -> 20 minutes)
  // when moderation-qa-invisibility.spec.ts added 6 units.
  timeout: 30_000,
  fullyParallel: false,
  // Kept at 1, where the prod tier deliberately uses 0. Both are correct now
  // that e2e-support/rate-limit.ts absorbs rate limits inside the helpers: a
  // 429 is retried in-test and never reaches Playwright, so this retry only
  // ever replays a genuine flake, not a limiter that a replay would feed.
  // Worst case (every unit hanging on both attempts) is 1260s, which exceeds
  // the 1200s job budget by one unit; such a run is already reporting failure
  // on every test, so the job timeout truncating its tail costs nothing, and
  // sizing the budget for that pathology would only delay the red signal.
  retries: process.env.CI ? 1 : 0,
  // #EDGE: concurrency: e2e-support/rate-limit.ts paces navigations through
  // per-worker module state, so one instance paces a whole run only while this
  // stays at 1. Multi-worker would let each worker pace independently and the
  // aggregate rate could still exceed the 60 rpm/IP ceiling.
  // #VERIFY: raising this requires moving the pacing floor to shared state.
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: requireStagingBaseUrl(),
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'e2e-staging', use: { ...devices['Desktop Chrome'] } }],
})
