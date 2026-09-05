import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E config. Tests run against the built app served by `vite preview`.
 *
 * Two tiers, as separate projects:
 * - `chromium` (testDir `./e2e`): the reader API is mocked per-test via route
 *   interception; no backend is required.
 * - `real-backend` (testDir `./e2e-real`): zero route mocks; requires the
 *   local stack (Postgres + seeded uvicorn on :8000) and reaches it through
 *   the `preview` proxy configured in vite.config.ts. Run via
 *   `npm run test:e2e:real`.
 *
 * Service workers are blocked: VitePWA's workbox runtime-caches `/api`, so an
 * active service worker would make the API fetch itself and bypass Playwright's
 * page.route mocks (the request would reach the preview server and 500). The
 * offline behavior these tests exercise is the app's IndexedDB story cache and
 * local state machine (see context.setOffline in reader.spec.ts), not the PWA
 * shell cache, so blocking the service worker does not weaken the coverage.
 *
 * #ASSUME: data-integrity: this is the SAME config file that backs `npm run test:e2e`
 * (`--project=chromium`), the mocked tier that `ci.yml`'s PR-blocking
 * `frontend-e2e` job runs on every PR, since that is also the config
 * `e2e-real-nightly.yml` selects (`--project=real-backend`) for the JSON
 * reporter added here (task A7-i). Adding the `json` reporter alongside
 * `list` therefore also changes what that required PR gate writes to disk;
 * `list` is kept unchanged so its human-readable console output is
 * identical, and the JSON file is written outside `frontend/test-results/`
 * (never uploaded, never read by ci.yml) so it has no other observable
 * effect on that job. This was a deliberate scope decision, not a side
 * effect; see the task report for the stated blast radius.
 * #VERIFY: `ci.yml`'s `frontend-e2e` job still passes/fails purely on
 * Playwright's own exit code, unaffected by whether the JSON file was
 * written.
 *
 * The default `PLAYWRIGHT_JSON_REPORT_PATH` below is shared by every project
 * in this file. `e2e-real-nightly.yml` runs Playwright against this config
 * TWICE in one job (`--project=real-backend`, then
 * `--project=real-backend-pipeline`); a single fixed output path would let
 * the second run silently overwrite the first run's report before anything
 * reads it. That workflow sets `PLAYWRIGHT_JSON_REPORT_PATH` to a distinct
 * path for each of the two steps so both reports survive; this default here
 * only matters for `npm run test:e2e` / `test:e2e:real` / `test:e2e:real:pr-smoke` /
 * `test:e2e:mobile` / `test:e2e:cross-device` invocations (single run each)
 * and local use.
 */
const JSON_REPORT_PATH =
  process.env.PLAYWRIGHT_JSON_REPORT_PATH ?? 'playwright-json-report/report.json'

/**
 * Playwright deletes its entire configured `outputDir` at the START of every
 * `playwright test` invocation, unconditionally, including subdirectories a
 * PRIOR invocation just wrote (traces, screenshots, videos); this is
 * independent of the `PLAYWRIGHT_JSON_REPORT_PATH` collision handled above,
 * which only protects the JSON report file, not `test-results/`. A job that
 * runs this config more than once in sequence (`accessibility-compliance-
 * weekly.yml`: `chromium` then `usersim-a11y`; `e2e-real-nightly.yml`:
 * `real-backend`, then `real-backend-pipeline`, then
 * `real-backend-pipeline-negative`, then `usersim-real`, the last
 * of which runs on `!cancelled()` regardless of the earlier two's outcome)
 * would otherwise have a later invocation silently wipe an earlier failing
 * invocation's evidence before the job's own "upload on failure" step ever
 * reads `frontend/test-results/`. Task B3b review, Important 1.
 *
 * The fix is per-project `outputDir` below (not a per-workflow-step CLI
 * `--output` flag): it is a property of the PROJECT, so it protects every
 * current and future caller of that project automatically, including a
 * workflow step nobody has written yet, rather than depending on each new
 * caller remembering to pass a flag the way `PLAYWRIGHT_JSON_REPORT_PATH`
 * requires each workflow step to do.
 *
 * `chromium` also gets its own `outputDir` (not the bare default), even
 * though today it is always the FIRST invocation in any job that runs a
 * second project from this file, so nothing has written there yet for it to
 * wipe. Task B3b second review, F2: the bare default is `test-results/`,
 * which is a PARENT directory of every isolated project dir below
 * (`test-results/usersim-a11y`, etc.), so "chromium always runs first" was
 * an invariant that lived only in this comment, not in anything that could
 * fail if it stopped being true; a later `chromium` step appended after one
 * of those projects (e.g. a future `--project=chromium e2e/keyboard-nav.spec.ts`
 * step added after the I7 step in the weekly job) would silently delete the
 * earlier project's evidence with nothing to catch it.
 * `tests/unit/test_playwright_output_dir_isolation.py` now asserts this
 * structurally instead of by convention: every project actually invoked as a
 * separate step within the same job must resolve to a distinct, non-nesting
 * `outputDir`. `real-backend-setup` is the one project left on the bare
 * default: it is a `dependencies: [...]` target that Playwright always runs
 * INSIDE its dependent's own invocation (never as its own separate workflow
 * step), so it never gets the chance to wipe a sibling's evidence the way a
 * separately-invoked project could; the contract test's project list is
 * built from the workflows' actual `run:` commands, so a dependency-only
 * project is correctly never a member of it.
 */

