import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { type BrowserContext, expect } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

export const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:8000'

// Repo root: two directories up from this file (frontend/e2e-real/ -> repo root).
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')

/**
 * Reset real-backend e2e fixture state to a clean, idempotent baseline by
 * shelling out to ``scripts/reset_e2e_real_state.py`` (the single source of
 * truth for which tables/fields get reverted; see that script's module
 * docstring for the exact list). Shared by `_reset.setup.ts` (the
 * once-per-invocation baseline the `real-backend-setup` project runs before
 * any spec) and by any individual spec file's own `test.beforeAll`, so a file
 * that assumes the pristine seeded baseline (a specific story's status, an
 * empty review queue, zero open kid flags) stays correct regardless of what
 * ran earlier in the same full-suite invocation (Playwright fixtures/hooks
 * have no file-ordering guarantee across `real-backend`'s
 * `fullyParallel: false` but still shared-DB run).
 *
 * `execFileSync` (not `exec`) avoids shell interpolation of the fixed
 * argument list; `stdio: 'inherit'` surfaces the Python script's own
 * print/traceback directly in the Playwright run's console instead of
 * swallowing it into a buffer only shown on failure.
 *
 * #CRITICAL: external-resources: this assumes `uv` is on PATH and
 * `CYO_ADVENTURE_DATABASE_URL` (or the script's own settings default) points
 * at the disposable local Postgres; the Python script's own
 * `_require_local_database` guard is the actual safety net (refuses to run
 * against anything but `environment == "local"` on a localhost/127.0.0.1
 * host), not this wrapper.
 * #VERIFY: scripts/reset_e2e_real_state.py's `_require_local_database`.
 */
export function resetRealState(): void {
  try {
    execFileSync('uv', ['run', 'python', 'scripts/reset_e2e_real_state.py'], {
      cwd: REPO_ROOT,
      stdio: 'inherit',
      // The reset is a handful of SQL statements (sub-second normally); cap it
      // so a hung DB connection surfaces as a failed run instead of stalling
      // the whole suite indefinitely. On timeout execFileSync throws and the
      // catch below rethrows with remediation guidance.
      timeout: 60_000,
    })
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw new Error(
      'scripts/reset_e2e_real_state.py failed (see output above). Re-run it ' +
        'manually from the repo root (uv run python ' +
        'scripts/reset_e2e_real_state.py) with CYO_ADVENTURE_DATABASE_URL set ' +
        `to the local Postgres DSN to diagnose: ${reason}`,
      { cause: error }
    )
  }
}

// localStorage key the app reads the device grant from; mirrors GRANT_KEY in
// src/auth/deviceGrant.ts (not exported there). Kept in sync manually, exactly
// as the specs hardcode the 'auth_token' key.
const DEVICE_GRANT_KEY = 'device_grant'

// The seeded guardian subject (scripts/seed_dev_data.py `_GUARDIAN_SUBJECT`).
// In ENVIRONMENT=local the backend trusts the bearer string as the authn
// subject, so this authenticates as the Dev Family guardian without a real
// Supabase session; the minted grant is therefore scoped to the Dev Family
// that owns the "Dev Reader" profile the kid specs click.
const SEEDED_GUARDIAN_BEARER = 'dev-guardian'

/**
 * Fails fast with an actionable message when the real stack is not running.
 * The backend must be started in ENVIRONMENT=local with the dev seed applied;
 * see the "Real-backend e2e" section of frontend/README.md.
 */
