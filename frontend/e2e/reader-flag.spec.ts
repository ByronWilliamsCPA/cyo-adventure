import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * Coverage for the K15 "Tell a grown-up" flag button in the reader chrome.
 * Mirrors reader.spec.ts's convention: `page.route` mocks against
 * `**\/api/v1/...`, no live backend, and an `addInitScript` auth token so
 * `useApi`'s request interceptor attaches an Authorization header.
 *
 * The flag button is hidden without a valid child session for the routed
 * profile (see FlagButton.tsx); reader.spec.ts's beforeEach only seeds the
 * guardian-style `auth_token`, so this file additionally seeds a real
 * `child_session` blob matching auth/childSession.ts's storage format.
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
    window.localStorage.setItem(
      'child_session',
      JSON.stringify({
        token: 'child-a-session-token',
        expiresAt: '2100-01-01T00:00:00Z',
        profileId: 'child-a',
      })
    )
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

test('submitting a reason posts the structured flag and shows the kid-language confirmation', async ({
  page,
}) => {
  let flagBody: unknown = null
  await page.route('**/api/v1/flags', (route) => {
    flagBody = route.request().postDataJSON()
    return route.fulfill({ status: 201, json: { id: 'flag-1', reason: 'scared_me' } })
  })

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  await page.getByRole('button', { name: 'Tell a grown-up' }).click()
  const dialog = page.getByRole('dialog', { name: 'Tell a grown-up' })
  await expect(dialog).toBeVisible()
  // Exactly three structured reasons, no free-text field.
  await expect(dialog.getByRole('textbox')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'It scared me' }).click()

  await expect(
    page.getByText("Thanks for telling us. A grown-up will take a look.")
  ).toBeVisible()
  expect(flagBody).toMatchObject({
    profile_id: 'child-a',
    storybook_id: 's_lantern_cave',
    version: 1,
    reason: 'scared_me',
    node_id: 'n_entrance',
  })
})

test('a 409 cap response shows the gentle "told us a lot already" message', async ({ page }) => {
  await page.route('**/api/v1/flags', (route) =>
    route.fulfill({ status: 409, json: { detail: 'open flag cap reached' } })
  )

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  await page.getByRole('button', { name: 'Tell a grown-up' }).click()
  await page.getByRole('dialog', { name: 'Tell a grown-up' }).getByRole('button', { name: 'It was confusing' }).click()

  await expect(page.getByText("You've told us a lot already.")).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('a failed flag submit still reassures the child and never dead-ends them', async ({
  page,
}) => {
  // The most emotionally sensitive path in the app: a child reported distress
  // and the POST failed. They must never see a scary "something went wrong"
  // alert or be trapped in the dialog. They get the same gentle confirmation
  // as success and can keep reading; the failure is logged, not surfaced.
  await page.route('**/api/v1/flags', (route) =>
    route.fulfill({ status: 500, json: { detail: 'internal server error' } })
  )

  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()

  await page.getByRole('button', { name: 'Tell a grown-up' }).click()
  await page
    .getByRole('dialog', { name: 'Tell a grown-up' })
    .getByRole('button', { name: 'It scared me' })
    .click()

  // Reassured with the exact success copy, never a scary error alert.
  await expect(
    page.getByText('Thanks for telling us. A grown-up will take a look.')
  ).toBeVisible()
  await expect(page.getByText('Something went wrong. Try again.')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  // Not a dead end: the dialog closes and the reader stays fully usable.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByTestId('reader')).toBeVisible()
})

test('the flag button is hidden without a valid child session', async ({ page, context }) => {
  // Override the seeded child_session with nothing: a guardian browsing the
  // reader directly (device-grant + guardian-style token only, per
  // reader.spec.ts's own beforeEach) has no child session minted.
  await context.addInitScript(() => {
    window.localStorage.removeItem('child_session')
  })
  await page.goto(READER_PATH)
  await expect(page.getByTestId('reader')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tell a grown-up' })).toHaveCount(0)
})
