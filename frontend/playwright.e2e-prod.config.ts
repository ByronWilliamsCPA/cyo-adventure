import { defineConfig, devices } from '@playwright/test'

import { PROD_BASE_URL } from './e2e-prod/support/prod-env'

/**
 * Third e2e tier, deliberately kept in its own config file rather than a
 * project entry in playwright.config.ts: this one targets LIVE production,
 * not a locally-built preview server, so it has no webServer block, and it
 * must never be wired into CI (every run authenticates a real account
 * against a live system). Run manually via `npm run test:e2e:prod`; see
 * frontend/.env.e2e-prod.example for credential setup.
 */
export default defineConfig({
  testDir: './e2e-prod',
  // Headroom for the rate-limit backoff in e2e-prod/support/rate-limit.ts: a
  // navigation or sign-in that trips the prod 60 rpm/IP limit waits out an
  // exponential backoff (2s, 4s) and retries, which can add ~6s on top of the
  // normal page-load budget. Kept at the tier level rather than per-test so the
  // beforeAll sign-in (which also retries) shares the headroom.
  timeout: 60_000,
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
