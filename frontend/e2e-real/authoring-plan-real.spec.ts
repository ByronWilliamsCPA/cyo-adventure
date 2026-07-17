import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'
import { BACKEND } from './real-stack'

/**
 * Real-API authoring-plan workflow: submit and approve a fresh story
 * request (Node-side, as setup), then drive the admin authoring-queue UI
 * against the real backend to build a skill-mechanism plan for it. Closes
 * the biggest gap found in the 2026-07-16 admin-role audit: the
 * authoring-plan endpoint had a full backend implementation and generated
 * client method but no frontend UI at all until this feature landed.
 *
 * Setup is a direct fetch (not through the browser), mirroring
 * real-stack.ts's authorizeDevice: mints the fixture this test needs rather
 * than depending on incidental state left by another spec.
 */

const DEV_GUARDIAN_BEARER = 'dev-guardian'
const DEV_ADMIN_BEARER = 'dev-admin'

async function createApprovedRequest(): Promise<string> {
  const profilesRes = await fetch(`${BACKEND}/api/v1/profiles`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
  })
  expect(profilesRes.ok, `GET /profiles failed (HTTP ${profilesRes.status})`).toBe(true)
  const { profiles } = (await profilesRes.json()) as { profiles: { id: string }[] }
  expect(profiles.length, 'seeded dev stack must have at least one profile').toBeGreaterThan(0)

  const createRes = await fetch(`${BACKEND}/api/v1/story-requests`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      profile_id: profiles[0].id,
      request_text: `An e2e-real authoring-plan check ${Date.now()}`,
    }),
  })
  expect(createRes.ok, `POST /story-requests failed (HTTP ${createRes.status})`).toBe(true)
  const { id } = (await createRes.json()) as { id: string }

  const approveRes = await fetch(`${BACKEND}/api/v1/story-requests/${id}/approve`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${DEV_ADMIN_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ age_band: '10-13', length: 'short', narrative_style: 'prose' }),
  })
  expect(approveRes.ok, `POST /approve failed (HTTP ${approveRes.status})`).toBe(true)
  return id
}

test('an admin builds a real skill-mechanism authoring plan for a freshly approved request', async ({
  page,
  context,
}) => {
  const requestId = await createApprovedRequest()
  await seedGuardianSession(context, DEV_ADMIN_BEARER)

  await page.goto('/admin/authoring-queue')
  await expect(page.getByRole('heading', { name: 'Authoring queue' })).toBeVisible()

  const row = page.getByTestId(`request-${requestId}`)
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: 'Build authoring plan' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // Skill mechanism is the default, and its prep model defaults to the
  // first recognized Claude Code session model; no input is required.
  await page.getByRole('button', { name: 'Create plan' }).click()

  // The dialog closes and the row disappears only on a real 201 from the
  // backend; a reload confirms the request no longer shows as approved
  // (it has moved past this step, into generation).
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(row).not.toBeVisible()
  await page.reload()
  await expect(page.getByTestId(`request-${requestId}`)).not.toBeVisible()
})

test('an admin builds a real automated-provider plan constrained to the real allowlist', async ({
  page,
  context,
}) => {
  const requestId = await createApprovedRequest()
  await seedGuardianSession(context, DEV_ADMIN_BEARER)

  await page.goto('/admin/authoring-queue')
  const row = page.getByTestId(`request-${requestId}`)
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: 'Build authoring plan' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // prep_model becomes free text only once mechanism is switched away from
  // 'skill' (it's a <select> until then); switch first, then fill.
  await page.getByRole('radio', { name: 'Automated provider' }).click()
  await page.getByLabel('Prep model').fill('claude-sonnet-4-6')
  // The dev seed's DEFAULT_ALLOWLIST includes an enabled anthropic entry
  // (scripts/seed_dev_data.py / generation/allowlist.py); this proves the
  // dialog's provider/model dropdowns are populated from the REAL allowlist
  // table, not a hardcoded list.
  await page.getByRole('combobox', { name: /^Provider/ }).selectOption('anthropic')
  await page.getByRole('combobox', { name: /^Model/ }).selectOption('claude-sonnet-4-6')
  await page.getByRole('button', { name: 'Create plan' }).click()

  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(row).not.toBeVisible()
})
