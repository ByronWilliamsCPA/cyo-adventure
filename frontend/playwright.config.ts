import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E config. Tests run against the built app served by `vite preview`.
 * The reader API is mocked per-test via route interception; no backend is required.
 *
 * Service workers are blocked: VitePWA's workbox runtime-caches `/api`, so an
 * active service worker would make the API fetch itself and bypass Playwright's
 * page.route mocks (the request would reach the preview server and 500). The
 * offline behavior these tests exercise is the app's IndexedDB story cache and
 * local state machine (see context.setOffline in reader.spec.ts), not the PWA
 * shell cache, so blocking the service worker does not weaken the coverage.
 */
export default defineConfig({
  testDir: './e2e',
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
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
