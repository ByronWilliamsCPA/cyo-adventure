import type { BrowserContext, Page, Route } from '@playwright/test'

/**
 * Guardian-surface auth helpers.
 *
 * seedGuardianSession writes the GoTrue session directly to localStorage
 * (the pattern proven in assignments.spec.ts): fast, no login form. Use it
 * for every guardian spec EXCEPT guardian-auth.spec.ts, which drives the
 * real login form because sign-in itself is the behavior under test.
 *
 * The storage key 'sb-example-auth-token' derives from the dummy
 * VITE_SUPABASE_URL (https://example.supabase.co) in playwright.config.ts.
 * A far-future expires_at keeps supabase-js from attempting a token refresh
 * mid-test, so no auth network calls ever fire.
 */
export const SUPABASE_SESSION_KEY = 'sb-example-auth-token'

export interface MeBody {
  subject: string
  role: 'guardian' | 'admin'
  is_admin: boolean
  family_id: string
  profile_ids: string[]
}

export const DEFAULT_ME: MeBody = {
  subject: 'guardian-1',
  role: 'guardian',
  is_admin: false,
  family_id: 'fam-1',
  profile_ids: ['p1'],
}

/**
 * Default response for POST /api/v1/onboarding: an already-provisioned,
 * consented guardian. AuthContext.syncPrincipal calls this endpoint
 * unconditionally, before GET /v1/me, for every non-null session (see the
 * '#CRITICAL: security: resolve onboarding BEFORE /v1/me' comment in
 * AuthContext.tsx) -- an unmocked call here 404s/ECONNREFUSEDs against the
 * proxy target in the mocked E2E tier and strands the app on the
 * awaiting-approval/needs-consent branches instead of reaching /me. Routed at
 * the context level (below) so every guardian-session spec is covered without
 * each one wiring it up individually.
 */
const DEFAULT_ONBOARDING_RESPONSE = {
  family_id: 'fam-1',
  user_id: 'e2e-user',
  role: 'guardian',
  created: false,
  status: 'active',
  consent_recorded: true,
}

function fulfillOnboarding(route: Route): Promise<void> {
  return route.fulfill({ json: DEFAULT_ONBOARDING_RESPONSE })
}

/**
 * Mock POST /api/v1/onboarding for a single page, overriding the default
 * already-onboarded response seeded by seedGuardianSession/
 * seedPasswordGuardianSession. Use for specs that specifically exercise the
 * awaiting-approval or needs-consent branches (e.g. { status: 'pending' } or
 * { consent_recorded: false }); a page-level route takes precedence over the
 * context-level default.
 */
export async function mockOnboarding(
  page: Page,
  overrides: Partial<typeof DEFAULT_ONBOARDING_RESPONSE> = {}
): Promise<void> {
  const body = { ...DEFAULT_ONBOARDING_RESPONSE, ...overrides }
  await page.route('**/api/v1/onboarding', (route) => route.fulfill({ json: body }))
}

export function makeGuardianSession(accessToken: string) {
  // Mirror the session shape currently in assignments.spec.ts:28-42, including
  // the fuller GoTrueClient user object (role/app_metadata/user_metadata/
  // created_at) that spec seeds beyond this helper's minimum fields.
  return {
    // deepcode ignore HardcodedNonCryptoSecret: fabricated E2E GoTrue session
    // fixture, not a real credential; refresh_token below is a dummy value too.
    access_token: accessToken,
    refresh_token: 'e2e-refresh-token',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: 4102444800, // 2100-01-01: never refreshes during a test
    user: {
      id: 'e2e-user',
      aud: 'authenticated',
      role: 'authenticated',
      email: 'parent@example.com',
      app_metadata: {},
      user_metadata: {},
      created_at: '2026-07-02T00:00:00Z',
    },
  }
}

/** Seed both the GoTrue session and the API bearer token before any page loads. */
// #ASSUME: data-integrity: accessToken deliberately backs both the GoTrue
// session's access_token and the 'auth_token' bearer key below; the app never
// compares the two values (AuthContext re-derives 'auth_token' from the
// session, and /v1/me is the sole principal source), so a single shared value
// is safe here and does not mask a real divergence.
export async function seedGuardianSession(
  context: BrowserContext,
  accessToken = 'e2e-guardian-token'
): Promise<void> {
  const payload = JSON.stringify(makeGuardianSession(accessToken))
  await context.addInitScript(
    ([key, value, token]) => {
      window.localStorage.setItem(key, value)
      window.localStorage.setItem('auth_token', token)
    },
    [SUPABASE_SESSION_KEY, payload, accessToken] as const
  )
  await context.route('**/api/v1/onboarding', fulfillOnboarding)
}

