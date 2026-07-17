import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

import { loadLanternStory } from './support/fixtures'

/**
 * Coverage for K5 (Replay + Go Back undo, register capability). Ratified
 * 2026-07-16 (Reader.tsx's goBackButton, engine.ts's back/canGoBack); this is
 * its first E2E pin. Mirrors reader.spec.ts's mock patterns (same fixture,
 * same route shapes) but drives the "Go back" affordance specifically:
 * absent at the start node, present after a choice, and faithful (state
 * recomputed by replay, not corrupted) after undoing into a state-gated
 * choice.
 */

const lantern = loadLanternStory()

const READER_PATH = '/read/child-a/s_lantern_cave/1'

const READING_ROW = {
  current_node: 'n_entrance',
  var_state: {},
  path: ['n_entrance'],
  visit_set: ['n_entrance'],
  version: 1,
  state_revision: 1,
  save_slots: {},
}

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /read/* redirects to guardian login.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    return route.fulfill({ status: 200, json: READING_ROW })
  })
  await page.route('**/api/v1/completions', (route) =>
    route.fulfill({
      status: 200,
      json: {
        child_profile_id: 'child-a',
        storybook_id: 's_lantern_cave',
        version: 1,
        ending_id: 'e_treasure_found',
        found_at: new Date().toISOString(),
      },
    })
  )
})

test('Go back is absent at the start node', async ({ page }) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toContainText('A lantern lies near the entrance.')
  await expect(page.getByTestId('go-back')).toHaveCount(0)
})

test('Go back undoes the last choice and replays state faithfully, not by corrupting it (K5)', async ({
  page,
}) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  // Two choices forward, the first sets has_lantern (state), the second is
  // gated on that state: c_dark_passage is only offered because the lantern
  // was taken.
  await page.getByTestId('choice-c_take_lantern').click()
  await expect(page.getByTestId('passage-body')).toContainText('The cave splits.')
  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('ending-id')).toHaveText('e_treasure_found')

  // Go back from the ending returns into the story, one step before it: the
  // prior node (n_cave_fork) text is shown again.
  await page.getByTestId('go-back').click()
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toContainText('The cave splits.')

  // The state-gated choice still behaves correctly after the undo: the
  // engine recomputed has_lantern=true by replaying the recorded path, it
  // did not reverse effects or drop the variable, so c_dark_passage is still
  // offered (and c_bright_tunnel too, ungated).
  await expect(page.getByTestId('choice-c_dark_passage')).toBeVisible()
  await expect(page.getByTestId('choice-c_bright_tunnel')).toBeVisible()

  // Go back is present again here (one recorded choice remains: c_take_lantern).
  await expect(page.getByTestId('go-back')).toBeVisible()

  // Taking the state-gated choice again reaches the same ending, proving the
  // replayed state is not corrupted, just recomputed.
  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('ending-id')).toHaveText('e_treasure_found')
})
