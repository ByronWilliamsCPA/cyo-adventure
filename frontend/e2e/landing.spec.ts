import { expect, test } from '@playwright/test'

/**
 * Landing page at `/` (design spec 2026-07-05): the audience-neutral root
 * with a Kids door (-> /kids picker) and a Grown-ups door (-> /guardian).
 */
test('landing shows both doors and the kid door reaches the picker', async ({ page }) => {
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
