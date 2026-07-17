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

  await expect(page.getByText(/Reading level 4.5/)).toBeVisible()
  expect(patched).toMatchObject({ reading_level_cap: 4.5 })
})

test('avatar choices are presets only; no photo upload exists', async ({ page }) => {
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [READER_A] } })
  )
  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()

  // None + the 22 illustrated presets (issue #65 phase 1 "Bucket B": the
  // original 8 animals/objects plus 14 new naturalistic/aspirational/sports
  // presets).
  await expect(page.getByRole('group', { name: 'Avatar' }).getByRole('radio')).toHaveCount(23)
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
})

// ADR-015 G3: the "Story requests" auto-approve section. Payload correctness
// (touched vs. untouched, null-clears-auto-approve) is covered exhaustively
// in ProfileFormDialog.test.tsx; this just proves the section renders and
// wires through end to end via a real submit round trip.
test('turns on auto-approve with a monthly limit and sends both fields', async ({ page }) => {
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [READER_A] } })
  )
  await page.route('**/api/v1/families/me/budget', (route) =>
    route.fulfill({
      json: { quota: 5, spent_this_month: 0, remaining: 5, children: [] },
    })
  )

  let patched: Record<string, unknown> | null = null
  await page.route('**/api/v1/profiles/p1', (route) => {
    patched = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({ json: READER_A })
  })

  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Edit Reader A' }).click()

  await page.getByRole('checkbox', { name: "Auto-approve this child's requests" }).check()
  await page.getByLabel(/Monthly auto-approve limit/).fill('3')
  await page.getByRole('button', { name: 'Save' }).click()

  await expect.poll(() => patched).not.toBeNull()
  expect(patched).toMatchObject({ request_auto_approve: true, monthly_request_envelope: 3 })
})
