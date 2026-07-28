import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

/**
 * Landing page at `/` (design spec 2026-07-05): the audience-neutral root
 * with a Kids door and a Grown-ups door (-> /guardian).
 *
 * The Kids door is now device-state-aware (ADR-014 section 5): it targets the
 * `/kids` picker only when this device holds a valid device grant, otherwise
 * it routes through guardian login carrying the authorize-device intent. Both
 * branches are covered below.
 */
test('landing kid door reaches the picker when the device is authorized', async ({
  page,
  context,
}) => {
  // An authorized device: the Kids door goes straight to the picker, and the
  // picker route (DeviceAuthorizedRoute) renders instead of redirecting.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))

  await page.goto('/')

  const guardianDoor = page.getByRole('link', { name: /grown-ups/i })
  await expect(guardianDoor).toBeVisible()
  await expect(guardianDoor).toHaveAttribute('href', '/guardian')
  await expect(guardianDoor).toContainText('Admins sign in here too')

  await page.getByRole('link', { name: /kids/i }).click()
  await expect(page).toHaveURL('/kids')
  await expect(page.getByText('No profiles yet')).toBeVisible()
})

test('landing kid door routes through guardian login when the device is not authorized', async ({
  page,
}) => {
  // A fresh device (no grant): the Kids door carries the authorize-device
  // intent so the guardian mints a grant for this device before handing it
  // back (ADR-014 section 5).
  await page.goto('/')

  const kidsDoor = page.getByRole('link', { name: /kids/i })
  await expect(kidsDoor).toHaveAttribute('href', '/guardian/login?intent=authorize-device')
})

// P-6e: the Kids/Grown-ups doors both assume an existing account; a
// brand-new visitor previously had no affordance at all. This proves the new
// "Get started" link reaches the real ordinary guardian login page (where
// "Continue with Google/Apple" is the actual self-signup mechanism), not
// just that the href string looks right.
test('a new visitor follows "Get started" straight to guardian sign-in', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText(/new here\?/i)).toBeVisible()
  await page.getByRole('link', { name: /get started/i }).click()

  await expect(page).toHaveURL('/guardian/login')
  await expect(page.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()
})