export default defineConfig({
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['json', { outputFile: JSON_REPORT_PATH }]],
  use: {
    baseURL: 'http://localhost:4173',
    serviceWorkers: 'block',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // The guardian lazy chunk (supabaseClient.ts) throws at module load unless
    // these are defined at build time; with dummy values it renders the login
    // flow (and thus the unauthenticated redirect) instead of the missing-env
    // errorElement. The kid surface never imports supabaseClient, so the values
    // are inert there. They are not real credentials.
    //
    // VITE_API_URL is forced empty so a developer's local .env.local (which may
    // set VITE_API_URL=http://localhost:8000 for `npm run dev`) cannot leak into
    // this tier's PROD build. useApi.ts resolves the axios baseURL as
    // `import.meta.env.PROD ? VITE_API_URL || '/api' : '/api'`; an absolute base
    // would make the browser call :8000 directly, bypassing both the preview
    // proxy and Playwright's same-origin `**/api/v1/**` route mocks (67/75 fail).
    // The empty string means the build always uses the `/api` fallback. This is
    // the enforcement of the README warning "Never set VITE_API_URL when building
    // for this tier"; the mocked tier must stay hermetic regardless of .env.local.
    env: {
      VITE_SUPABASE_URL: 'https://example.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'dummy-anon-key-for-e2e-build',
      VITE_API_URL: '',
    },
  },
  projects: [
    {
      name: 'chromium',
      testDir: './e2e',
      // See the JSON_REPORT_PATH header comment above (Task B3b second
      // review, F2): an explicit, non-default outputDir so this project is a
      // SIBLING of every other project's isolated dir under `test-results/`,
      // never its parent.
      outputDir: 'test-results/chromium',
      // P4-1: visual.spec.ts asserts pixel-exact screenshot baselines that are
      // captured on the Linux CI runner. A developer host (macOS/Windows/WSL)
      // renders fonts differently, so those baselines drift by sub-pixel anti-
      // aliasing noise off-CI and every visual test "fails" locally for no real
      // reason. Ignore them when CI is unset so a local `npm run test:e2e` is
      // clean; CI (GitHub Actions sets CI=true) still runs and enforces them,
      // and update-visual-snapshots.yml still regenerates them. Structural
      // gating, not a per-test skip marker. Run locally with
      // `CI=1 npm run test:e2e -- visual.spec.ts`.
      //
      // cross-device.spec.ts is excluded too: it runs the same checks as
      // responsive.spec.ts's "@ desktop" block, once per real device/browser
      // project (see the cross-device-*/cross-browser-* projects below), and
      // would just be a redundant third desktop-chrome pass here.
      testIgnore: process.env.CI
        ? ['cross-device.spec.ts']
        : ['visual.spec.ts', 'cross-device.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Mobile-web viewport tier: the same mocked e2e specs, but at an iPhone
      // viewport, so fluid layouts and the no-breakpoint stylesheets are
      // exercised at a real narrow width. Run: npm run test:e2e:mobile.
      //
      // Runs on real WebKit: devices['iPhone 13'] defaults to WebKit, the
      // engine iOS Safari and the R2 Capacitor WKWebView actually use, and
      // WebKit's Linux system libraries are now installed here. This tier
      // still does not emulate env(safe-area-inset-*) (A8); that needs a
      // real device.
      name: 'mobile-safari',
      testDir: './e2e',
      testMatch: /mobile-viewport\.spec\.ts/,
      use: { ...devices['iPhone 13'] },
    },
    {
      // Runs scripts/reset_e2e_real_state.py (via e2e-real/_reset.setup.ts)
      // before the real-backend project's specs, so a second consecutive
      // `npm run test:e2e:real` is deterministic (Phase 4.2): it reverts the
      // seeded review story's real approval and clears reading_state rows a
      // prior run pinned at an ending. Matched by testMatch, not the default
      // spec/test glob, so `real-backend` below never picks this file up as
      // an ordinary test; `chromium` has no backend to reset and does not
      // depend on either project.
      name: 'real-backend-setup',
      testDir: './e2e-real',
      testMatch: /_reset\.setup\.ts/,
    },
    {
      // Real-backend smoke tier: zero route mocks; requires the local stack
      // (Postgres + seeded uvicorn on :8000). Run via npm run test:e2e:real.
      name: 'real-backend',
      testDir: './e2e-real',
      // See the JSON_REPORT_PATH header comment above (Important 1): isolates
      // this project's trace/screenshot output from the other Playwright
      // invocations e2e-real-nightly.yml runs in the same job.
      outputDir: 'test-results/real-backend',
      dependencies: ['real-backend-setup'],
      // full-pipeline-real.spec.ts, full-pipeline-negative-real.spec.ts and
      // connections-enforcement-real.spec.ts all drive a real RQ worker
      // end-to-end (the last to mint a fresh catalog-visible storybook); they
      // run in their own `real-backend-pipeline` project (npm run
      // test:e2e:real:pipeline) that additionally requires a running
      // generation worker, so this project must not pick any of them up.
      // Every other e2e-real spec has no such dependency and stays here.
      //
      // full-pipeline-negative-real.spec.ts was missing from this list while
      // being just as worker-dependent as its positive twin, so the nightly
      // ran it in THIS project, which executes before the workflow starts the
      // worker. It therefore failed on every run with its own
      // "worker does not appear to be consuming the generation queue"
      // message: an accurate report of a condition the job's own ordering
      // guaranteed. Match worker-dependence, not filename similarity, when
      // adding specs here.
      testIgnore: [
        'full-pipeline-real.spec.ts',
        'full-pipeline-negative-real.spec.ts',
        'connections-enforcement-real.spec.ts',
      ],
      fullyParallel: false,
      // #EDGE: data-integrity: the approve test mutates the database, so a CI
      // retry after a post-mutation failure re-enters an already-approved
      // state and fails with a different symptom; read the FIRST attempt's
      // error when diagnosing.
      // #VERIFY: approval-flow.spec.ts asserts persisted state after reload.
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Full-pipeline tier: drives a story from a guardian concept through a
      // REAL RQ generation worker (mock provider) to in_review, then admin
      // approve/publish, then a kid read. Kept in its own project because it
      // is the only e2e-real spec that requires the generation worker
      // (`python -m cyo_adventure.generation.worker_main`) running alongside
      // the seeded uvicorn; the worker is not part of the default local stack,
      // so bundling this into `real-backend` would make that whole tier fail
      // wherever no worker is up. Same deterministic reset dependency as
      // `real-backend` (the reset also purges worker-generated storybooks so
      // consecutive runs stay clean). Run via npm run test:e2e:real:pipeline.
      // connections-enforcement-real.spec.ts joins this project (not
      // `real-backend`) for the same reason: it needs a fresh CATALOG-visible
      // storybook, and approving one to catalog visibility requires generating
      // it first (no seeded story is catalog-visible), which needs the same
      // live worker as full-pipeline-real.spec.ts.
      // #CRITICAL: external-resources: this project is meaningless without a
      // live worker consuming the "generation" queue; each spec's poll
      // deadline fails with an explicit "worker not running" message if none
      // is up.
      // #VERIFY: the nightly job must start the worker before invoking this.
      name: 'real-backend-pipeline',
      testDir: './e2e-real',
      // full-pipeline-negative-real.spec.ts is deliberately NOT matched here
      // even though it is just as worker-dependent: see the
      // `real-backend-pipeline-negative` project below for why the two
      // directions cannot share one worker process.
      testMatch: /(full-pipeline-real|connections-enforcement-real)\.spec\.ts/,
      // See the JSON_REPORT_PATH header comment above (Important 1): isolates
      // this project's trace/screenshot output from the other Playwright
      // invocations e2e-real-nightly.yml runs in the same job.
      outputDir: 'test-results/real-backend-pipeline',
      dependencies: ['real-backend-setup'],
      fullyParallel: false,
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Full-pipeline tier, the BLOCKING direction (review finding S-5):
      // full-pipeline-negative-real.spec.ts drives the same real request ->
      // generate -> gate path as `real-backend-pipeline` above, but needs the
      // worker to serve the structurally invalid canned fixture
      // (CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid, core/config.py::
      // Settings.mock_story_fixture). That selector is a process-wide worker
      // setting, not a per-job one, and the positive specs need the default
      // `safe` fixture from the SAME queue, so one worker process cannot serve
      // both directions: for 37 consecutive nightlies (issue #290) this spec
      // ran under the positive tier's worker and failed with "expected a
      // HARD-BLOCK terminal status, got passed", an accurate report of a
      // condition the job's own wiring guaranteed. It therefore runs as its
      // own project, which .github/workflows/e2e-real-nightly.yml invokes
      // only AFTER stopping the positive worker and starting a second one
      // with the invalid fixture (npm run test:e2e:real:pipeline:negative).
      // Same reset dependency as its siblings, so a blocked run never sees a
      // stale worker-generated storybook from the positive tier.
      // #CRITICAL: external-resources: meaningless without a worker that was
      // started with CYO_ADVENTURE_MOCK_STORY_FIXTURE=invalid; against a
      // default worker the spec fails at its block assertion with an explicit
      // "is MOCK_STORY_FIXTURE=invalid set?" message, never a silent pass.
      // #VERIFY: e2e-real-nightly.yml's "Stop generation worker" step asserts
      // no worker_main process survives before the invalid-fixture worker
      // starts; two workers on the queue would make this project's outcome a
      // race.
      name: 'real-backend-pipeline-negative',
      testDir: './e2e-real',
      testMatch: /full-pipeline-negative-real\.spec\.ts/,
      // Own outputDir (tests/unit/test_playwright_output_dir_isolation.py):
      // this project is its own workflow step in the nightly job, so it must
      // not be able to wipe a sibling invocation's failure evidence.
      outputDir: 'test-results/real-backend-pipeline-negative',
      dependencies: ['real-backend-setup'],
      fullyParallel: false,
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // PR-path smoke tier (G4, Phase 7.4): the ONE fast, seeded, happy-path
      // real-backend spec promoted to run per-PR (npm run test:e2e:real:pr-smoke)
      // so developers get a full-stack signal without the whole `real-backend`
      // tier's cost. A dedicated project (not a `playwright test <file>`
      // positional filter) is deliberate: a filename filter can also filter the
      // `real-backend-setup` dependency out, silently skipping the deterministic
      // reset, whereas testMatch selects exactly this spec while keeping the
      // reset. kid-reads is a pure read happy-path: no state mutation, no
      // generation worker, no live LLM, so it stays fast and deterministic.
      // Run informational (non-blocking) in CI via e2e-real-pr-smoke.yml; this
      // same spec also runs under `real-backend` in the nightly (a spec may be
      // matched by more than one project).
      name: 'real-backend-pr-smoke',
      testDir: './e2e-real',
      testMatch: /kid-reads\.spec\.ts/,
      dependencies: ['real-backend-setup'],
      fullyParallel: false,
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
    // Cross-device/cross-browser tier (npm run test:e2e:cross-device): every
    // project below matches ONLY e2e/cross-device.spec.ts, not the full
    // ./e2e suite. That spec asserts structural properties (no page-level
    // horizontal overflow, a lone grid item filling its row) rather than
    // pixel-exact screenshots, so it tolerates the font/rendering
    // differences between engines; the full mocked suite above already
    // covers Desktop Chrome behavior and isn't worth re-running under every
    // engine. `devices[...]` picks each profile's real-world browser engine
    // (iPad/iPhone default to webkit, matching actual Mobile Safari), so
    // this is the only tier that exercises non-Chromium engines at all.
    // #ASSUME: external-resources: requires `playwright install firefox
    // webkit` in addition to chromium (see ci.yml); a host with only
    // chromium installed fails these four projects with a clear
    // "Executable doesn't exist" error, not a silent skip.
    // #VERIFY: ci.yml's "Install Playwright browsers" step installs all
    // three engines before this tier runs.
    {
      name: 'cross-device-mobile',
      testDir: './e2e',
      testMatch: /cross-device\.spec\.ts/,
      use: { ...devices['Pixel 7'] },
    },
    {
      name: 'cross-device-tablet',
      testDir: './e2e',
      testMatch: /cross-device\.spec\.ts/,
      use: { ...devices['iPad (gen 7)'] },
    },
    {
      name: 'cross-browser-mobile-safari',
      testDir: './e2e',
      testMatch: /cross-device\.spec\.ts/,
      use: { ...devices['iPhone 14'] },
    },
    {
      name: 'cross-browser-firefox',
      testDir: './e2e',
      testMatch: /cross-device\.spec\.ts/,
      use: { ...devices['Desktop Firefox'] },
    },
    {
      // Engine-expansion tier (task B2, docs/testing/user-side-testing-module-
      // proposal-2026-08-27.md, "Engine expansion: `webkit-kid`"): the
      // reader/library/offline/read-aloud mocked specs on real WebKit at an
      // iPad viewport, the engine and form factor kids actually read on.
      // `cross-device-e2e.yml` already runs a WebKit profile, but only
      // against cross-device.spec.ts's structural checks; this is the first
      // project to run an actual kid reading journey on that engine.
      //
      // Nightly-only, informational (see webkit-kid.yml): this project is
      // deliberately NOT wired into any per-PR job and must never become a
      // required check. Scope decided by the task owner, not by this
      // project's own reasoning, and it is what keeps this addition out of
      // ADR-029's per-PR accessibility-scope constraint entirely.
      //
      // Spec selection is by explicit filename alternation, matching
      // `real-backend-pipeline`'s style above, not a directory or tag:
      //   - reader.spec.ts, reader-conflict.spec.ts, reader-flag.spec.ts,
      //     reader-go-back.spec.ts, reader-reload-resume.spec.ts,
      //     series-continue.spec.ts: every spec that drives the `/read/...`
      //     reader page (series-continue.spec.ts does too, for a
      //     series-continuation read). Offline behavior (IndexedDB-backed
      //     resume, the live-save 409 path, the queued-offline-choice
      //     replay) lives inside reader.spec.ts, reader-conflict.spec.ts,
      //     and reader-reload-resume.spec.ts already, so it needs no
      //     separate entry here.
      //   - library.spec.ts: the kid library page, including its offline
      //     shelf fallback (F-6b).
      //   - kid-read-aloud.spec.ts: the K7 read-aloud toggle.
      // Deliberately excluded: visual.spec.ts (pixel-exact baselines are
      // captured on the Linux CI runner and are engine-specific; a second
      // WebKit baseline set is out of scope for this task) and a11y.spec.ts
      // plus keyboard-nav.spec.ts (accessibility scope is ADR-029's to
      // widen, not this project's). cross-device.spec.ts and
      // mobile-viewport.spec.ts already run on WebKit elsewhere in this
      // file and are not kid reading journeys themselves.
      //
      // devices['iPad (gen 7)'], not a plain WebKit desktop profile: the
      // rationale is specifically iPads, matching cross-device-tablet's
      // profile above.
      //
      // Inherits this file's global `use.serviceWorkers: 'block'` like
      // every other mocked-tier project (see the file header comment): this
      // tier does not exercise the app's real service worker lifecycle, the
      // same way `chromium` and `mobile-safari` do not. It exercises
      // IndexedDB-backed offline persistence, reader replay, and speech
      // synthesis stubbing under WebKit, which is real coverage the fleet
      // did not have before this task.
      name: 'webkit-kid',
      testDir: './e2e',
      testMatch:
        /(reader|reader-conflict|reader-flag|reader-go-back|reader-reload-resume|series-continue|library|kid-read-aloud)\.spec\.ts/,
      use: { ...devices['iPad (gen 7)'] },
    },
    {
      // Leg A of the usersim tier (docs/testing/user-side-testing-module-
      // proposal-2026-08-27.md): a seeded random walk over the live app, one
      // walk per persona, asserting I1-I6 at every state. A separate project
      // + testDir, not a tag or grep filter, per this tier's own tier-
      // separation rule. Run via npm run test:e2e:usersim.
      //
      // Reuses this file's shared `webServer` and the top-level `use`
      // block, including `serviceWorkers: 'block'` (see the file header
      // comment): a live service worker would answer this tier's navigations
      // itself and bypass every page.route mock the walk installs, the same
      // SW-navigation-fallback defect class documented for the `chromium`
      // project above, so this tier must not opt back into service workers.
      //
      // This project shares the file's single JSON_REPORT_PATH default with
      // every other project here (see the header comment on
      // PLAYWRIGHT_JSON_REPORT_PATH); a scheduled usersim workflow that also
      // runs another project in the same invocation must set
      // PLAYWRIGHT_JSON_REPORT_PATH itself to avoid one run overwriting the
      // other's report, the same way e2e-real-nightly.yml already does for
      // the two real-backend projects. Not this task's concern to wire (a
      // later task owns the scheduled workflow); noted here so the next
      // reader does not have to rediscover the collision.
      // No per-project timeout override: this file's global 30s (see
      // `timeout: 30_000` above) is enough. An earlier draft of this walk
      // set timeout to 60_000 here, on the claim that the guardian persona
      // (the slowest of the three, since GuardianShell/AdminShell wrap an
      // Outlet and keep the sidebar's own links mounted across a route
      // change instead of detaching) hit the global 30s ceiling "well after
      // its own walk had already finished". That claim does not hold up: a
      // Playwright test does not keep its clock running after the test body
      // returns, so a timeout could only fire while the walk was genuinely
      // still awaiting something. The real mechanism was the networkidle
      // hang documented on settleAfterNavigation (support/walk-runner.ts;
      // originally inline in this file's walk.spec.ts before task B3a
      // extracted the shared walk loop) (the guardian/admin persistent SSE
      // connection never lets 'networkidle' resolve); once that was
      // replaced with the DOM-observed detach/loading-indicator settle used
      // today, repeated measured runs of the guardian and admin walks (the
      // two slowest personas) complete in 8-10s each, comfortably inside the
      // shared 30s, so the override was stale head-room left over from the
      // fixed bug, not a real need.
      //
      // testMatch narrows this project to the mocked walk spec plus the
      // reader-persona fixture check (task C2's `reader-personas.spec.ts`:
      // a non-browser referential-integrity check against the backend's
      // age bands, cheap enough to ride alongside the walk rather than earn
      // a fourth project). task B3a added a second, real-backend spec to
      // the same testDir; see `usersim-real` below, which stays scoped to
      // `walk-real.spec.ts` only since the reader-persona check needs no
      // real backend and would be pure duplication there. Matches the
      // filename-alternation convention `real-backend-pipeline`/
      // `webkit-kid` already use above rather than a tag or grep filter.
      name: 'usersim',
      testDir: './e2e-usersim',
      testMatch: /(walk|reader-personas)\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Real-backend leg of the usersim tier (task B3a, docs/testing/
      // testing-implementation-plan-2026-08-27.md): the SAME seeded walk as
      // `usersim` above, run against a real backend instead of route-mocked
      // fixtures, so the walk exercises genuine state transitions rather
      // than fixture responses. Shares walk-real.spec.ts's walk loop with
      // `usersim` via support/walk-runner.ts (parameterized, not forked);
      // only session setup (real device grant / real seeded bearers,
      // support/real-session-setup.ts's REAL_SESSION_SETUP) and the I5 canary values
      // (support/real-canaries.ts, real seeded rows) differ. Run via
      // npm run test:e2e:usersim:real.
      //
      // `dependencies: ['real-backend-setup']` matches `real-backend` and
      // `real-backend-pipeline` above: this walk needs the review story
      // back at a known `in_review` state (real-canaries.ts's I5
      // guardian-only canary lives on its moderation report) before it
      // starts, the same deterministic baseline every other real-backend
      // project depends on.
      //
      // Zero route mocks (unlike `usersim`): every `/api/v1/**` call this
      // walk makes reaches the real uvicorn `real-backend`/
      // `real-backend-pipeline` already require, matching
      // frontend/e2e-real/'s own convention. This project therefore must
      // run inside a job that has already brought up that real stack (see
      // .github/workflows/e2e-real-nightly.yml); it is meaningless run
      // alone against this file's own mocked-tier `webServer`, since that
      // server proxies `/api` to whatever `E2E_BACKEND_URL` points at (real
      // uvicorn, not a mock), and walk-real.spec.ts's own
      // `requireBackend()` call fails fast and legibly if nothing real is
      // listening there.
      //
      // Shares this project group's `PLAYWRIGHT_JSON_REPORT_PATH` collision
      // risk with every other project in this file (see the header comment
      // on JSON_REPORT_PATH): the nightly job sets a distinct path for this
      // step, the same way it already does for `real-backend` and
      // `real-backend-pipeline`.
      name: 'usersim-real',
      testDir: './e2e-usersim',
      testMatch: /walk-real\.spec\.ts/,
      // See the JSON_REPORT_PATH header comment above (Important 1): this
      // project runs LAST in e2e-real-nightly.yml's job, on `!cancelled()`
      // regardless of whether `real-backend` or `real-backend-pipeline`
      // above it failed, so without its own outputDir it would silently wipe
      // whichever of those two just wrote trace/screenshot evidence for a
      // failure the job's "Upload Playwright trace on failure" step has not
      // read yet.
      outputDir: 'test-results/usersim-real',
      dependencies: ['real-backend-setup'],
      fullyParallel: false,
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // I7 (task B3b): the same seeded walk as `usersim` above, plus an axe
      // scan of each newly-reached state signature (route + main heading),
      // widening the "one fixed mock state per surface" gap
      // docs/testing/coverage-matrix.md records for e2e/a11y.spec.ts.
      // Separate project/testDir/testMatch (never a tag or grep filter, per
      // this tier's own tier-separation rule), and separate from `usersim`
      // itself so I1-I6-only nightly runs (usersim.yml,
      // e2e-real-nightly.yml) never pick up the axe dependency or its extra
      // scan time.
      //
      // Run ONLY from .github/workflows/accessibility-compliance-weekly.yml
      // behind A11Y_EXTENDED=1 (owner decision, see walk-a11y.spec.ts's own
      // header comment); walk-a11y.spec.ts's own `test.skip` enforces that
      // flag requirement even if this project is ever invoked elsewhere.
      // Never wired into ci.yml's required frontend-e2e job (ADR-029).
      //
      // Reuses the mocked-tier fixtures (support/mocked-api.ts, shared with
      // `usersim`), not a real backend: matches the weekly workflow's
      // existing a11y.spec.ts step, which also scans the mocked-tier build.
      //
      // Shares this file's single JSON_REPORT_PATH default with every other
      // project here (see the header comment on PLAYWRIGHT_JSON_REPORT_PATH);
      // accessibility-compliance-weekly.yml sets a distinct path for this
      // step, the same way e2e-real-nightly.yml already does for its three
      // Playwright invocations.
      name: 'usersim-a11y',
      testDir: './e2e-usersim',
      testMatch: /walk-a11y\.spec\.ts/,
      // See the JSON_REPORT_PATH header comment above (Important 1): this
      // project runs SECOND in accessibility-compliance-weekly.yml's job,
      // right after `chromium` (e2e/a11y.spec.ts). Without its own outputDir
      // it would silently wipe stream 1's trace/screenshot evidence for a
      // failure before the job's "Upload Playwright report on failure" step
      // ever reads it.
      outputDir: 'test-results/usersim-a11y',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
