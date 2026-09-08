import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { GUARDIAN_CONSOLE_PATH, GUARDIAN_LOGIN_PATH } from '../src/routes'
import { signInAsProdTestAdmin, unlockAdultGateIfPresent } from './support/auth'
import { expectConsoleHeading } from './support/diagnostics'
import { gotoResilient } from '../e2e-support/rate-limit'
import { LOGIN_HEADLINE } from '../src/guardian/loginHeadline'

/**
 * R1 live checklist Section 1 (guardian auth and profile management) against
 * LIVE production. Read-only: opens the create-profile dialog to confirm the
 * avatar picker renders, but never submits it, and never creates, edits, or
 * deletes a profile.
 *
 * This file gets its OWN shared page, unlike guardian-admin-smoke.spec.ts's
 * pattern of one page per describe block being reused elsewhere: the sign-out
 * test at the end tears down the session, so nothing else in this tier may
 * share this page afterward. Serial mode (also enforced by the tier's
 * workers:1/fullyParallel:false, made explicit here) because sign-out is a
 * one-way transition partway through the suite.
 *
 * The first two tests run against the default `page` fixture (a fresh,
 * unauthenticated context each), not the shared authenticated page below:
 * they must observe a signed-out visitor, and a fresh context carries none of
 * the shared page's session regardless of ordering.
 *
 * The isolation is the context boundary, and only that. `beforeAll` does NOT
 * run after the first test: Playwright runs it once before every test in the
 * describe block, so `signInAsProdTestAdmin` has already completed by the time
 * test one executes. It simply signed in a different browser context. Do not
 * reintroduce an ordering argument here; moving these tests, or letting them
 * touch `sharedPage`, breaks them for the real reason.
 */
test.describe('guardian auth and profile management (read-only)', () => {
  test.describe.configure({ mode: 'serial' })

  test('an unauthenticated visit to the guardian console redirects to sign-in', async ({
    page,
  }) => {
    // ProtectedRoute (src/auth/ProtectedRoute.tsx) sends any non-signed-in
    // visitor to redirectTo=GUARDIAN_LOGIN_PATH, carrying the attempted
    // location in router state (not the URL), so the destination pathname
    // alone is the thing to assert.
    await gotoResilient(page, GUARDIAN_CONSOLE_PATH)
    await expect(page).toHaveURL(new RegExp(`${GUARDIAN_LOGIN_PATH}$`))
    await expect(page.getByRole('heading', { name: LOGIN_HEADLINE, level: 1 })).toBeVisible()
  })

  test('the login page never offers Apple sign-in (ADR-009: gated behind an unset flag)', async ({
    page,
  }) => {
    await gotoResilient(page, GUARDIAN_LOGIN_PATH)
    await expect(page.getByRole('heading', { name: LOGIN_HEADLINE, level: 1 })).toBeVisible()
    // Apple sign-in is hidden behind VITE_ENABLE_APPLE_OAUTH (LoginPage.tsx),
    // unset in this build because Apple's provider needs a paid Apple
    // Developer account and a signed, expiring client secret that Supabase is
    // not yet configured with (see LoginPage.tsx's own comment). Google is the
    // only always-on provider; asserting it IS visible is the positive
    // control for the Apple assertion below, so a page that rendered no
    // provider buttons at all (an error state, say) cannot make the
    // Apple-absence claim vacuously true.
    await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Continue with Apple/ })).not.toBeVisible()
  })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    await signInAsProdTestAdmin(sharedPage)
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  test('the profiles page renders exactly one profile for the isolated test family', async () => {
    await gotoResilient(sharedPage, '/guardian/profiles')
    await unlockAdultGateIfPresent(sharedPage)
    // Positive control: a page that failed to render (error boundary,
    // ErrorBanner, or a stuck loading state) also shows zero profile cards, so
    // the heading must be visible before the count below means anything.
    await expectConsoleHeading(sharedPage, 'Profiles')
    // ProfilesPage.tsx renders one <li class="profiles__card"> per profile
    // inside a single <ul class="profiles__list">; the E2E Test Family
    // (84b96700) has exactly one child profile.
    await expect(sharedPage.locator('.profiles__list > li')).toHaveCount(1)
  })

  test('the profile form exposes the preset avatar picker', async () => {
    await sharedPage.getByRole('button', { name: 'Add child' }).click()
    const dialog = sharedPage.getByRole('dialog', { name: 'Add child' })
    await expect(dialog).toBeVisible()
    // The avatar catalog is a <fieldset><legend>Avatar</legend>...</fieldset>
    // (ProfileFormDialog.tsx), which the accessibility tree exposes as a
    // "group" named by its legend.
    await expect(dialog.getByRole('group', { name: 'Avatar' })).toBeVisible()
    // Never submit: close via Cancel only. This dialog is also reachable from
    // "Edit" on the one real profile, but Add child avoids touching that
    // profile's stored data even transiently (e.g. a stray keystroke).
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('signing out sends the guardian console back to sign-in', async () => {
    await gotoResilient(sharedPage, '/guardian/profiles')
    await unlockAdultGateIfPresent(sharedPage)
    await sharedPage.getByRole('button', { name: 'Sign out' }).click()
    // AuthContext.signOut clears the session client-side; ProtectedRoute
    // reacts to the resulting status change and redirects via React Router,
    // with no full page reload. Assert that first.
    await expect(sharedPage).toHaveURL(new RegExp(`${GUARDIAN_LOGIN_PATH}$`))
    // Then the harder check the checklist item actually asks for: a fresh
    // navigation (not just the client-side redirect above) back to the
    // guardian console still lands on sign-in, proving the session is gone,
    // not merely hidden by transient React state that a reload would undo.
    await gotoResilient(sharedPage, GUARDIAN_CONSOLE_PATH)
    await expect(sharedPage.getByRole('heading', { name: LOGIN_HEADLINE, level: 1 })).toBeVisible()
  })
})
