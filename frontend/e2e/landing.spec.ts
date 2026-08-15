import { expect, test } from '@playwright/test'

import { LANDING_HEADLINE } from '../src/landing/headline'
import { seedDeviceGrant } from './support/auth'
import { LOGIN_HEADLINE } from '../src/guardian/loginHeadline'

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

/**
 * Section ORDER on a granted device, plus the spacing that ordering needs.
 *
 * The doors band renders above the hero so a child handed a family tablet
 * sees their door on the first screenful. That promotion makes the band
 * `main`'s first child, where its own `padding-top: 0` (correct when it
 * follows the hero) left the heading flush against the sticky topbar's lower
 * edge. Geometry is the only way to catch that: every DOM-order and
 * visibility assertion passes while the text sits under the bar.
 */
test('a granted device leads with the doors band, clear of the sticky topbar', async ({
  page,
  context,
}) => {
  await seedDeviceGrant(context)
  await page.goto('/')

  const band = page.locator('.landing-doors-band')
  const heading = page.locator('.landing-doors-band__heading')
  await expect(heading).toBeVisible()

  const bandBox = await band.boundingBox()
  const heroBox = await page.locator('.landing-hero').boundingBox()
  const topbarBox = await page.locator('.landing__topbar').boundingBox()
  if (!bandBox || !heroBox || !topbarBox) throw new Error('landing geometry unavailable')

  // Ordering: the band really is above the hero, not merely present.
  expect(bandBox.y).toBeLessThan(heroBox.y)

  // Spacing: the heading clears the topbar's bottom edge rather than
  // starting underneath it.
  const headingBox = await heading.boundingBox()
  if (!headingBox) throw new Error('doors-band heading geometry unavailable')
  expect(headingBox.y).toBeGreaterThan(topbarBox.y + topbarBox.height)
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

// P-6e, now promoted from an easily-missed text link to the funnel's one
// repeated primary CTA: this proves the hero instance reaches the real
// guardian login (where "Continue with Google/Apple" is the actual
// self-signup mechanism), not just that the href string looks right. Scoped
// to the hero because the same label recurs (topbar, post-safety, final
// band) by design: one action, one name.
test('a new visitor follows the hero "Get started free" CTA straight to guardian sign-in', async ({
  page,
}) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: LANDING_HEADLINE })).toBeVisible()
  await page.locator('.landing-hero').getByRole('link', { name: 'Get started free' }).click()

  await expect(page).toHaveURL('/guardian/login')
  await expect(page.getByRole('heading', { name: LOGIN_HEADLINE })).toBeVisible()
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

  // The unavailable Family tier gets NO card at all (pricing.ts #CRITICAL):
  // an unbuyable card invites a comparison the visitor cannot act on. It
  // survives as a one-line future commitment instead.
  await expect(page.getByRole('article', { name: 'Family' })).toHaveCount(0)
  const pricing = page.locator('#pricing')
  await expect(pricing.getByText(/A paid Family plan comes later/)).toBeVisible()

  // One action in the whole section, and it is sign-in, never a checkout.
  await expect(pricing.getByRole('link')).toHaveCount(1)
  await expect(pricing.getByRole('button')).toHaveCount(0)
})

test('the sample adventure plays through to an ending, counts it, and restarts', async ({
  page,
}) => {
  await page.goto('/')

  await expect(page.getByText(/brass lantern swings/i)).toBeVisible()
  await page.getByRole('button', { name: /slip into the glittering cave/i }).click()
  await page.getByRole('button', { name: /peek behind the stone/i }).click()

  await expect(page.getByText(/you found 1 of 4 endings/i)).toBeVisible()
  await expect(
    page.locator('.demo-adventure').getByRole('link', { name: 'Get started free' })
  ).toHaveAttribute('href', '/guardian/login')

  // "Back one choice" (the reader's go-back feature in miniature) reaches a
  // sibling ending and the counter advances (the invitation to replay must
  // not show a stale count).
  await page.getByRole('button', { name: /back one choice/i }).click()
  await expect(page.getByText(/walls sparkle/i)).toBeVisible()
  await page.getByRole('button', { name: /giggle back, twice/i }).click()
  await expect(page.getByText(/you found 2 of 4 endings/i)).toBeVisible()

  // The restart the test's name promises: back to the opening passage with its
  // first choice available again.
  await page.getByRole('button', { name: /start over/i }).click()
  await expect(page.getByText(/brass lantern swings/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /slip into the glittering cave/i })).toBeVisible()
})

test('topbar anchors jump to their funnel sections', async ({ page }) => {
  await page.goto('/')

  // Scoped to the topnav rather than the page. The comment here used to
  // blame a hero "See how it works" CTA, which no longer exists; the real
  // reason to scope is that the how-it-works SECTION heading also matches a
  // substring-based name lookup, and the eyebrow/heading pairs repeat the
  // nav labels ("Pricing", "Safety") verbatim by design.
  const topnav = page.getByRole('navigation', { name: 'Page sections' })

  // toBeInViewport() alone is NOT enough here, and that is the whole point of
  // the geometry below. Measured with scroll-padding-top removed, #pricing
  // lands at y=-0 with the topbar occupying 0..61: still "in viewport", still
  // green, and the section heading sits underneath the sticky bar. The
  // scroll-padding rule and its @supports fallback in landing.css exist for
  // exactly this, so they need an assertion that can see it.
  const topbar = page.locator('.landing__topbar')
  const topbarBox = await topbar.boundingBox()
  if (!topbarBox) throw new Error('topbar geometry unavailable')
  const topbarBottom = topbarBox.y + topbarBox.height

  for (const [label, id] of [
    ['Pricing', '#pricing'],
    ['How it works', '#how-it-works'],
  ] as const) {
    await topnav.getByRole('link', { name: label }).click()
    const section = page.locator(id)
    await expect(section).toBeInViewport()
    await expect
      .poll(async () => (await section.boundingBox())?.y ?? -1, {
        message: `${id} should come to rest clear of the sticky topbar`,
      })
      .toBeGreaterThanOrEqual(topbarBottom)
  }
})

// S6: the topnav puts these URLs in the address bar, so they get bookmarked
// and shared. The landing route is lazy, so the browser resolves the fragment
// against an empty document and the visitor lands at the top with no sign
// anything was meant to happen.
test('a bookmarked section link cold-loads at that section', async ({ page }) => {
  await page.goto('/#pricing')
  await expect(page.getByRole('heading', { name: 'Simple family pricing' })).toBeVisible()
  await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeGreaterThan(0)
  await expect(page.locator('#pricing')).toBeInViewport()
})
