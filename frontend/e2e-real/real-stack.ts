import { type BrowserContext, expect } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

export const BACKEND = process.env.E2E_BACKEND_URL || 'http://localhost:8000'

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