/**
 * A password-identity session variant: app_metadata records the 'email'
 * provider, so AdultGate's hasPassword check (AdultGate.tsx:180) is true. Every
 * other seeded guardian session leaves app_metadata empty and therefore takes
 * the OAuth-bypass branch, which is why the mocked tier never exercises a real
 * locked "Grown-ups only" challenge. A seeded session fires INITIAL_SESSION,
 * not SIGNED_IN, so the gate stays cold (AuthContext only warms on SIGNED_IN),
 * and a cold + has-password entry renders the challenge.
 */
export function makePasswordGuardianSession(accessToken: string) {
  const session = makeGuardianSession(accessToken)
  return {
    ...session,
    user: { ...session.user, app_metadata: { provider: 'email', providers: ['email'] } },
  }
}

/** Seed a cold password-identity session so a cold adult entry hits the gate. */
export async function seedPasswordGuardianSession(
  context: BrowserContext,
  accessToken = 'e2e-guardian-token'
): Promise<void> {
  const payload = JSON.stringify(makePasswordGuardianSession(accessToken))
  await context.addInitScript(
    ([key, value, token]) => {
      window.localStorage.setItem(key, value)
      window.localStorage.setItem('auth_token', token)
    },
    [SUPABASE_SESSION_KEY, payload, accessToken] as const
  )
  await context.route('**/api/v1/onboarding', fulfillOnboarding)
}

export interface DeviceGrantSeed {
  token: string
  /** ISO 8601 timestamp; mirrors DeviceGrantView.expires_at (deviceGrant.ts). */
  expiresAt: string
  familyId: string
  id: string
}

export const DEFAULT_DEVICE_GRANT: DeviceGrantSeed = {
  token: 'e2e-device-grant-token',
  expiresAt: '2100-01-01T00:00:00Z', // far future: never expires mid-test
  familyId: 'fam-1',
  id: 'device-1',
}

/**
 * Seed a valid device grant into localStorage before any page loads, so
 * DeviceAuthorizedRoute (ADR-014) renders the kid surface (/kids, /library/*,
 * /read/*) on first render instead of redirecting to guardian login. The gate
 * checks only the grant's shape and client-side expiry, not familyId, so any
 * non-expired blob unlocks the kid routes. Pair with the existing auth_token
 * seed for kid specs that also issue mocked API calls.
 */
export async function seedDeviceGrant(
  context: BrowserContext,
  overrides: Partial<DeviceGrantSeed> = {}
): Promise<void> {
  const grant = JSON.stringify({ ...DEFAULT_DEVICE_GRANT, ...overrides })
  await context.addInitScript((value) => {
    window.localStorage.setItem('device_grant', value)
  }, grant)
}

/**
 * Mock the device-grant CRUD endpoints for the guardian console's "This
 * device" section and the authorize-device login intent (ADR-014). POST
 * returns a DeviceGrantView-shaped body; GET lists the current grants; DELETE
 * revokes. Call before navigating to a page that drives device authorization.
 */
export async function mockDeviceGrants(
  page: Page,
  grant: Partial<DeviceGrantSeed> = {}
): Promise<void> {
  const view = { ...DEFAULT_DEVICE_GRANT, ...grant }
  const body = {
    id: view.id,
    token: view.token,
    family_id: view.familyId,
    expires_at: view.expiresAt,
    label: 'This device',
    created_at: '2026-07-13T00:00:00Z',
    revoked_at: null,
  }
  await page.route('**/api/v1/device-grants', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 201, json: body })
    }
    return route.fulfill({ json: { device_grants: [body] } })
  })
  await page.route('**/api/v1/device-grants/*', (route) =>
    route.fulfill({ status: 204, body: '' })
  )
}

/**
 * Mock GET /api/v1/me. Pass { role: 'admin' } for admin-gate tests; the
 * is_admin capability defaults from the role so an 'admin' persona passes
 * the /admin route gate without every call site spelling out the flag. Pass
 * { role: 'guardian', is_admin: true } for a dual-role adult.
 */
export async function mockMe(page: Page, me: Partial<MeBody> = {}): Promise<void> {
  const body: MeBody = {
    ...DEFAULT_ME,
    ...(me.role === 'admin' ? { is_admin: true } : {}),
    ...me,
  }
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: body }))
}

/**
 * Mock the endpoints the two console homes fetch on mount: /v1/profiles for
 * the guardian family console, /v1/review-queue + /v1/generation-jobs for
 * the admin review queue.
 */
export async function mockEmptyConsole(page: Page): Promise<void> {
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/generation-jobs', (route) => route.fulfill({ json: { jobs: [] } }))
}
