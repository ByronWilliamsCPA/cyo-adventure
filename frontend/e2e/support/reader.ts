import { expect, type Page } from '@playwright/test'

/**
 * Waits for the reader to finish opening a book and lands on the reading
 * screen it was asked for.
 *
 * A fresh read opens on the title page (cover, title, Start); a resumed read
 * or a reload mid-book goes straight to its page, and a read saved on an
 * ending reopens on the ending screen. This accepts all three, taps Start
 * only when the title page is what appeared, and returns once the reading or
 * ending screen is up, so a spec written against "the reader is visible"
 * keeps its meaning without caring which of the three its fixture produces.
 * Specs that are ABOUT the title page assert it directly instead.
 */
export async function openReader(page: Page): Promise<void> {
  const titlePage = page.getByTestId('title-page')
  const reading = page.getByTestId('reader').or(page.getByTestId('ending-screen'))
  await expect(titlePage.or(reading)).toBeVisible()
  // Retried as a unit: the title page can be replaced underneath the tap (a
  // mount-time save that 409s adopts the server row and remounts the reader
  // straight onto that position), so a single click could wait on a Start
  // button that no longer exists.
  await expect(async () => {
    if (await titlePage.isVisible()) {
      await page.getByTestId('start-reading').click({ timeout: 1000 })
    }
    await expect(reading).toBeVisible({ timeout: 1000 })
  }).toPass()
}
