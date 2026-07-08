import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { requireBackend } from './real-stack'

/**
 * Real-API authored story request (WS-B PR2): a guardian submits the
 * pre-approved "Request a story" form on RequestsPage
 * (src/guardian/RequestStoryForm.tsx, mode="guardian") with no route mocks;
 * the POST to /api/v1/story-requests/authored hits uvicorn through the
 * preview proxy, authorized as the seeded dev-guardian subject
 * (ENVIRONMENT=local trusts the bearer token, mirroring approval-flow.spec.ts).
 *
 * Kept minimal per the task brief: no child is selected (the seeded
 * dev-guardian's children are not guaranteed to exist or match a specific
 * band), so the request rides the guardian's own family with an
 * explicitly-chosen age band and length. This only asserts the success
 * notice; it does not invent new real-stack seeding helpers.
 */

test.beforeEach(async ({ context }) => {
  await requireBackend()
  await seedGuardianSession(context, 'dev-guardian')
})

test('a guardian submits an authored request and sees the success notice', async ({ page }) => {
  await page.goto('/guardian/requests')

  await page
    .getByLabel('What should the story be about?')
    .fill('A story about a lighthouse keeper')
  await page.getByLabel('Age band').selectOption('8-11')
  await page.getByLabel('Story length').selectOption('short')
  await page.getByRole('button', { name: 'Send request' }).click()

  await expect(page.getByText('Request approved and sent for authoring.')).toBeVisible()
})
