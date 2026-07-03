import { expect, test } from '@playwright/test'

/**
 * Guardian concept-intake surface (C4a-5). The IntakePage lives under
 * GuardianAuthLayout + ProtectedRoute, which require a live Supabase
 * (GoTrueClient) session; a route-mock cannot establish one, so this spec
 * covers only the reachable auth-gate behavior (an unauthenticated visit
 * redirects to the guardian login). The submit-body / no-PII / pill / polling
 * behavior is covered by Vitest (src/guardian/IntakePage.test.tsx), mirroring
 * the documented guardian-surface decision in profiles.spec.ts.
 */

test('unauthenticated visit to intake redirects to guardian sign-in', async ({
  page,
}) => {
  await page.goto('/guardian/intake')
  await expect(page).toHaveURL(/\/guardian\/login$/)
  await expect(page.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()
})
