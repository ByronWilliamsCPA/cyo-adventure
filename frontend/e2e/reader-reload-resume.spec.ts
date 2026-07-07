import { expect, test } from '@playwright/test'

import { loadLanternStory } from './support/fixtures'

const lantern = loadLanternStory()

const READER_PATH = '/read/child-a/s_lantern_cave/1'

/**
 * Same-device reload-resume (closes #62). offline/sync.ts's saveProgress
 * writes each step to the local IndexedDB cache before it ever touches the
 * network, and ReaderPage.load() reads that local cache before falling back
 * to a server fetch. A same-tab page.reload() keeps the browser's IndexedDB
 * intact, so this exercises the real local-first persistence path end to end:
 * no mocked "resume" response, just genuine save-then-reload behaviour.
 */

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
})

test('reloading the same device resumes at the same node, not the start', async ({ page }) => {
  let revision = 0
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    const body = route.request().postDataJSON() as Record<string, unknown>
    revision += 1
    return route.fulfill({ status: 200, json: { ...body, state_revision: revision } })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toHaveText('A lantern lies near the entrance.')

  await page.getByTestId('choice-c_take_lantern').click()
  await expect(page.getByTestId('passage-body')).toHaveText('The cave splits.')

  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  const passageBeforeReload = await page.getByTestId('passage-body').innerText()
  expect(passageBeforeReload).toBe('Treasure!')

  // Let the mount-time save and both choice saves reach the local cache. Each
  // save writes IndexedDB before its network PUT is even sent (offline/sync.ts:
  // saveProgress awaits putReadingState before calling the API), so observing
  // 3 PUTs here guarantees the ending state is already persisted locally.
  await expect.poll(() => revision).toBeGreaterThanOrEqual(3)

  await page.reload()

  // Resumes straight into the same ending: the same passage text as before
  // the reload, with the ending screen shown immediately and the story's
  // start node never re-displayed.
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('passage-body')).toHaveText(passageBeforeReload)
  await expect(page.getByText('A lantern lies near the entrance.')).toHaveCount(0)
})
