import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

import { loadLanternStory } from './support/fixtures'

const lantern = loadLanternStory()

// The reader lives at /read/:profileId/:storybookId/:version (ReaderRoute); the
// bare `/` renders the kid-surface Profile Picker (C4a-2, see profiles.spec.ts),
// and the LibraryPage stub lives at /library/:profileId (C4a-3). Neither is the
// reader. storybookId and version match the mocked s_lantern_cave story loaded
// in beforeEach.
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

test('a malformed story link shows an exit, not a dead end', async ({ page }) => {
  await page.goto('/read/child-a/s_lantern_cave/abc')
  await expect(page.getByText('That story link looks wrong')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to my books' })).toBeVisible()
})

test('a missing story shows not-found, not the offline copy', async ({ page }) => {
  // Override the beforeEach storybooks route with a 404 (last-registered route wins).
  await page.route('**/api/v1/storybooks/**', (route) =>
    route.fulfill({ status: 404, json: { error: 'not found' } })
  )
  await page.goto('/read/child-a/does_not_exist/1')
  await expect(page.getByText("We couldn't find that story")).toBeVisible()
  await expect(page.getByText(/save space/)).toHaveCount(0)
})

test('the reader column has no horizontal scroll at 390px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  )
  expect(overflow).toBe(false)
})

test('choice buttons meet the 44px tap target', async ({ page }) => {
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  const box = await page.getByTestId('choice-c_take_lantern').boundingBox()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
})

test('records a completion when the story reaches an ending', async ({ page }) => {
  const posted: unknown[] = []
  // Override the beforeEach completions route to capture the body (last wins).
  await page.route('**/api/v1/completions', (route) => {
    posted.push(route.request().postDataJSON())
    return route.fulfill({
      status: 200,
      json: {
        child_profile_id: 'child-a',
        storybook_id: 's_lantern_cave',
        version: 1,
        ending_id: 'e_treasure_found',
        found_at: new Date().toISOString(),
      },
    })
  })
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_take_lantern').click()
  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect.poll(() => posted.length).toBe(1)
  expect(posted[0]).toMatchObject({
    profile_id: 'child-a',
    storybook_id: 's_lantern_cave',
    version: 1,
    ending_id: 'e_treasure_found',
  })
})

test('shows the endings tracker on the ending screen once reading-history resolves (K6)', async ({
  page,
}) => {
  await page.route('**/api/v1/reading-history/**', (route) =>
    route.fulfill({
      json: {
        profile_id: 'child-a',
        books: [
          {
            storybook_id: 's_lantern_cave',
            title: 'The Lantern Cave',
            endings_found: 2,
            ending_ids: ['e_treasure_found', 'e_other'],
            total_endings: 4,
            in_progress: false,
            last_activity_at: new Date().toISOString(),
          },
        ],
      },
    })
  )
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_take_lantern').click()
  await page.getByTestId('choice-c_dark_passage').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()
  await expect(page.getByTestId('endings-tracker')).toHaveText(
    'You found ending 2 of 4! Read again to find more.'
  )
})

test('resumes from server state when the local cache is empty (cross-device)', async ({
  page,
}) => {
  const RESUMED_ROW = {
    current_node: 'n_cave_fork',
    var_state: { has_lantern: true },
    path: ['n_entrance', 'n_cave_fork'],
    visit_set: ['n_entrance', 'n_cave_fork'],
    version: 1,
    state_revision: 4,
    save_slots: {},
  }
  // Override the beforeEach reading-state route: GET returns a saved server row
  // (a fresh browser context has an empty IndexedDB, so the cold-cache fallback
  // must consult the server), PUT still succeeds.
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, json: RESUMED_ROW })
    }
    return route.fulfill({ status: 200, json: READING_ROW })
  })
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  // Resumed at the cave fork holding the lantern, so the gated dark-passage
  // choice is offered without first taking the lantern.
  await expect(page.getByTestId('choice-c_dark_passage')).toBeVisible()
})
