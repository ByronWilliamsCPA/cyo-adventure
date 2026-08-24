import { expect, test } from '@playwright/test'

import { LANDING_HEADLINE } from '../src/landing/headline'
import { GUARDIAN_LOGIN_PATH } from '../src/routes'
import { gotoResilient } from '../e2e-support/rate-limit'
import { LOGIN_HEADLINE } from '../src/guardian/loginHeadline'

/**
 * Unauthenticated public surfaces on LIVE production. These are the lightest
 * possible prod checks: no sign-in, no writes, just that the two doors a first
 * visitor sees (the landing page and the guardian sign-in form) render.
 *
 * Runs ad hoc and on the tier's daily cron (see playwright.e2e-prod.config.ts
 * and .github/workflows/e2e-prod.yml). These two tests are the only ones here
 * that never reach requireProdCredentials()'s CI guard, because they need no
 * credentials at all; the rest of the tier depends on that workflow clearing
 * CI deliberately.
 */
test.describe('public surfaces (unauthenticated)', () => {
  test('the landing page renders its headline and both doors', async ({ page }) => {
    await gotoResilient(page, '/')
    // The h1 is the funnel headline since the 2026-08 redesign; the app name
    // moved to the topbar wordmark (a span, not a heading). Mirrors the same
    // readiness assertion in e2e/a11y.spec.ts, via the shared constant so a
    // copy tweak cannot silently red the daily production canary.
    await expect(page.getByRole('heading', { name: LANDING_HEADLINE, level: 1 })).toBeVisible()
    // The two audience doors live in a labelled nav; their visible text
    // ("Kids", "Grown-ups") is span content inside the links, so match the
    // links by accessible name rather than as headings.
    const nav = page.getByRole('navigation', { name: 'Pick who you are' })
    await expect(nav.getByRole('link', { name: /Grown-ups/ })).toBeVisible()
    await expect(nav.getByRole('link', { name: /Kids/ })).toBeVisible()
  })

  test('the guardian sign-in form renders its fields', async ({ page }) => {
    await gotoResilient(page, GUARDIAN_LOGIN_PATH)
    // LOGIN_HEADLINE, not the "Sign in" submit button: every landing-funnel
    // CTA lands here, so the heading has to admit that continuing with Google
    // provisions a new account.
    // exact:true on the field labels avoids matching the reset sub-form's
    // "Email for reset link" if the "Forgot your password?" toggle ever
    // renders its input into the DOM.
    await expect(page.getByRole('heading', { name: LOGIN_HEADLINE, level: 1 })).toBeVisible()
    await expect(page.getByLabel('Email', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  })
})
