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
  // production on every run, so CI execution is default-deny: any workflow that
  // picks this config up fails fast here rather than quietly authenticating.
  // Exactly one audited override exists, .github/workflows/e2e-prod.yml, which
  // runs the tier on a daily cron and clears CI to an empty string for the
  // test-run step specifically to pass this guard (an owner-directed decision,
  // recorded in docs/planning/test-traceability-matrix.md). The guard is
  // therefore still the enforcement point; it is simply no longer absolute.
  // #VERIFY: this check is the only runtime enforcement, so any NEW workflow
  // that clears or unsets CI is an unreviewed second override. Audit with
  // `grep -rn "CI:" .github/workflows/` and expect exactly one hit for this
  // tier.
  if (process.env.CI) {
    throw new Error(
      'e2e-prod must not run in CI: every test authenticates a real account ' +
        'against live production. The only sanctioned exception is ' +
        '.github/workflows/e2e-prod.yml, which clears CI deliberately (see ' +
        'frontend/README.md).'
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
