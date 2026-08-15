import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

/**
 * Landing page at `/` (sales-funnel redesign, 2026-08): one page, two jobs.
 *
 * Returning users keep the two doors: the Kids door is device-state-aware
 * (ADR-014 section 5), targeting the `/kids` picker only when this device
 * holds a valid device grant and otherwise routing through guardian login
 * with the authorize-device intent. Both branches are covered below,
 * unchanged from before the redesign.
 *
 * New adults get the funnel: hero CTA into guardian login (the self-signup
 * path, P-6e), a working sample adventure, and a subscription-ready pricing
 * section that sells nothing until billing exists (see pricing.ts).
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

// P-6e, now promoted from an easily-missed text link to the hero's primary
// CTA: this proves the funnel's main action reaches the real guardian login
// (where "Continue with Google/Apple" is the actual self-signup mechanism),
// not just that the href string looks right.
test('a new visitor follows the hero "Get started free" CTA straight to guardian sign-in', async ({
  page,
}) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'They pick the path. You approve every page.' })
  ).toBeVisible()
  await page.getByRole('link', { name: /get started free/i }).click()

  await expect(page).toHaveURL('/guardian/login')
  await expect(page.getByRole('heading', { name: 'Guardian sign-in' })).toBeVisible()
})

test('the pricing section is subscription-ready but sells nothing today', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Simple family pricing' })).toBeVisible()

  const explorer = page.getByRole('article', { name: 'Explorer' })
  await expect(explorer.getByText('Available now')).toBeVisible()
  await expect(explorer.getByRole('link', { name: 'Start free' })).toHaveAttribute(
    'href',
    '/guardian/login'
  )

  // The unpriced Family tier must carry no actionable control (pricing.ts
  // #CRITICAL): a status chip and an invitation line only.
  const family = page.getByRole('article', { name: 'Family' })
  await expect(family.getByText('Coming soon').first()).toBeVisible()
  await expect(family.getByRole('link')).toHaveCount(0)
  await expect(family.getByRole('button')).toHaveCount(0)
})

test('the sample adventure plays through to an ending and restarts', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText(/brass lantern swings/i)).toBeVisible()
  await page.getByRole('button', { name: /slip into the glittering cave/i }).click()
  await page.getByRole('button', { name: /peek behind the stone/i }).click()

  await expect(page.getByText(/you found 1 of 4 endings/i)).toBeVisible()
  await expect(page.getByRole('link', { name: /make their next story/i })).toHaveAttribute(
    'href',
    '/guardian/login'
  )

  await page.getByRole('button', { name: /read it again/i }).click()
  await expect(page.getByText(/brass lantern swings/i)).toBeVisible()
})

test('topbar anchors jump to their funnel sections', async ({ page }) => {
  await page.goto('/')

  // Scoped to the topnav: the hero's "See how it works" CTA would otherwise
  // also match the substring-based role-name lookup for "How it works".
  const topnav = page.getByRole('navigation', { name: 'Page sections' })
  await topnav.getByRole('link', { name: 'Pricing' }).click()
  await expect(page.locator('#pricing')).toBeInViewport()

  await topnav.getByRole('link', { name: 'How it works' }).click()
  await expect(page.locator('#how-it-works')).toBeInViewport()
})
