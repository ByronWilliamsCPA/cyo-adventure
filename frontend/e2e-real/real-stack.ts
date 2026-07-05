import { expect } from '@playwright/test'

export const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:8000'

/**
 * Fails fast with an actionable message when the real stack is not running.
 * The backend must be started in ENVIRONMENT=local with the dev seed applied;
 * see the "Real-backend e2e" section of frontend/README.md.
 */
export async function requireBackend(): Promise<void> {
  let ready = false
  let detail = ''
  try {
    // A hung backend must not block for the full Playwright timeout; a 5s
    // deadline keeps the "fails fast" promise even when the TCP connect
    // succeeds but /health/ready never responds (e.g. an exhausted DB pool).
    const res = await fetch(`${BACKEND}/health/ready`, {
      signal: AbortSignal.timeout(5000),
    })
    ready = res.ok
    if (!ready) detail = ` (HTTP ${res.status})`
  } catch (err) {
    // Surface the underlying cause (DNS failure, connection refused, timeout)
    // so a wrong E2E_BACKEND_URL is distinguishable from a stopped backend.
    ready = false
    detail = ` (${err instanceof Error ? err.message : String(err)})`
  }
  expect(
    ready,
    `Real backend not ready at ${BACKEND}${detail}. Start Postgres, run ` +
      'scripts/seed_dev_data.py, and start uvicorn (ENVIRONMENT=local) before ' +
      'npm run test:e2e:real.'
  ).toBe(true)
}
