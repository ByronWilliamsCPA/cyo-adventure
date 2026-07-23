import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, mockOnboarding } from './support/auth'

/**
 * Guardian password recovery (request-a-reset, set-a-new-password, and the
 * cross-tab hand-off): previously NO browser-level coverage. Component tests
 * (ResetPasswordRequestForm.test.tsx, SetNewPasswordForm.test.tsx) mock
 * useAuth() directly and never touch supabase-js itself, so nothing had ever
 * exercised the real Supabase Auth (GoTrue) network contract these two forms
 * depend on.
 *
 * Both forms call GoTrue directly (ADR-009), not the backend: resetPassword-
 * ForEmail -> POST **auth/v1/recover**, updateUser -> PUT **auth/v1/user**.
 * This is why the mocks below target `auth/v1/...` routes, not `api/v1/...`.
 *
 * The set-new-password path additionally requires an established Supabase
 * session, which only exists once a password-recovery link is followed. That
 * link lands on `/guardian/login` with an implicit-grant URL hash
 * (`#access_token=...&type=recovery`); supabase-js's `_getSessionFromURL`
 * parses it and, for the implicit flow, calls `_getUser(access_token)` --
 * i.e. a real GET **auth/v1/user** round trip -- before it will consider the
 * session established (confirmed by reading
 * node_modules/@supabase/auth-js/dist/main/GoTrueClient.js `_getSessionFromURL`
 * and `_updateUser`, which throws `AuthSessionMissingError` with no session).
 * Skipping that mock would make updateUser() throw before ever reaching the
 * PUT, so `mockRecoverySession` below covers both the GET (session
 * establishment) and the PUT (the actual password change) on the same
 * `**auth/v1/user**` pattern, keyed on HTTP method.
 *
 * #ASSUME: external-resource: GoTrue (supabase-js) derives `expires_at` from
 * `expires_in` plus its own `Date.now()` read inside the page, so `expires_at`
 * is intentionally omitted from the recovery hash and there is nothing to keep
 * in sync with the test's clock.
 * #VERIFY: pinned by reading @supabase/auth-js's `_getSessionFromURL` (the
 * source note above); re-check on any @supabase/auth-js version bump.
 */

const RECOVERY_USER = {
  id: 'e2e-user',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'parent@example.com',
  app_metadata: {},
  user_metadata: {},
  created_at: '2026-07-02T00:00:00Z',
}

/**
 * The implicit-grant recovery-link hash GoTrue expects: `access_token`,
 * `refresh_token`, `expires_in`, and `token_type` are all required for
 * `_isImplicitGrantCallback` to recognize the URL and for `_getSessionFromURL`
 * to accept it (any missing field throws "No session defined in URL"); `type
 * =recovery` is what routes the outcome to a `PASSWORD_RECOVERY` event
 * instead of `SIGNED_IN`.
 */
function recoveryHash(): string {
  const params = new URLSearchParams({
    // deepcode ignore HardcodedNonCryptoSecret: fabricated GoTrue implicit-grant
    // recovery hash for this E2E test; dummy token values, not real secrets.
    access_token: 'e2e-recovery-access-token',
    refresh_token: 'e2e-recovery-refresh-token',
    expires_in: '3600',
    token_type: 'bearer',
    type: 'recovery',
  })
  return `#${params.toString()}`
}

/**
 * Mock the two GoTrue calls the recovery return-leg makes on the same
 * `**auth/v1/user**` path, keyed on method: GET establishes the session
 * (`_getSessionFromURL` -> `_getUser`), PUT is the actual password change
 * (`updateUser`). Returns a getter for the captured PUT body so the test can
 * assert the exact payload the app sent.
 */
async function mockRecoverySession(page: Page): Promise<() => Record<string, unknown> | null> {
  let updateBody: Record<string, unknown> | null = null
  await page.route('**/auth/v1/user', (route) => {
    if (route.request().method() === 'PUT') {
      updateBody = route.request().postDataJSON() as Record<string, unknown>
      return route.fulfill({ json: { user: RECOVERY_USER } })
    }
    return route.fulfill({ json: RECOVERY_USER })
  })
  return () => updateBody
}

