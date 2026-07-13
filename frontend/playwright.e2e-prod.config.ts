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
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: PROD_BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'e2e-prod', use: { ...devices['Desktop Chrome'] } }],
})
