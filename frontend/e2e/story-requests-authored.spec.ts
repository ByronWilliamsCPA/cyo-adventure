import { expect, test } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * Guardian/admin "authored" story request (WS-B PR2) e2e: the pre-approved
 * request form (src/guardian/RequestStoryForm.tsx) that skips the child
 * free-text moderation queue. Guardian mode renders on RequestsPage
 * (src/guardian/RequestsPage.tsx, /guardian/requests) with an optional child
 * selector; admin mode renders on ConsolePage (src/guardian/ConsolePage.tsx,
 * the guardian surface's index route at /guardian) with a required family
 * selector and no child selector. See RequestStoryForm.tsx's header comment
 * for why the guardian body never carries family_id and the admin body never
 * carries profile_id.
 *
 * Auth seeding and /api/v1/me mocking use the shared support/auth.ts helpers
 * (the pattern established by guardian-console.spec.ts), rather than
 * story-requests.spec.ts's inlined session object, since those helpers now
 * exist and are the repo's current convention.
 */

const CHILD_PROFILE = {
  id: 'p1',
  display_name: 'Ada',
  age_band: '5-8',
  reading_level_cap: 2,
  avatar: null,
  tts_enabled: false,
  created_at: '2026-07-04T10:00:00Z',
}

const FAMILY = { id: 'fam-1', name: 'The Rivera Family' }

test.describe('guardian authored request (RequestsPage)', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page)
    // Empty pending queue: RequestsPage's own row-level "Age band"/"Story
    // length" labels would otherwise collide with the form's identically
    // labeled fields.
    await page.route('**/api/v1/story-requests?status=pending', (route) =>
      route.fulfill({ json: { requests: [] } })
    )
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ json: { profiles: [CHILD_PROFILE] } })
    )
  })

  test('submitting with a child selected posts profile_id, the child band, and no family_id', async ({
    page,
  }) => {
    let requestBody: unknown = null
    await page.route('**/api/v1/story-requests/authored', (route) => {
      requestBody = route.request().postDataJSON()
      return route.fulfill({
        status: 201,
        json: { id: 'req-9', status: 'approved', concept_id: 'concept-9' },
      })
    })

    await page.goto('/guardian/requests')

    await page.getByLabel('Child (optional)').selectOption(CHILD_PROFILE.id)
    await expect(page.getByLabel('Age band')).toHaveValue(CHILD_PROFILE.age_band)
    await page.getByLabel('What should the story be about?').fill('A story about a kind robot')
    await page.getByLabel('Story length').selectOption('medium')
    // Tie the wait to the mocked response rather than a bare visibility
    // timeout: under parallel-worker load the round trip can outrun the
    // default 5s expect timeout even though the UI update itself is instant.
    await Promise.all([
      page.waitForResponse('**/api/v1/story-requests/authored'),
      page.getByRole('button', { name: 'Send request' }).click(),
    ])

    await expect(page.getByText('Request approved and sent for authoring.')).toBeVisible()
    expect(requestBody).toEqual({
      request_text: 'A story about a kind robot',
      age_band: CHILD_PROFILE.age_band,
      length: 'medium',
      narrative_style: 'prose',
      profile_id: CHILD_PROFILE.id,
    })
  })

  test('a blocked response shows the blocked notice, not the success notice', async ({ page }) => {
    await page.route('**/api/v1/story-requests/authored', (route) =>
      route.fulfill({
        status: 201,
        json: { id: 'req-10', status: 'blocked', concept_id: null },
      })
    )

    await page.goto('/guardian/requests')

    await page.getByLabel('What should the story be about?').fill('A scary story')
    await page.getByLabel('Age band').selectOption('8-11')
    await page.getByLabel('Story length').selectOption('medium')
    await page.getByRole('button', { name: 'Send request' }).click()

    await expect(
      page.getByRole('alert').filter({ hasText: 'did not pass our content check' })
    ).toBeVisible()
    await expect(page.getByText('Request approved and sent for authoring.')).toHaveCount(0)
  })
})

test.describe('admin authored request (ConsolePage)', () => {
  test.beforeEach(async ({ page, context }) => {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
    await mockEmptyConsole(page)
    // ConsolePage's onboarding-nudge read; not under test here.
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: { profiles: [] } }))
    await page.route('**/api/v1/admin/families', (route) =>
      route.fulfill({ json: { families: [FAMILY] } })
    )
  })

  test('submitting posts family_id and no profile_id, with no child selector rendered', async ({
    page,
  }) => {
    let requestBody: unknown = null
    await page.route('**/api/v1/story-requests/authored', (route) => {
      requestBody = route.request().postDataJSON()
      return route.fulfill({
        status: 201,
        json: { id: 'req-11', status: 'approved', concept_id: 'concept-11' },
      })
    })

    await page.goto('/guardian')

    await expect(page.getByLabel('Child (optional)')).toHaveCount(0)
    await page.getByLabel('Family').selectOption(FAMILY.id)
    await page.getByLabel('What should the story be about?').fill('A story for the whole family')
    await page.getByLabel('Age band').selectOption('8-11')
    await page.getByLabel('Story length').selectOption('short')
    await Promise.all([
      page.waitForResponse('**/api/v1/story-requests/authored'),
      page.getByRole('button', { name: 'Send request' }).click(),
    ])

    await expect(page.getByText('Request approved and sent for authoring.')).toBeVisible()
    expect(requestBody).toEqual({
      request_text: 'A story for the whole family',
      age_band: '8-11',
      length: 'short',
      narrative_style: 'prose',
      family_id: FAMILY.id,
    })
  })
})
