import { expect, test } from '@playwright/test'

import { SUPABASE_SESSION_KEY, mockEmptyConsole, seedGuardianSession } from './support/auth'

/**
 * The backend-unreachable branch (#452): `/guardian/unavailable`
 * (`frontend/src/auth/GuardianBackendUnavailablePage.tsx`, classified by
 * `AuthContext.tsx::classifyPrincipalError`).
 *
 * Why this file exists. The coverage matrix declared this gap honestly and
 * even named the recipe: "no E2E tier exercises the backend-unreachable
 * branch. Reproducing it needs the API to fail while Supabase keeps
 * succeeding, which the mocked tier can express (fulfil `/api/v1/**` with a
 * 503 after sign-in) but no spec does." This is that spec.
 *
 * What only a network-tier test can prove. The regression this branch exists
 * to prevent is a LOOP, and a loop is a property of the whole system, not of
 * any one component: on 2026-07-23 a transient `/v1/me` failure was handled
 * identically to a rejection, so sign-out sent the guardian to login, login
 * re-established the same perfectly good Supabase session, and resolution
 * failed again against the same downed backend, forever. Component tests
 * cover each end of that (AuthContext's classification matrix, and the
 * interstitial's own retry behavior) but neither can observe the guardian
 * being bounced, because neither owns the router and the session store at
 * once.
 *
 * The two halves are a matched pair, and neither is worth much alone. The
 * transient test asserts a 5xx KEEPS the token and lands on the retry page;
 * the terminal test asserts a 401 CLEARS it and lands on login. Assert only
 * the first and a build that treated every `/me` failure as transient would
 * pass while parking genuinely rejected sessions on a retry screen that can
 * never succeed. Assert only the second and the original loop comes back.
 */

/** Read the bearer the app persists, from the page's own localStorage. */
async function storedToken(page: import('@playwright/test').Page): Promise<string | null> {
  return page.evaluate(() => window.localStorage.getItem('auth_token'))
}

async function sessionPresent(page: import('@playwright/test').Page): Promise<boolean> {
  return page.evaluate((key) => window.localStorage.getItem(key) !== null, SUPABASE_SESSION_KEY)
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('a 5xx on /me parks the guardian on the retry interstitial and KEEPS the session', async ({
  page,
}) => {
  await mockEmptyConsole(page)
  // Supabase keeps succeeding (the session is seeded and never refreshes);
  // only OUR api fails. That asymmetry is the whole scenario: a failure of
  // both would be an ordinary signed-out case.
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({ status: 503, json: { detail: 'upstream unavailable' } })
  )

  await page.goto('/guardian')

  await expect(page).toHaveURL(/\/guardian\/unavailable$/)
  await expect(
    page.getByRole('heading', { name: "We can't reach CYO Adventure", level: 1 })
  ).toBeVisible()

  // The #452 fix itself. If this regresses, the guardian is signed out by a
  // problem that was never about their credentials, and the loop returns.
  expect(await storedToken(page)).not.toBeNull()
  expect(await sessionPresent(page)).toBe(true)

  // And they are not stranded: a manual retry is offered rather than only an
  // automatic one, because the auto-retry gives up after a cap.
  await expect(page.getByRole('button', { name: /try again/i })).toBeVisible()
})

test('POSITIVE CONTROL: a 401 on /me is terminal, so it clears the session and goes to login', async ({
  page,
}) => {
  await mockEmptyConsole(page)
  // A 401 is NOT simply the mirror of the 503 above, and leaving this mock
  // out is a trap worth naming. useApi.ts's P6-06 path treats a 401 as
  // possibly-stale rather than possibly-wrong: it calls
  // supabase.auth.refreshSession() and retries the request once. In this tier
  // GoTrue is the dummy https://example.supabase.co, so an unmocked refresh
  // never resolves, the retry never happens, and the app sits on "Loading…"
  // forever. The test then fails claiming the guardian was not redirected to
  // login, which is true but says nothing about the branch under test.
  //
  // Failing the refresh here is what a really-rejected session does: the
  // refresh token is dead too. That makes this case exercise the full
  // realistic path (401 -> refresh -> refresh fails -> terminal) rather than
  // a shortcut, and it incidentally pins that a failed refresh resolves
  // rather than stranding the app mid-load.
  await page.route('**/auth/v1/token**', (route) =>
    route.fulfill({ status: 400, json: { error: 'invalid_grant', error_description: 'expired' } })
  )
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({ status: 401, json: { detail: 'invalid token' } })
  )

  await page.goto('/guardian')

  // Terminal means signed-out, NOT the retry interstitial: retrying a
  // rejected credential can only fail again.
  //
  // Timeout raised above Playwright's 5s default deliberately. This path can
  // legitimately take longer than any other assertion in this file, because
  // the refresh attempt above is raced against useApi.ts's
  // REFRESH_DEADLINE_MS (10s): normally the mocked 400 answers immediately,
  // but under a loaded full-suite run the request can be slow enough that the
  // deadline, not the response, is what ends the wait. That produced a real
  // flake, passing standalone and failing in the full run. 15s clears the
  // deadline with margin rather than merely widening the window.
  await expect(page).toHaveURL(/\/guardian\/login$/, { timeout: 15_000 })
  await expect(page).not.toHaveURL(/unavailable/)

  // NOT asserted here: that `auth_token` is gone. It is cleared, but not
  // durably, and the difference cost a full-suite flake worth recording.
  //
  // The terminal path calls safeRemoveToken() and leaves the SUPABASE session
  // alone, by design: only the app's bearer is rejected, not the GoTrue
  // session. Every later syncPrincipal for a non-null session opens with
  // `localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token)`
  // (AuthContext.tsx), so any subsequent auth event re-mints the bearer from
  // the session that is still sitting in storage. "Token cleared" is
  // therefore a transient state inside a retry loop, not a postcondition, and
  // an assertion on it passes or fails on timing: it held standalone and
  // failed under a loaded full-suite run.
  //
  // The stable, and the actually meaningful, claim is the routing one above:
  // a rejected principal ends at login and NOT at the retry interstitial. The
  // sibling test asserts token RETENTION on the transient path, which is
  // stable in the other direction because nothing on that path clears it.
})

test('recovering backend: Try again resolves the principal and moves on to the console', async ({
  page,
}) => {
  await mockEmptyConsole(page)

  // One handler whose behavior flips, rather than two competing routes: this
  // models the real event (the API comes back) instead of a routing trick,
  // and keeps the "before" and "after" on the same request path.
  let backendUp = false
  await page.route('**/api/v1/me', (route) => {
    if (!backendUp) {
      return route.fulfill({ status: 503, json: { detail: 'upstream unavailable' } })
    }
    return route.fulfill({
      json: {
        subject: 'guardian-1',
        role: 'guardian',
        is_admin: false,
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
  })

  await page.goto('/guardian')
  await expect(page).toHaveURL(/\/guardian\/unavailable$/)

  backendUp = true
  await page.getByRole('button', { name: /try again/i }).click()

  // Recovery is a redirect OUT of the interstitial, not merely a cleared
  // error banner: the guardian must end up where they were going.
  await expect(page).toHaveURL(/\/guardian$/, { timeout: 15000 })
  await expect(page).not.toHaveURL(/unavailable/)
})
