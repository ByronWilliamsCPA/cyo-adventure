import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'

const SERIES_ID = 'ser-e2e-1'

function seriesBlock(bookIndex: number, entry: string) {
  return {
    series_id: SERIES_ID,
    book_index: bookIndex,
    series_entry_node: entry,
    is_final: false,
    carries_state: true,
  }
}

const BOOK1 = {
  schema_version: '2.0',
  id: 's_ember_1',
  version: 1,
  title: 'Ember Trail 1',
  metadata: { series: seriesBlock(1, 'n_b1_start') },
  variables: [{ name: 'courage', type: 'int', initial: 0, min: 0, max: 5 }],
  start_node: 'n_b1_start',
  nodes: [
    {
      id: 'n_b1_start',
      body: 'The trail begins.',
      is_ending: false,
      choices: [
        {
          id: 'c_brave',
          label: 'Face the ember wolf',
          target: 'n_b1_end',
          effects: [{ op: 'set', var: 'courage', value: 3 }],
        },
      ],
    },
    {
      id: 'n_b1_end',
      body: 'You did it.',
      is_ending: true,
      ending: { id: 'e_b1_done', valence: 'positive', kind: 'success', title: 'Brave!' },
      choices: [],
    },
  ],
}

// Book 2's default start_node (n_b2_intro) deliberately DIVERGES from its
// series_entry_node (n_b2_start). A continuation must land on the entry node,
// not the default start, so a reader that ignored the carried entry node would
// render the prologue body instead: the assertions below catch exactly that.
const BOOK2 = {
  schema_version: '2.0',
  id: 's_ember_2',
  version: 1,
  title: 'Ember Trail 2',
  metadata: { series: seriesBlock(2, 'n_b2_start') },
  variables: [{ name: 'courage', type: 'int', initial: 0, min: 0, max: 5 }],
  start_node: 'n_b2_intro',
  nodes: [
    {
      id: 'n_b2_intro',
      body: 'Prologue nobody should reach on a continuation.',
      is_ending: false,
      choices: [{ id: 'c_intro', label: 'Begin', target: 'n_b2_start' }],
    },
    {
      id: 'n_b2_start',
      body: 'The trail continues.',
      is_ending: false,
      choices: [
        {
          id: 'c_carried',
          label: 'Roar with carried courage',
          target: 'n_b2_end',
          condition: { '>=': [{ var: 'courage' }, 2] },
        },
        { id: 'c_plain', label: 'Walk on', target: 'n_b2_end' },
      ],
    },
    {
      id: 'n_b2_end',
      body: 'Onward.',
      is_ending: true,
      ending: { id: 'e_b2_done', valence: 'positive', kind: 'success', title: 'Done' },
      choices: [],
    },
  ],
}

const SERIES_NEXT = {
  next: {
    storybook_id: 's_ember_2',
    version: 1,
    title: 'Ember Trail 2',
    series_entry_node: 'n_b2_start',
    carries_state: true,
  },
}

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-a')
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute; without a
  // valid device grant /read/* redirects to guardian login.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/storybooks/s_ember_1/**', (route) =>
    route.fulfill({ json: BOOK1 })
  )
  await page.route('**/api/v1/storybooks/s_ember_2/**', (route) =>
    route.fulfill({ json: BOOK2 })
  )
  await page.route('**/api/v1/series-next/**', (route) =>
    route.fulfill({ json: SERIES_NEXT })
  )
  await page.route('**/api/v1/reading-state/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 404, json: { error: 'not found' } })
    }
    const body = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 200,
      json: { ...body, state_revision: (body.state_revision as number) + 1 },
    })
  })
  await page.route('**/api/v1/completions', (route) =>
    route.fulfill({
      status: 200,
      json: {
        child_profile_id: 'child-a',
        storybook_id: 's_ember_1',
        version: 1,
        ending_id: 'e_b1_done',
        found_at: new Date().toISOString(),
      },
    })
  )
})

test('continues a series into the next book with carried state', async ({ page }) => {
  await page.goto('/read/child-a/s_ember_1/1')
  await expect(page.getByTestId('reader')).toBeVisible()
  await page.getByTestId('choice-c_brave').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()

  const continueButton = page.getByTestId('continue-series')
  await expect(continueButton).toBeVisible()
  await continueButton.click()

  // The continuation navigates to book 2's route...
  await expect(page).toHaveURL(/\/read\/child-a\/s_ember_2\/1/)
  // ...and opens at its series ENTRY node (n_b2_start), which now diverges from
  // book 2's default start_node (n_b2_intro): the entry-node body shows and the
  // prologue never does, so this proves a real transition to the entry node
  // rather than a tautology where start_node == entry_node.
  await expect(page.getByTestId('passage-body')).toContainText('The trail continues.')
  await expect(page.getByTestId('passage-body')).not.toContainText('Prologue')
  // ...and the carried courage (3) makes the conditional choice visible.
  await expect(page.getByTestId('choice-c_carried')).toBeVisible()
})
