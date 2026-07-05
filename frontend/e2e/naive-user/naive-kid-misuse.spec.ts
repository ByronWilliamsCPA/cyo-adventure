import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
const lantern = JSON.parse(
  readFileSync(path.resolve(here, '../../../schema/conformance/player_traces.json'), 'utf-8')
).traces[0].story

/**
 * Naive kid misuse: a child using the app alone, unsupervised, prone to
 * double-clicking, refreshing mid-story, and rating things twice. Not a
 * re-run of story-requests-kid.spec.ts / library.spec.ts / reader.spec.ts,
 * which cover the happy paths these tests build on.
 */

test.describe('double-submitting a story request', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
  })

  test('double-clicking Send only creates one story request', async ({ page }) => {
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

    let createCalls = 0
    let requests: Array<{ id: string; status: string }> = []
    await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
      route.fulfill({ json: { requests } })
    )
    await page.route('**/api/v1/story-requests', async (route) => {
      createCalls += 1
      // Hold the response open briefly so an impatient second click has a
      // real window to land while the guard should already be active.
      await new Promise((resolve) => setTimeout(resolve, 300))
      requests = [{ id: 'req-1', status: 'pending' }]
      return route.fulfill({ json: { id: 'req-1', status: 'pending' } })
    })

    await page.goto('/library/p1')
    await page.getByRole('button', { name: 'Request a story' }).click()
    await page.getByRole('textbox').fill('A brave fox who solves mysteries')

    const sendButton = page.getByRole('button', { name: /send/i })
    await sendButton.click()
    // RequestStory.tsx's saving-flag guard disables the button synchronously;
    // force bypasses Playwright's own enabled-check to simulate a kid
    // mashing it anyway. A genuinely disabled button does not dispatch a
    // click handler even when forced, so this cannot double-count.
    // Note: After first click, button text changes to "Sending…", but the
    // more flexible regex /send/i still matches.
    await sendButton.click({ force: true })

    await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
    expect(createCalls).toBe(1)
  })
})

test.describe('refresh mid-reader', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
  })

  test('a clean refresh (not the offline/409 case) does not lose reading position', async ({
    page,
  }) => {
    const READER_PATH = '/read/child-fox/s_lantern_cave/1'
    let currentNode = 'n_entrance'

    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        if (currentNode === 'n_entrance') {
          return route.fulfill({ status: 404, json: { error: 'not found' } })
        }
        return route.fulfill({
          status: 200,
          json: {
            current_node: currentNode,
            var_state: { has_lantern: true },
            path: ['n_entrance', currentNode],
            visit_set: ['n_entrance', currentNode],
            version: 1,
            state_revision: 2,
            save_slots: {},
          },
        })
      }
      const body = route.request().postDataJSON() as { current_node: string }
      currentNode = body.current_node
      return route.fulfill({
        status: 200,
        json: {
          current_node: currentNode,
          var_state: { has_lantern: true },
          path: ['n_entrance', currentNode],
          visit_set: ['n_entrance', currentNode],
          version: 1,
          state_revision: 2,
          save_slots: {},
        },
      })
    })

    await page.goto(READER_PATH)
    await expect(page.getByTestId('reader')).toBeVisible()
    await page.getByTestId('choice-c_take_lantern').click()

    // Wait for the reading state to be posted before refreshing
    await page.waitForLoadState('networkidle')
    await page.reload()

    await expect(page.getByTestId('reader')).toBeVisible()
    // The gated dark-passage choice requires has_lantern: true, which only
    // holds if the refreshed reader resumed past the entrance, not reset to it.
    await expect(page.getByTestId('choice-c_dark_passage')).toBeVisible()
  })
})

test.describe('rating twice', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
  })

  test('rating a story twice keeps only the latest value', async ({ page }) => {
    const stories = {
      stories: [
        {
          id: 's3',
          title: 'Acorn Detectives',
          version: 1,
          age_band: '6-8',
          tier: 1,
          reading_level_target: 2,
          node_count: 8,
          rating: null,
          progress: null,
        },
      ],
    }
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))

    const ratingBodies: unknown[] = []
    await page.route('**/api/v1/ratings', (route) => {
      ratingBodies.push(route.request().postDataJSON())
      return route.fulfill({
        json: {
          child_profile_id: 'p1',
          storybook_id: 's3',
          value: 3,
          rated_at: '2026-07-05T00:00:00Z',
          updated_at: '2026-07-05T00:00:00Z',
        },
      })
    })

    await page.goto('/library/p1')
    const shelf = page.getByRole('region', { name: 'More to Explore' })
    await shelf.getByRole('button', { name: '5 stars' }).click()
    await shelf.getByRole('button', { name: '3 stars' }).click()

    expect(ratingBodies).toEqual([
      { profile_id: 'p1', storybook_id: 's3', value: 5 },
      { profile_id: 'p1', storybook_id: 's3', value: 3 },
    ])
    await expect(shelf.getByRole('button', { name: '3 stars' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    await expect(shelf.getByRole('button', { name: '5 stars' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })
})
