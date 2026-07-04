import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

const READER_A = {
  id: 'p1',
  display_name: 'Reader A',
  age_band: '10-13',
  reading_level_cap: 99,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-07-02T00:00:00Z',
}

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page)
})

test('creates a child profile with a preset avatar', async ({ page }) => {
  let created: Record<string, unknown> | null = null
  await page.route('**/api/v1/profiles', (route) => {
    if (route.request().method() === 'POST') {
      created = route.request().postDataJSON() as Record<string, unknown>
      return route.fulfill({
        status: 201,
        json: { ...READER_A, id: 'p2', display_name: 'Nova', age_band: '5-8', avatar: 'owl' },
      })
    }
    return route.fulfill({ json: { profiles: [READER_A] } })
  })

  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()
  await page.getByLabel(/Name/).fill('Nova')
  await page.getByLabel(/Age band/).selectOption('5-8')
  await page.getByRole('radio', { name: /Owl/ }).check()
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('Nova')).toBeVisible()
  expect(created).toMatchObject({ display_name: 'Nova', age_band: '5-8', avatar: 'owl' })
})

test('edits a profile reading cap', async ({ page }) => {
  let patched: Record<string, unknown> | null = null
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [READER_A] } })
  )
  await page.route('**/api/v1/profiles/p1', (route) => {
    patched = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({ json: { ...READER_A, reading_level_cap: 4.5 } })
  })

  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Edit Reader A' }).click()
  await page.getByLabel(/Reading level cap/).fill('4.5')
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText(/Reading cap 4.5/)).toBeVisible()
  expect(patched).toMatchObject({ reading_level_cap: 4.5 })
})

test('avatar choices are presets only; no photo upload exists', async ({ page }) => {
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [READER_A] } })
  )
  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()

  // None + the 8 preset animals/objects (fox, owl, dragon, cat, unicorn, robot, rocket, frog).
  await expect(page.getByRole('radio')).toHaveCount(9)
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
})