export async function requireBackend(): Promise<void> {
  let ready: boolean
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

/**
 * Mint a real, family-scoped device grant and inject it into the browser
 * context so the kid surface (`/kids`, `/library/:profileId`, `/read/*`) is
 * reachable. Since ADR-014 (#247) that surface is gated by
 * `DeviceAuthorizedRoute` -> `hasValidDeviceGrant()`; a spec that sets only
 * `auth_token` is redirected to guardian sign-in, so the kid specs need this
 * before navigating. Mirrors the guardian console's real flow: an authenticated
 * guardian POSTs `/api/v1/device-grants`, and the returned blob is stored under
 * the `device_grant` localStorage key the app reads on load.
 *
 * The mint is a Node-side fetch (not a browser call) authorized as the seeded
 * guardian; the grant is stored via addInitScript so it is present before any
 * page script runs and the route gate resolves to `authorized` on first render.
 *
 * #EDGE: external-resource: a missing/misconfigured DEVICE_GRANT_SECRET makes
 * the mint 400 (ConfigurationError) rather than 201; the error below names the
 * fix so a stale local uvicorn (started before the secret was set) is
 * diagnosable instead of surfacing later as a `/kids` redirect timeout.
 * #VERIFY: the backend rejects mint without the secret; this helper asserts 201.
 */
export async function authorizeDevice(context: BrowserContext): Promise<DeviceGrant> {
  const res = await fetch(`${BACKEND}/api/v1/device-grants`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${SEEDED_GUARDIAN_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ label: 'e2e-real' }),
    signal: AbortSignal.timeout(5000),
  })
  expect(
    res.ok,
    `Device-grant mint failed (HTTP ${res.status}) at ${BACKEND}. If this is a ` +
      'ConfigurationError, the local uvicorn was started without ' +
      'DEVICE_GRANT_SECRET set; restart it with that env var (any non-empty ' +
      'value works in ENVIRONMENT=local) before npm run test:e2e:real.'
  ).toBe(true)

  // DeviceGrantView -> DeviceGrant: the backend's snake_case wire fields map to
  // the client's camelCase blob (see src/auth/deviceGrantApi.ts's real mapping).
  const view = (await res.json()) as {
    token: string
    expires_at: string
    family_id: string
    id: string
  }
  const grant: DeviceGrant = {
    token: view.token,
    expiresAt: view.expires_at,
    familyId: view.family_id,
    id: view.id,
  }

  await context.addInitScript(
    ([key, serialized]) => {
      window.localStorage.setItem(key, serialized)
    },
    [DEVICE_GRANT_KEY, JSON.stringify(grant)] as const
  )
  return grant
}

/**
 * Revoke a grant minted by `authorizeDevice` so a dev stack that is reused
 * across runs does not accumulate one live device-grant row per test. This is
 * the real tier's parallel to the prod tier's `afterAll` cleanup: the mint is
 * a real POST, so it needs a real DELETE to undo it. Node-side fetch authorized
 * as the same seeded guardian that minted the grant.
 *
 * Best-effort by design and never throws: it runs from spec teardown
 * (`afterEach`), where throwing would mask the real test result with a cleanup
 * error, and the local dev stack is disposable anyway (a stray row is reset by
 * the next `seed_dev_data.py`). A revoke that does not confirm is surfaced as a
 * warning, not a failure, so an accumulating stack is visible rather than
 * silent.
 *
 * #EDGE: external-resource: the backend may be stopped or the grant already
 * gone (404) by teardown; both are swallowed with a warning, never rethrown.
 * #VERIFY: fetch() resolves on 4xx/5xx, so `res.ok` is checked explicitly and a
 * 404 is treated as already-revoked (success for cleanup).
 */
export async function revokeDevice(grant: DeviceGrant): Promise<void> {
  try {
    const res = await fetch(`${BACKEND}/api/v1/device-grants/${grant.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${SEEDED_GUARDIAN_BEARER}` },
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok && res.status !== 404) {
      console.warn(
        `[real-stack] device-grant revoke did not confirm (HTTP ${res.status}) ` +
          `for grant ${grant.id}; the dev stack may accumulate a row until the ` +
          'next seed_dev_data.py run.'
      )
    }
  } catch (err) {
    console.warn(
      `[real-stack] device-grant revoke errored for grant ${grant.id}: ` +
        `${err instanceof Error ? err.message : String(err)}`
    )
  }
}
