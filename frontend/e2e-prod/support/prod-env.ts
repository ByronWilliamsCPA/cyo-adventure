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
  const email = process.env.E2E_PROD_TEST_EMAIL
  const password = process.env.E2E_PROD_TEST_PASSWORD
  if (!email || !password) {
    throw new Error(
      'E2E_PROD_TEST_EMAIL / E2E_PROD_TEST_PASSWORD are not set. Run via ' +
        '`infisical run --env=prod -- npm run test:e2e:prod`, or copy ' +
        'frontend/.env.e2e-prod.example to frontend/.env.e2e-prod and fill it in.'
    )
  }
  return { email, password }
}
