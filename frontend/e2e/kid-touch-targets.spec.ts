import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * WCAG 2.5.5 tap-target floor for the KID reader's choice buttons. Kids are
 * the app's primary users and tap on real phones/tablets, yet the reader's
 * choice buttons (Reader.tsx's ChoiceButton, data-testid `choice-<id>`) were
 * the one high-traffic control surface with no 44x44 regression guard
 * (admin-touch-targets.spec.ts covers the adult admin CRUD buttons only).
 *
 * Asserts BOTH axes at a phone viewport. If a real choice button falls under
 * 44x44, that is a genuine WCAG 2.5.5 defect to fix in the component, not a
 * threshold to lower here.
 */

const lantern = loadLanternStory()

const READER_PATH = '/read/child-a/s_lantern_cave/1'

test('kid reader choice buttons meet the 44x44 tap floor at a phone viewport', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /read/* redirects to guardian login.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, json: { state: null } })
    }
    return route.fulfill({ status: 200, json: { current_node: 'n_entrance', state_revision: 1 } })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  // The entrance node offers at least the take/ignore-lantern choices; measure
  // every rendered choice button, not a single one.
  const choices = page.locator('.reader-choices button:visible')
  const count = await choices.count()
  expect(count, 'the entrance node should render at least one choice button').toBeGreaterThan(0)
  for (let i = 0; i < count; i++) {
    const box = await choices.nth(i).boundingBox()
    expect(box?.height ?? 0, `choice button ${i} height`).toBeGreaterThanOrEqual(44)
    expect(box?.width ?? 0, `choice button ${i} width`).toBeGreaterThanOrEqual(44)
  }
})
