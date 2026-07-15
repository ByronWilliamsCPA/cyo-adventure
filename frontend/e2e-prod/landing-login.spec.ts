import { expect, test } from '@playwright/test'

import { GUARDIAN_LOGIN_PATH } from '../src/routes'

/**
 * Unauthenticated public surfaces on LIVE production. These are the lightest
 * possible prod checks: no sign-in, no writes, just that the two doors a first
 * visitor sees (the landing page and the guardian sign-in form) render. Manual
 * trigger only, never wired into CI (see playwright.e2e-prod.config.ts and
 * requireProdCredentials()'s CI guard, which these tests do not even reach
 * because they need no credentials).
 */
test.describe('public surfaces (unauthenticated)', () => {
  test('the landing page renders its title and both doors', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'CYO Adventure', level: 1 })).toBeVisible()
    // The two audience doors live in a labelled nav; their visible text
    // ("Kids", "Grown-ups") is span content inside the links, so match the
    // links by accessible name rather than as headings.
    const nav = page.getByRole('navigation', { name: 'Pick who you are' })
    await expect(nav.getByRole('link', { name: /Grown-ups/ })).toBeVisible()
    await expect(nav.getByRole('link', { name: /Kids/ })).toBeVisible()
  })

  test('the guardian sign-in form renders its fields', async ({ page }) => {
    await page.goto(GUARDIAN_LOGIN_PATH)
    // The heading is "Guardian sign-in" (not "Sign in", which is the submit
    // button). exact:true on the field labels avoids matching the reset
    // sub-form's "Email for reset link" if the "Forgot your password?" toggle
    // ever renders its input into the DOM.
    await expect(page.getByRole('heading', { name: 'Guardian sign-in', level: 1 })).toBeVisible()
    await expect(page.getByLabel('Email', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  })
})
