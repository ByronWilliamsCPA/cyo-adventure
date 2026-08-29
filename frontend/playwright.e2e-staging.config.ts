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
 * The `json` reporter writes outside `frontend/test-results/` on purpose.
 * Two reasons, both still live now that the wholesale trace upload of that
 * directory has been deleted from e2e-staging.yml (see the #CRITICAL block
 * on `use.trace` below): Playwright CLEARS its output directory at the start
 * of every invocation, and this workflow runs a second Playwright
 * invocation (the sweep config) in the same job, so a report written there
 * would be wiped before the alert-composing step reads it; and
 * `frontend/test-results/` is the directory the narrow leaked-grant ledger
 * artifact is still uploaded from, so keeping the report out of it means no
 * future widening of that path can pick the report up. `list` stays first so
 * human-readable CI console output is unchanged.
 *
 * `PLAYWRIGHT_JSON_REPORT_PATH` is read by all four Playwright configs in
 * this repo (this one, playwright.config.ts, playwright.e2e-staging-sweep.config.ts,
 * playwright.e2e-prod.config.ts), each with its own distinct default when the
 * variable is unset, which is why e2e-staging.yml sets it NOWHERE today: the
 * main tier (this config, default `e2e-staging.json`) and the same job's
 * `grant_sweep` step (playwright.e2e-staging-sweep.config.ts, default
 * `e2e-staging-sweep.json`) already write to different paths without any env
 * override. Do not "simplify" that by adding a single `PLAYWRIGHT_JSON_REPORT_PATH`
 * at JOB level in e2e-staging.yml: a job-level `env:` applies to both steps
 * identically, so it would collide the main-tier and sweep reports into one
 * file, silently breaking whichever step's alert-composing read happens
 * second. e2e-real-nightly.yml needs and correctly uses a STEP-level override
 * instead (its two Playwright steps target the same config, not two
 * different ones, so they would otherwise share this file's single default).
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
    // #CRITICAL: security: trace/screenshot/video are OFF for the whole
    // config, deliberately at the TOP LEVEL rather than on one project.
    // THIS REPOSITORY IS PUBLIC, so any workflow artifact is downloadable by
    // anyone for its whole retention window, and both projects below handle
    // the real staging guardian bearer: `staging-auth-setup` performs the
    // tier's only two real sign-ins (so its trace would carry the sign-in
    // POST body, the DOM of the sign-in form, and the resulting Supabase
    // session), and `e2e-staging` runs every spec against a restored
    // `storageState` (so every request it makes carries that same bearer in
    // an `Authorization` header, plus the device-grant token its specs
    // mint). Scoping this to the setup project only would leave the second,
    // larger surface exposed, which is why it is not scoped.
    //
    // This matches playwright.e2e-staging-sweep.config.ts, the sibling
    // config for the same staging target, which has pinned the same three
    // off for the same reason since it was written. `screenshot` and `video`
    // are Playwright defaults today; they are pinned here so turning either
    // on later has to be a deliberate edit to a line carrying this comment.
    //
    // Debuggability was weighed, not ignored: `list`'s console output plus
    // the `json` report (read by scripts/extract-failing-specs.mjs into the
    // alert issue) name the failing spec and its assertion, and a staging
    // failure is reproducible locally against the same target. That is what
    // the sweep tier has always run on.
    // #VERIFY: do not set any of these to a capturing value to debug a red
    // staging run, and do not add a workflow step that uploads
    // `frontend/test-results/` wholesale (see .github/workflows/e2e-staging.yml,
    // where that step was deleted and the prohibition is restated).
    trace: 'off',
    screenshot: 'off',
    video: 'off',
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
