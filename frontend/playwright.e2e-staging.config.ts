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
 *
 * The `json` reporter writes outside `frontend/test-results/` on purpose:
 * that directory is uploaded wholesale as a public artifact on Playwright
 * failure (see e2e-staging.yml's "Upload Playwright trace on Playwright
 * failure" step, gated on THIS repository being public) and this same
 * workflow's own alert-composing step reads the JSON report, so nothing it
 * reads may live in the uploaded directory. `list` stays first so
 * human-readable CI console output is unchanged.
 */
const JSON_REPORT_PATH =
  process.env.PLAYWRIGHT_JSON_REPORT_PATH ?? 'playwright-json-report/e2e-staging.json'

export default defineConfig({
  testDir: './e2e-staging',
  // Left at 30s, unlike the prod tier's deliberately-sized 45s. The arithmetic
  // is different, not overlooked: this tier has 28 timeout-bearing units (20
  // tests plus 6 beforeAll hooks, plus the 2 `staging-auth-setup` tests below),
  // so a fully-hung first pass costs 840s against the workflow's 1500s budget,
  // with room for checkout, npm ci, playwright install, and the separate 60s
  // device-grant sweep the same job runs afterwards. The prod tier exceeded
  // its (then-identical 900s) budget on the first pass, which is why only
  // that one was resized.
  //
  // The 6 beforeAll hooks no longer sign in (they load a pre-authenticated
  // `storageState` instead, see `staging-auth-setup` below); the tier's only
  // two sign-ins now live in that setup project's own 2 tests, which is why
  // this recount adds 2 units rather than replacing 5. See
  // `e2e-staging/auth.setup.ts` for the full rationale: consolidating every
  // sign-in into one setup project, run once per role, is what stops the
  // main tier and the separate sweep step from competing for the same
  // server-side per-IP rate-limit window across two `npm run` invocations.
  //
  // Per spec, so the next recount starts from a diff rather than a re-read:
  // staging-auth-setup 2 tests (the tier's only two sign-ins), guardian-admin-smoke
  // 9 tests + 2 hooks, kid-library-smoke 3 + 1, moderation-qa-invisibility 4 + 2,
  // kws-public-urls 4 + 1. `afterAll` teardown hooks are deliberately outside
  // this model (there are 6 of them today); they are bounded cleanup that runs
  // after the units they follow, and the headroom above absorbs them.
  //
  // Adding a spec? Recount the units and redo this arithmetic plus the retry
  // note below; the workflow budget has now been raised twice, 15 -> 20
  // minutes when moderation-qa-invisibility.spec.ts added 6 units, and
  // 20 -> 25 when kws-public-urls.spec.ts added 5.
  timeout: 30_000,
  fullyParallel: false,
  // Kept at 1, where the prod tier deliberately uses 0. Both are correct now
  // that e2e-support/rate-limit.ts absorbs rate limits inside the helpers: a
  // 429 is retried in-test and never reaches Playwright, so this retry only
  // ever replays a genuine flake, not a limiter that a replay would feed.
  // Worst case (every unit hanging on both attempts) is 1680s, which exceeds
  // the 1500s job budget by six units; such a run is already reporting failure
  // on every test, so the job timeout truncating its tail costs nothing, and
  // sizing the budget for that pathology would only delay the red signal.
  retries: process.env.CI ? 1 : 0,
  // #EDGE: concurrency: e2e-support/rate-limit.ts paces navigations through
  // per-worker module state, so one instance paces a whole run only while this
  // stays at 1. Multi-worker would let each worker pace independently and the
  // aggregate rate could still exceed the 60 rpm/IP ceiling.
  // #VERIFY: raising this requires moving the pacing floor to shared state.
  workers: 1,
  reporter: [['list'], ['json', { outputFile: JSON_REPORT_PATH }]],
  use: {
    baseURL: requireStagingBaseUrl(),
    trace: 'retain-on-failure',
  },
  projects: [
    {
      // Signs in as the seeded guardian, then the seeded admin, and writes
      // each session's `storageState` to `e2e-staging/.auth/`
      // (`e2e-staging/support/auth-storage.ts`). Matched by `testMatch`, not
      // the default spec/test glob, so `e2e-staging` below never picks
      // `auth.setup.ts` up as an ordinary test; mirrors the existing
      // `real-backend-setup` pattern in `playwright.config.ts`.
      name: 'staging-auth-setup',
      testDir: './e2e-staging',
      testMatch: /auth\.setup\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'e2e-staging',
      dependencies: ['staging-auth-setup'],
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
