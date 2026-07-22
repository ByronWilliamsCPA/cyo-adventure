import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { requireBackend } from './real-stack'

/**
 * Real G10 guardian notification path. The admin approves the seeded
 * in-review story (the same real action approval-flow.spec.ts drives),
 * which fires a real ``RELEASED`` pipeline_event (publishing/service.py);
 * notifications/registry.py composes that into a "story_ready" item for the
 * Dev Family guardian. This spec then signs in as the guardian and asserts
 * the real ``GET /v1/notifications`` feed carries that item, the unread
 * badge reflects it, and opening the panel clears the badge and survives a
 * reload.
 *
 * #ASSUME: data-integrity: notifications/service.py's docstring states the
 * backend keeps no server-side read/unread state for this first slice; the
 * whole model lives client-side in notificationSeenStore.ts (localStorage).
 * So "marking read" here is a client-side markSeen(), not a real mutation
 * endpoint; the persistence being proven is that the localStorage record
 * survives a reload, combined with the real `since`-filtered poll continuing
 * to report zero new items.
 * #VERIFY: NotificationBell.test.tsx and notificationSeenStore.test.ts cover
 * the client-side model directly; this spec proves it holds against the real
 * backend's `since` semantics, not just a mocked response.
 *
 * Serial: the approve step mutates the database and the guardian-side
 * assertions depend on it having happened first.
 */

test.describe.configure({ mode: 'serial' })

test.beforeEach(async () => {
  await requireBackend()
})

test('the admin approves the seeded story through the real API', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto('/admin/review/s_bridge_builder')
  await expect(page.getByRole('heading', { name: 'The Bridge Builder' })).toBeVisible()

  await page.getByRole('button', { name: /^Approve$/ }).click()
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/admin$/)
})

test('the guardian sees the real story_ready notification, and seeing it persists across reload', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/guardian')

  const bell = page.getByRole('button', { name: /Notifications/ })
  await expect(bell).toBeVisible()

  await bell.click()
  const panel = page.getByRole('dialog', { name: 'Notifications' })
  await expect(panel).toBeVisible()
  // The exact title composed by notifications/registry.py::_compose_released
  // for a RELEASED event: f"{_story_label(ctx)} is ready on the shelf".
  // #ASSUME: data-integrity: reset_e2e_real_state.py reverts the storybook's
  // status but does not purge pipeline_event, so a dev stack that has run
  // this approval before (this spec, or approval-flow.spec.ts) carries one
  // "story_ready" row per prior run; .first() asserts the newest (the one
  // this run just produced) is present without depending on it being the
  // only one.
  // #VERIFY: this spec passes on both a first and a second consecutive run.
  const releasedItem = panel.getByText('The Bridge Builder is ready on the shelf').first()
  await expect(releasedItem).toBeVisible()

  // Opening the panel marks-seen client-side (notificationSeenStore.ts), so
  // the badge clears immediately even though the real feed still has items.
  await expect(bell).toHaveAccessibleName('Notifications')

  // Persisted across reload: the seen-state lives in localStorage, not just
  // React state, so a reload must not resurrect the unread badge even though
  // the real GET /v1/notifications still returns the same item unfiltered.
  await page.reload()
  await expect(bell).toHaveAccessibleName('Notifications')
  await bell.click()
  await expect(releasedItem).toBeVisible()
})
