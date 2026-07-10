import { expect, test } from '@playwright/test'

/**
 * Coverage for the kid "Request a story" affordance mounted on the library
 * page (Task K3). Mirrors library.spec.ts's convention: `page.route` mocks
 * against `**\/api/v1/...`, no live backend, and an `addInitScript` auth
 * token so `useApi`'s request interceptor attaches an Authorization header
 * (the mocked routes don't check it, but it matches the real app's request
 * shape). Unlike the guardian requests surface (story-requests.spec.ts), the
 * kid library route does not mount GuardianAuthLayout, so no Supabase
 * session needs to be seeded here, same as library.spec.ts.
 *
 * WS-B PR 3: RequestStory.tsx now renders a second text input (the optional
 * series name) alongside the idea textarea whenever the form is open and no
 * continuation anchor is set, so `page.getByRole('textbox')` with no name
 * filter is ambiguous once the form opens; every locator below scopes to the
 * idea textarea's accessible name instead.
 */

const IDEA_LABEL = 'What should your story be about?'
const SERIES_LABEL = 'Part of a series? Give it a name! (optional)'

// KidNav (mounted by KidShell on every /library/:profileId route) fetches
// GET /api/v1/profiles unconditionally, same as the picker (see
// profiles.spec.ts). Every test in this file navigates to /library/p1, so the
// mock lives in beforeEach alongside the auth token init script.
const PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Remy',
      age_band: '6-8',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

test.beforeEach(async ({ context, page }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
})

test('typing an idea and sending it posts the request and shows the pending status', async ({
  page,
}) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

  let createCalls = 0
  let createBody: unknown = null
  let requests: Array<{ id: string; status: string }> = []
  await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
    route.fulfill({ json: { requests } })
  )
  await page.route('**/api/v1/story-requests', (route) => {
    // Only POST create requests reach this pattern: the list GET above always
    // carries a `?profile_id=` query string, which this bare-path glob does
    // not match.
    createCalls += 1
    createBody = route.request().postDataJSON()
    requests = [{ id: 'req-1', status: 'pending' }]
    return route.fulfill({ json: { id: 'req-1', status: 'pending' } })
  })

  await page.goto('/library/p1')

  await expect(page.getByText('No books yet')).toBeVisible()
  await page.getByRole('button', { name: 'Request a story' }).click()
  await page.getByLabel(IDEA_LABEL).fill('A brave fox who solves mysteries')
  await page.getByRole('button', { name: /^send$/i }).click()

  await expect.poll(() => createCalls).toBe(1)
  expect(createBody).toEqual({
    profile_id: 'p1',
    request_text: 'A brave fox who solves mysteries',
  })
  await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
})

test('filling the series name posts the proposed series title, not an anchor', async ({ page }) => {
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

  let createCalls = 0
  let createBody: unknown = null
  await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/story-requests', (route) => {
    createCalls += 1
    createBody = route.request().postDataJSON()
    return route.fulfill({ json: { id: 'req-2', status: 'pending' } })
  })

  await page.goto('/library/p1')

  await page.getByRole('button', { name: 'Request a story' }).click()
  await page.getByLabel(IDEA_LABEL).fill('A fox who starts a detective club')
  await page.getByLabel(SERIES_LABEL).fill('Fox Tales')
  await page.getByRole('button', { name: /^send$/i }).click()

  await expect.poll(() => createCalls).toBe(1)
  expect(createBody).toEqual({
    profile_id: 'p1',
    request_text: 'A fox who starts a detective club',
    proposed_series_title: 'Fox Tales',
  })
})

test('tapping "Continue this story" anchors the request to that book', async ({ page }) => {
  const stories = {
    stories: [
      {
        id: 's1',
        title: 'The Lantern',
        version: 2,
        age_band: '6-8',
        tier: 1,
        reading_level_target: 2,
        node_count: 10,
        rating: null,
        progress: null,
        series_id: 'ser-1',
        book_index: 1,
      },
      {
        id: 's3',
        title: 'Acorn Detectives',
        version: 1,
        age_band: '6-8',
        tier: 1,
        reading_level_target: 2,
        node_count: 8,
        rating: 3,
        progress: null,
        series_id: null,
        book_index: null,
      },
    ],
  }
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))

  let createCalls = 0
  let createBody: unknown = null
  await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
    route.fulfill({ json: { requests: [] } })
  )
  await page.route('**/api/v1/story-requests', (route) => {
    createCalls += 1
    createBody = route.request().postDataJSON()
    return route.fulfill({ json: { id: 'req-3', status: 'pending' } })
  })

  await page.goto('/library/p1')

  const shelf = page.getByRole('region', { name: 'More to Explore' })
  await shelf
    .getByRole('listitem')
    .filter({ hasText: 'The Lantern' })
    .getByRole('button', { name: 'Continue this story' })
    .click()

  await expect(page.getByText('Continuing: The Lantern')).toBeVisible()
  await expect(page.getByLabel(SERIES_LABEL)).toHaveCount(0)
  await page.getByLabel(IDEA_LABEL).fill('More lantern light adventures')
  await page.getByRole('button', { name: /^send$/i }).click()

  await expect.poll(() => createCalls).toBe(1)
  expect(createBody).toEqual({
    profile_id: 'p1',
    request_text: 'More lantern light adventures',
    anchor_storybook_id: 's1',
  })
})
