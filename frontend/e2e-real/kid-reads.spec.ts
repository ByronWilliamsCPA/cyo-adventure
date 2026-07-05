import { expect, test } from '@playwright/test'

import { requireBackend } from './real-stack'

/**
 * Real-API kid journey: picker -> library -> read to an ending. No route
 * mocks; every /api call hits uvicorn through the preview proxy, authorized
 * as the seeded dev-child subject (ENVIRONMENT=local trusts the bearer token).
 */

test.beforeEach(async ({ context }) => {
  await requireBackend()
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test('the seeded child reads a real story to an ending', async ({ page }) => {
  await page.goto('/')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Two published seeded stories (tide pools, clockwork garden).
  const shelfBooks = page.locator('.library__shelf > li')
  const hero = page.getByRole('region', { name: 'Continue Reading' })
  // Open whichever surface offers the first book (hero on revisit, shelf first time).
  if (await hero.count()) {
    await hero.getByRole('link').first().click()
  } else {
    await shelfBooks.first().getByRole('link').click()
  }
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  for (let i = 0; i < 40; i += 1) {
    if (await page.getByTestId('ending-screen').count()) break
    await page.locator('[data-testid^="choice-"]').first().click()
  }
  await expect(page.getByTestId('ending-screen')).toBeVisible()
})
