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
 */

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
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
  await page.getByRole('textbox').fill('A brave fox who solves mysteries')
  await page.getByRole('button', { name: /^send$/i }).click()

  await expect.poll(() => createCalls).toBe(1)
  expect(createBody).toEqual({
    profile_id: 'p1',
    request_text: 'A brave fox who solves mysteries',
  })
  await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
})
