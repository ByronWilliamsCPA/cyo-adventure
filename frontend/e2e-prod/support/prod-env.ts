import { existsSync } from 'node:fs'
import path from 'node:path'

import { config as loadDotenv } from 'dotenv'

// Populated either by `infisical run --env=prod -- npm run test:e2e:prod`
// (preferred: nothing touches disk) or, when Infisical is unavailable, by a
// local .env.e2e-prod file (gitignored; see .env.e2e-prod.example). Loading
// here is a no-op if the vars are already set in process.env, so the
// Infisical path always wins when both are present.
const localEnvFile = path.resolve(import.meta.dirname, '../../.env.e2e-prod')
if (existsSync(localEnvFile)) {
  loadDotenv({ path: localEnvFile })
}

export const PROD_BASE_URL = process.env.E2E_PROD_BASE_URL || 'https://cyo.williamshome.family'

/**
 * Fails fast with an actionable message when the prod test account
 * credentials are not available, rather than letting every test in the
 * suite fail individually with a confusing login-form error.
 */
export function requireProdCredentials(): { email: string; password: string } {
  // #CRITICAL: security: this tier authenticates a real account against live
  // production on every run. It must never execute unattended in CI; fail
  // fast and loudly rather than relying solely on the config file never
  // being wired into a workflow.
  // #VERIFY: this check is the only runtime enforcement of that constraint.
  if (process.env.CI) {
    throw new Error(
      'e2e-prod must never run in CI: every test authenticates a real account ' +
        'against live production. This tier is manual-only (see frontend/README.md).'
    )
  }

  const email = process.env.E2E_PROD_TEST_EMAIL
  const password = process.env.E2E_PROD_TEST_PASSWORD
  if (!email || !password) {
    const missing = [
      !email ? 'E2E_PROD_TEST_EMAIL' : null,
      !password ? 'E2E_PROD_TEST_PASSWORD' : null,
    ]
      .filter(Boolean)
      .join(' / ')
    throw new Error(
      `${missing} not set. Run via ` +
        '`infisical run --env=prod -- npm run test:e2e:prod`, or copy ' +
        'frontend/.env.e2e-prod.example to frontend/.env.e2e-prod and fill it in.'
    )
  }
  return { email, password }
}
