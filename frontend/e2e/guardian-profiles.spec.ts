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

  // exact: true because the new gamification-toggle hints interpolate the
  // child's name ("A small ring in Nova's library...", G19), so a substring
  // match is a strict-mode violation while the dialog is still closing.
  await expect(page.getByText('Nova', { exact: true })).toBeVisible()
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

// P-6c: there was no UI at all to delete a child profile despite the backend
// supporting it. The confirm dialog names the child and warns of permanence
// before DELETE /v1/profiles/{id} fires; Cancel must be a true no-op.
test('deletes a child profile after confirming, naming the child and warning it is permanent', async ({
  page,
}) => {
  await page.route('**/api/v1/families/me/budget', (route) =>
    route.fulfill({ json: { quota: 5, spent_this_month: 0, remaining: 5, children: [] } })
  )
  let profiles = [READER_A]
  let deleteRequests = 0
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles } }))
  await page.route('**/api/v1/profiles/p1', (route) => {
    if (route.request().method() === 'DELETE') {
      deleteRequests += 1
      profiles = []
      return route.fulfill({ status: 204, body: '' })
    }
    return route.fulfill({ json: READER_A })
  })

  await page.goto('/guardian/profiles')
  await expect(page.getByText('Reader A')).toBeVisible()

  // Cancel is a true no-op: no DELETE fires, the card stays.
  await page.getByRole('button', { name: 'Delete Reader A' }).click()
  await expect(page.getByRole('heading', { name: /delete reader a.?s profile/i })).toBeVisible()
  await expect(page.getByText(/permanently deletes/i)).toBeVisible()
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(deleteRequests).toBe(0)
  await expect(page.getByText('Reader A')).toBeVisible()

  // Confirming fires the DELETE and removes the card.
  await page.getByRole('button', { name: 'Delete Reader A' }).click()
  await page.getByRole('button', { name: 'Delete profile' }).click()

  await expect.poll(() => deleteRequests).toBe(1)
  await expect(page.getByText('Reader A')).toHaveCount(0)
})
