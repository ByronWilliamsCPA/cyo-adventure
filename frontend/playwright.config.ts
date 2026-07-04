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
    env: {
      VITE_SUPABASE_URL: 'https://example.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'dummy-anon-key-for-e2e-build',
    },
  },
  projects: [
    { name: 'chromium', testDir: './e2e', use: { ...devices['Desktop Chrome'] } },
    {
      // Real-backend smoke tier: zero route mocks; requires the local stack
      // (Postgres + seeded uvicorn on :8000). Run via npm run test:e2e:real.
      name: 'real-backend',
      testDir: './e2e-real',
      fullyParallel: false,
      retries: process.env.CI ? 1 : 0,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
