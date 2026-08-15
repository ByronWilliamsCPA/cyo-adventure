import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * G10 guardian notification bell (route-mocked): sign in as a guardian, see
 * the unread badge from the poll, open the panel, and see a safety alert
 * rendered as visually distinct from an informational item.
 */

const ALERT_ITEM = {
  id: 'evt-alert-1',
  occurred_at: '2026-07-15T13:00:00Z',
  kind: 'kid_flagged',
  severity: 'alert',
  title: 'Reader A flagged a story',
  body: 'Reader A said this story scared them; it needs your review.',
  storybook_id: 'story-1',
  request_id: null,
  profile_id: 'p1',
}

const INFO_ITEM = {
  id: 'evt-info-1',
  occurred_at: '2026-07-15T12:00:00Z',
  kind: 'story_ready',
  severity: 'info',
  title: 'A story is ready',
  body: 'It has been published to your family library.',
  storybook_id: 'story-2',
  request_id: null,
  profile_id: null,
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('guardian opens the notification bell and sees the alert distinctly styled', async ({
  page,
}) => {
  await mockMe(page)
  await page.route('**/api/v1/story-requests*', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/notifications*', (route) =>
    route.fulfill({ json: { notifications: [ALERT_ITEM, INFO_ITEM] } })
  )
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: { profiles: [{ id: 'p1' }] } })
  )
  await page.route('**/api/v1/review-queue', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/generation-jobs', (route) =>
    route.fulfill({ json: { jobs: [] } })
  )

  await page.goto('/guardian')

  const bell = page.getByRole('button', { name: /Notifications/ })
  await expect(bell).toHaveAccessibleName('Notifications, 2 unread')

  await bell.click()
  const panel = page.getByRole('dialog', { name: 'Notifications' })
  await expect(panel).toBeVisible()
  await expect(panel.getByText('Reader A flagged a story')).toBeVisible()
  await expect(panel.getByText('A story is ready')).toBeVisible()
  await expect(panel.getByText('Alert')).toBeVisible()

  const alertRow = panel.getByText('Reader A flagged a story').locator('..')
  await expect(alertRow).toHaveClass(/notification-bell__item--alert/)

  // Opening the panel marks-seen, so the badge clears.
  await expect(bell).toHaveAccessibleName('Notifications')
})
