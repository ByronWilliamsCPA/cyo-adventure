import { expect } from '@playwright/test'

export const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:8000'

/**
 * Fails fast with an actionable message when the real stack is not running.
 * The backend must be started in ENVIRONMENT=local with the dev seed applied;
 * see the "Real-backend e2e" section of frontend/README.md.
 */
export async function requireBackend(): Promise<void> {
  let ready = false
  try {
    const res = await fetch(`${BACKEND}/health/ready`)
    ready = res.ok
  } catch {
    ready = false
  }
  expect(
    ready,
    `Real backend not ready at ${BACKEND}. Start Postgres, run scripts/seed_dev_data.py, ` +
      'and start uvicorn (ENVIRONMENT=local) before npm run test:e2e:real.'
  ).toBe(true)
}
