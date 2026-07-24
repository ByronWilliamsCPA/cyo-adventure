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
 */
export default defineConfig({
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
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
      dependencies: ['real-backend-setup'],
      // full-pipeline-real.spec.ts drives a real RQ worker end-to-end; it runs
      // in its own `real-backend-pipeline` project (npm run test:e2e:real:pipeline)
      // that additionally requires a running generation worker, so this project
      // must not pick it up. Every other e2e-real spec has no such dependency
      // and stays here.
      testIgnore: ['full-pipeline-real.spec.ts'],
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
      // #CRITICAL: external-resources: this project is meaningless without a
      // live worker consuming the "generation" queue; the spec's poll deadline
      // fails with an explicit "worker not running" message if none is up.
      // #VERIFY: the nightly job must start the worker before invoking this.
      name: 'real-backend-pipeline',
      testDir: './e2e-real',
      testMatch: /full-pipeline-real\.spec\.ts/,
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
  ],
})
