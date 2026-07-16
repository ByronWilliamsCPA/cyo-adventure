import { expect, test } from '@playwright/test'

import { mockMe, seedGuardianSession } from './support/auth'

/**
 * Mocked-tier E2E for the admin authoring-queue page: the step between a
 * guardian/admin approving a story request (age_band/length/narrative_style
 * already locked in) and generation starting, where an admin picks the
 * authoring method/mechanism and, for an automated provider, the specific
 * model (validated against the provider allowlist).
 */

const APPROVED_REQUEST = {
  id: 'req-1',
  profile_id: 'p1',
  status: 'approved',
  request_text: 'A story about a friendly dragon',
  moderation_flags: [],
  created_at: '2026-07-04T10:00:00Z',
  initiator_role: 'child',
  age_band: '8-11',
  length: 'short',
  narrative_style: 'prose',
  series_id: null,
  proposed_series_title: null,
  anchor_storybook_id: null,
}

const ALLOWLIST = {
  rows: [
    {
      id: 'a1',
      provider: 'anthropic',
      model_id: 'claude-sonnet-4-6',
      enabled: true,
      display_name: 'Claude Sonnet 4.6 (direct)',
    },
  ],
}

test.beforeEach(async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await page.route('**/api/v1/admin/story-requests?status=approved', (route) =>
    route.fulfill({ json: { requests: [APPROVED_REQUEST] } })
  )
  await page.route('**/api/v1/admin/provider-allowlist', (route) =>
    route.fulfill({ json: ALLOWLIST })
  )
})

test('an admin builds a skill-mechanism authoring plan and the row disappears', async ({
  page,
}) => {
  let posted: Record<string, unknown> | null = null
  await page.route('**/api/v1/story-requests/req-1/authoring-plan', (route) => {
    posted = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 201,
      json: {
        request_id: 'req-1',
        concept_id: 'c1',
        job_id: 'job-1',
        method: 'skeleton_fill',
        mechanism: 'skill',
        status: 'queued',
        skeleton_alternatives: [],
        warnings: [],
      },
    })
  })

  await page.goto('/admin/authoring-queue')
  await expect(page.getByRole('heading', { name: 'Authoring queue' })).toBeVisible()
  await expect(page.getByText('A story about a friendly dragon')).toBeVisible()
  await expect(page.getByText('8-11 · short · prose')).toBeVisible()

  await page.getByRole('button', { name: 'Build authoring plan' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  // Skill mechanism is the default, and its prep model defaults to the
  // first recognized Claude Code session model; no input is required.
  await page.getByRole('button', { name: 'Create plan' }).click()

  await expect.poll(() => posted).toMatchObject({
    method: 'skeleton_fill',
    mechanism: 'skill',
    prep_model: 'sonnet',
  })
  await expect(page.getByText('A story about a friendly dragon')).not.toBeVisible()
})

test('an automated-provider plan is constrained to the enabled allowlist', async ({ page }) => {
  let posted: Record<string, unknown> | null = null
  await page.route('**/api/v1/story-requests/req-1/authoring-plan', (route) => {
    posted = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 201,
      json: {
        request_id: 'req-1',
        concept_id: 'c1',
        job_id: 'job-1',
        method: 'skeleton_fill',
        mechanism: 'automated_provider',
        status: 'queued',
        skeleton_alternatives: [],
        warnings: [],
      },
    })
  })

  await page.goto('/admin/authoring-queue')
  await page.getByRole('button', { name: 'Build authoring plan' }).click()
  // prep_model becomes free text only once mechanism is switched away from
  // 'skill' (it's a <select> until then); switch first, then fill.
  await page.getByRole('radio', { name: 'Automated provider' }).click()
  await page.getByLabel('Prep model').fill('claude-sonnet-4-6')
  // Scoped by role (combobox), not getByLabel: a <select> wrapped by its
  // <label> computes an accessible name that includes the select's own
  // rendered option text (e.g. "ProviderChoose…anthropic"), which collides
  // with the "Automated provider" radio's label on plain substring
  // matching. Role scoping sidesteps the collision entirely (radio vs
  // combobox), and the ^-anchored regex tolerates the concatenated tail.
  await page.getByRole('combobox', { name: /^Provider/ }).selectOption('anthropic')
  await page.getByRole('combobox', { name: /^Model/ }).selectOption('claude-sonnet-4-6')
  await page.getByRole('button', { name: 'Create plan' }).click()

  await expect.poll(() => posted).toMatchObject({
    mechanism: 'automated_provider',
    provider: 'anthropic',
    model: 'claude-sonnet-4-6',
  })
})

test('fresh generation forces the automated-provider mechanism', async ({ page }) => {
  await page.goto('/admin/authoring-queue')
  await page.getByRole('button', { name: 'Build authoring plan' }).click()
  await page.getByRole('radio', { name: 'Fresh generation' }).click()
  await expect(page.getByRole('radio', { name: /cyo-author skill/ })).toBeDisabled()
  await expect(page.getByRole('radio', { name: 'Automated provider' })).toBeChecked()
})
