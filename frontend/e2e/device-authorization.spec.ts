import { expect, test } from '@playwright/test'

import {
  makeGuardianSession,
  mockDeviceGrants,
  mockEmptyConsole,
  mockMe,
  mockOnboarding,
  seedGuardianSession,
  seedPasswordGuardianSession,
} from './support/auth'

/**
 * ADR-014 device-authorization journeys that no other spec exercises. The kid
 * specs seed a grant to get past DeviceAuthorizedRoute; these instead drive the
 * three flows that MINT, REMOVE, or CHALLENGE at the boundary:
 *   1. the authorize-device login intent (a fresh device is handed to a child),
 *   2. the guardian console "This device" set-up / remove roundtrip, and
 *   3. the cold adult step-up challenge on a password-identity session.
 *
 * All mocked (page.route), same as the rest of the mocked e2e tier; no backend.
 */

test.describe('authorize-device intent (ADR-014 section 5)', () => {
  test('a fresh device: the Kids door routes through login, mints a grant, then drops to the picker', async ({
    page,
  }) => {
    // A fresh device holds no grant, so the landing Kids door carries the
    // authorize-device intent. Sign-in is mocked at the Supabase token
    // endpoint; the minted grant comes back from POST /v1/device-grants.
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ json: makeGuardianSession('e2e-guardian-token') })
    )
    await mockOnboarding(page)
    await mockMe(page)
    await mockDeviceGrants(page)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

    await page.goto('/')
    await page.getByRole('link', { name: /kids/i }).click()
    await expect(page).toHaveURL('/guardian/login?intent=authorize-device')

    // Signing in with the intent present mints a grant for THIS device and
    // returns to the picker (LoginPage's authorize-device effect), so the kid
    // never sees the console.
    await page.getByLabel('Email').fill('parent@example.com')
    await page.getByLabel('Password').fill('test-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page).toHaveURL('/kids')
    await expect(page.getByText('No profiles yet')).toBeVisible()

    // The minted grant persisted to localStorage: a full reload into a kid
    // route now renders instead of bouncing back to authorize-device.
    await page.goto('/library/p1')
    await expect(page).toHaveURL('/library/p1')
    await expect(page.getByText('No books yet')).toBeVisible()
  })
})

test.describe('guardian console "This device" (ADR-014)', () => {
  test('set up this device, then remove it', async ({ page, context }) => {
    // An OAuth-bypass guardian session (empty app_metadata) so the console
    // renders without a challenge; no device grant yet, so the set-up CTA shows.
    await seedGuardianSession(context)
    await mockMe(page)
    await mockEmptyConsole(page)
    await mockDeviceGrants(page)

    await page.goto('/guardian')
    await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()

    const deviceSection = page.getByRole('region', { name: 'Device setup' })
    await deviceSection.getByRole('button', { name: 'Set up this device for your kids' }).click()

    // POST /v1/device-grants (mocked 201) flips the section to the authorized
    // state, which surfaces the hand-off launcher.
    await expect(
      deviceSection.getByText('This device is set up for your family')
    ).toBeVisible()
    await expect(
      deviceSection.getByRole('button', { name: 'Hand device to a child' })
    ).toBeVisible()

    // The button now opens a confirm dialog rather than revoking directly
    // (I13: a misclick would otherwise lock kids out until re-authorized).
    // DELETE /v1/device-grants/:id (mocked 204) revokes and returns to the CTA
    // only after the confirm click.
    await deviceSection.getByRole('button', { name: 'Remove from this device' }).click()
    await page.getByRole('button', { name: 'Remove device' }).click()
    await expect(
      deviceSection.getByRole('button', { name: 'Set up this device for your kids' })
    ).toBeVisible()
  })
})

test.describe('cold adult step-up (ADR-014 Phase 5 single boundary)', () => {
  test('a password-identity session must clear the gate before the console', async ({
    page,
    context,
  }) => {
    // Cold + has-password => the "Grown-ups only" challenge stands in front of
    // the whole adult subtree (unlike the OAuth-bypass sessions the other
    // guardian specs seed). Re-auth on Confirm hits the token endpoint.
    await seedPasswordGuardianSession(context)
    await mockMe(page)
    await mockEmptyConsole(page)
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ json: makeGuardianSession('e2e-guardian-token') })
    )

    await page.goto('/guardian')

    await expect(page.getByRole('heading', { name: 'Grown-ups only' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Family console' })).toHaveCount(0)

    await page.getByLabel('Password').fill('test-password')
    await page.getByRole('button', { name: 'Confirm' }).click()

    await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  })
})
