import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian trust surface (`/guardian/privacy`, PrivacyPage.tsx, register
 * G11): a plain-language, footer-linked explanation of how family data is
 * handled, with reference links out to Profiles/Requests/Books. Had no
 * browser-level coverage before this file: the page is static content plus
 * plain `react-router` `Link`s, with no dedicated Vitest component test
 * either.
 */

async function setUp(context: BrowserContext, page: Page): Promise<void> {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/story-requests**', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications**', (route) =>
    route.fulfill({ json: { notifications: [], unread_count: 0 } })
  )
}

test('renders the plain-language privacy explanation', async ({ page, context }) => {
  await setUp(context, page)

  await page.goto('/guardian/privacy')

  await expect(
    page.getByRole('heading', { name: "How we handle your family's data" })
  ).toBeVisible()
  await expect(page.getByText('The short version')).toBeVisible()
  await expect(
    page.getByText('Stories are shaped by the settings you choose, never by who your child is.')
  ).toBeVisible()
})

test('the reference links point at their guardian-console destinations', async ({
  page,
  context,
}) => {
  await setUp(context, page)

  await page.goto('/guardian/privacy')
  const controls = page.locator('.privacy__controls')

  await expect(controls.getByRole('link', { name: 'Profiles' }).first()).toHaveAttribute(
    'href',
    '/guardian/profiles'
  )
  await expect(controls.getByRole('link', { name: 'Requests from your kids' })).toHaveAttribute(
    'href',
    '/guardian/requests'
  )
  await expect(controls.getByRole('link', { name: 'Books' })).toHaveAttribute(
    'href',
    '/guardian/books'
  )
})

test('clicking the Profiles reference link navigates to the profiles page', async ({
  page,
  context,
}) => {
  await setUp(context, page)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))

  await page.goto('/guardian/privacy')
  await page.locator('.privacy__controls').getByRole('link', { name: 'Profiles' }).first().click()

  await expect(page).toHaveURL(/\/guardian\/profiles$/)
})

test('an unauthenticated visit to the privacy route redirects to guardian login', async ({
  page,
}) => {
  await page.goto('/guardian/privacy')

  await expect(page).toHaveURL(/\/guardian\/login$/)
})