/**
 * Mock POST auth/v1/recover, returning a getter for the captured email.
 * The trailing wildcard on the route glob is load-bearing:
 * resetPasswordForEmail sends the redirectTo option as a `?redirect_to=...`
 * query string (AuthContext.tsx), and Playwright globs match the full URL
 * including the query, so a query-less `recover` pattern would miss the real
 * request and let it fall through to the (absent) backend proxy.
 */
async function mockRecover(page: Page): Promise<() => string | undefined> {
  let email: string | undefined
  await page.route('**/auth/v1/recover**', (route) => {
    email = (route.request().postDataJSON() as { email?: string }).email
    return route.fulfill({ json: {} })
  })
  return () => email
}

test('a signed-out guardian requests a reset link and sees the neutral confirmation', async ({
  page,
}) => {
  const recoveredEmail = await mockRecover(page)

  await page.goto('/guardian/login')
  await expect(page.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()

  await page.getByRole('button', { name: 'Forgot your password?' }).click()
  await page.getByLabel('Email for reset link').fill('guardian@example.com')
  await page.getByRole('button', { name: 'Send reset link' }).click()

  // Neutral by design (Supabase does not disclose whether the address is
  // registered): the same confirmation renders regardless of the outcome.
  // Scope to the confirmation paragraph (guardian-login__note): a global
  // toast-viewport also carries role="status", so a bare getByRole('status')
  // is ambiguous and would resolve the empty toaster region instead.
  await expect(page.locator('p.guardian-login__note')).toHaveText(
    "If an account exists for that email, we've sent a reset link. Check your inbox."
  )
  expect(recoveredEmail()).toBe('guardian@example.com')
})

test('a recovery link lands on the set-new-password form, and submitting it signs the guardian into the console', async ({
  page,
}) => {
  const updateBody = await mockRecoverySession(page)
  await mockOnboarding(page)
  await mockMe(page)
  await mockEmptyConsole(page)

  await page.goto(`/guardian/login${recoveryHash()}`)

  // LoginPage checks `recovery` before any of its signed-in/status branches,
  // so this form renders even while the onboarding/me round trip is still
  // resolving in the background.
  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()

  await page.getByLabel('New password').fill('new-password-123')
  await page.getByLabel('Confirm password').fill('new-password-123')
  await page.getByRole('button', { name: 'Set new password' }).click()

  // A successful updateUser() clears `recovery`; by then the PASSWORD_RECOVERY
  // event fired by the hash landing has already resolved the principal to
  // signed-in via the mocked onboarding/me, so LoginPage auto-continues to
  // the guardian console with no separate sign-in step.
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()

  // flowType defaults to 'implicit' for this client (supabaseClient.ts passes
  // no flowType override), so code_challenge/code_challenge_method are always
  // null here; only a 'pkce' client with an email change would populate them.
  expect(updateBody()).toEqual({
    // deepcode ignore NoHardcodedPasswords: dummy test password asserted
    // against a mocked GoTrue updateUser call, not a real credential.
    password: 'new-password-123',
    code_challenge: null,
    code_challenge_method: null,
  })
})

test('a recovery link opened in one tab surfaces the set-new-password form in another open tab', async ({
  context,
}) => {
  // Page B: an already-open guardian login tab, e.g. a parent who left the
  // sign-in page up on a second device/tab. It must be mounted (and its
  // BroadcastChannel listener registered, AuthContext.tsx's effect) BEFORE
  // page A posts, or the message has nowhere to land.
  const pageB = await context.newPage()
  await pageB.goto('/guardian/login')
  await expect(pageB.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()

  // Page A: follows the recovery link. supabaseClient.ts posts to the shared
  // 'cyo-guardian-recovery' BroadcastChannel purely from the raw `type=
  // recovery` hash marker, at module-eval time -- this does not require
  // `access_token` to be present, so no auth/v1 mocking is needed here; the
  // full implicit-grant hash is only needed by the previous test, which
  // drives the actual session establishment and password update.
  const pageA = await context.newPage()
  await pageA.goto('/guardian/login#type=recovery')
  await expect(pageA.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()

  // Page B never followed the link itself, so it learns about the recovery
  // landing only from AuthProvider's cross-tab broadcast listener
  // (AuthContext.tsx), which flips it straight to the set-new-password form
  // instead of letting Supabase's cross-tab session sync sign it in on the
  // guardian's old password.
  await expect(pageB.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()

  await pageA.close()
  await pageB.close()
})
