import type { BrowserContext, Page } from '@playwright/test'

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

export function makeGuardianSession(accessToken: string) {
  // Mirror the session shape currently in assignments.spec.ts:28-42, including
  // the fuller GoTrueClient user object (role/app_metadata/user_metadata/
  // created_at) that spec seeds beyond this helper's minimum fields.
  return {
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
