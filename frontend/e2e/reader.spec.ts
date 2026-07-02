import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
const lantern = JSON.parse(
  readFileSync(path.resolve(here, '../../schema/conformance/player_traces.json'), 'utf-8')
).traces[0].story

// The reader lives at /read/:profileId/:storybookId/:version (ReaderRoute); the
// bare `/` renders the LibraryPage stub (C4a-2/C4a-3), not the reader. storybookId
// and version match the mocked s_lantern_cave story loaded in beforeEach.
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
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    return route.fulfill({ status: 200, json: READING_ROW })
  })
})

test('plays a downloaded story to an ending (US-101)', async ({ page }) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_take_lantern').click()
  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('ending-id')).toHaveText('e_treasure_found')
})

test('plays to an ending with the network disabled', async ({ page, context }) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  // The story is loaded; disable the network and finish reading offline.
  await context.setOffline(true)
  await page.getByTestId('choice-c_ignore_lantern').click()
  await page.getByTestId('choice-c_bright_tunnel').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('ending-id')).toHaveText('e_safe_exit')
})

test('state-gated choice is hidden until its condition holds (US-102)', async ({ page }) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_ignore_lantern').click()
  // Without the lantern, the dark passage is not offered.
  await expect(page.getByTestId('choice-c_dark_passage')).toHaveCount(0)
  await expect(page.getByTestId('choice-c_bright_tunnel')).toBeVisible()
})
