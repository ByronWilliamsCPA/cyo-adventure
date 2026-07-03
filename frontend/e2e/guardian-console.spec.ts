import { expect, test } from '@playwright/test'

/**
 * Guardian console (C4a-4) e2e: unauthenticated-redirect smoke only.
 *
 * The signed-in guardian surface is deliberately NOT covered here: mounting it
 * requires a persisted supabase-js GoTrue session, whose storage shape is
 * version-pinned brittleness this repo already declined for the guardian
 * ProfilesPage (see the header comment in profiles.spec.ts). The console and
 * review-detail behavioral matrix lives in Vitest instead
 * (src/guardian/ConsolePage.test.tsx, src/guardian/ReviewDetailPage.test.tsx).
 *
 * The placeholder VITE_SUPABASE_* values in playwright.config.ts exist so the
 * guardian lazy chunk loads (supabaseClient.ts throws without them) and the
 * real ProtectedRoute redirect can run; getSession() finds no persisted
 * session and resolves null without any network call.
 */

test('an unauthenticated visit to /guardian redirects to the guardian login', async ({
  page,
}) => {
  await page.goto('/guardian')
  await expect(page).toHaveURL(/\/guardian\/login$/)
  // The login page rendered (not the RouteError boundary), proving the
  // guardian chunk loaded and the redirect came from ProtectedRoute.
  await expect(page.getByText(/sign in/i).first()).toBeVisible()
})

test('an unauthenticated visit to a review detail URL also redirects to login', async ({
  page,
}) => {
  await page.goto('/guardian/review/some-story')
  await expect(page).toHaveURL(/\/guardian\/login$/)
})
