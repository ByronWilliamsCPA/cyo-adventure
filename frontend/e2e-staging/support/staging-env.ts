import { existsSync } from 'node:fs'
import path from 'node:path'

import { config as loadDotenv } from 'dotenv'

// Populated either by CI (the `staging` GitHub Environment's secrets, wired
// in .github/workflows/e2e-staging.yml) or, for a local manual run, by a
// .env.e2e-staging file (gitignored; see .env.e2e-staging.example). Loading
// here is a no-op if the vars are already set in process.env.
const localEnvFile = path.resolve(import.meta.dirname, '../../.env.e2e-staging')
if (existsSync(localEnvFile)) {
  loadDotenv({ path: localEnvFile })
}

/**
 * Resolves the staging frontend's base URL. Deliberately has no hardcoded
 * fallback (unlike e2e-prod's PROD_BASE_URL): this repo has no frontend
 * deploy workflow of its own (homelab-infra builds and ships the frontend
 * image on its own cadence), so there is no single "the staging URL" this
 * codebase can assume. Whoever wires the workflow's secrets supplies it.
 */
export function requireStagingBaseUrl(): string {
  const url = process.env.E2E_STAGING_BASE_URL
  if (!url) {
    throw new Error(
      'E2E_STAGING_BASE_URL not set. Point it at the already-deployed staging ' +
        'frontend (see docs/testing/README.md); copy frontend/.env.e2e-staging.example ' +
        'to frontend/.env.e2e-staging for a local run, or set the staging GitHub ' +
        "Environment's secret for CI."
    )
  }
  return url
}

/**
 * Test account identities seeded by scripts/seed_staging.py. The emails
 * match that script's SEED_GUARDIAN_EMAIL / SEED_ADMIN_EMAIL defaults (see
 * .env.staging.example) so a fresh checkout works with zero extra config;
 * override via env if a project's seed ever uses different addresses.
 *
 * Passwords have no default: scripts/seed_staging.py intentionally never
 * persists SEED_GUARDIAN_PASSWORD / SEED_ADMIN_PASSWORD anywhere (see that
 * script's docstring), so whatever value was used at seed time must be
 * supplied here separately as E2E_STAGING_GUARDIAN_PASSWORD /
 * E2E_STAGING_ADMIN_PASSWORD, matching what the account was actually seeded
 * with.
 */
export function requireStagingCredentials(role: 'guardian' | 'admin'): {
  email: string
  password: string
} {
  const email =
    process.env[`E2E_STAGING_${role.toUpperCase()}_EMAIL`] ||
    (role === 'guardian' ? 'cyo-test-guardian@example.com' : 'cyo-test-admin@example.com')
  const password = process.env[`E2E_STAGING_${role.toUpperCase()}_PASSWORD`]
  if (!password) {
    throw new Error(
      `E2E_STAGING_${role.toUpperCase()}_PASSWORD not set. This must match the ` +
        `password scripts/seed_staging.py used to create ${email}.`
    )
  }
  return { email, password }
}
