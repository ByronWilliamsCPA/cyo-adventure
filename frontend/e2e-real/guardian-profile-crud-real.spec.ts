import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { BACKEND, requireBackend, resetRealState } from './real-stack'

/**
 * Real-API guardian profile CRUD (Phase 3.1 write-path backfill): the
 * guardian console's create and edit round-trip through the real
 * POST/PATCH /api/v1/profiles endpoints (no route mocks, unlike
 * guardian-profiles.spec.ts in the mocked tier), then a direct real DELETE
 * against the same resource.
 *
 * ProfilesPage.tsx deliberately has no delete control ("Deletion is
 * deferred: it cascades into reading state and ratings" per its docstring),
 * so the only way to exercise the real erasure path
 * (api/profiles.py::delete_profile, GDPR Article 17 / COPPA 312.10) is a
 * direct authenticated fetch, mirroring authoring-plan-real.spec.ts's
 * Node-side setup pattern rather than inventing a new helper in
 * real-stack.ts for a single call site.
 *
 * #ASSUME: data-integrity: a timestamp-suffixed display name keeps the
 * create idempotent across the two consecutive runs the validation step
 * requires; scripts/seed_dev_data.py and _reset.setup.ts never touch
 * hand-created profiles, so a stable name would not fail but would
 * accumulate rows across runs, and the suffix keeps each run's row uniquely
 * findable by name for the delete step.
 * #VERIFY: the DELETE at the end of the test removes the row it created, so
 * a normal (non-failing) run leaves no extra profile behind either way.
 *
 * #ASSUME: concurrency: "Ages 8-11" and "Reading level 4.5" are not unique
 * page-wide text: another profile (in this family or, if run concurrently,
 * one admin-management-real.spec.ts creates in the same "Dev Family") can
 * carry the same age band or cap and trip a Playwright strict-mode
 * violation on a bare page.getByText. Every such assertion below is scoped
 * to this test's own profile card (profiles__card, keyed on the timestamped
 * name) rather than searched page-wide.
 * #VERIFY: card-scoped locators stay correct even when this spec runs in
 * the same worker/time window as another real-backend spec touching the
 * same family.
 */

const DEV_GUARDIAN_BEARER = 'dev-guardian'

interface ProfileRow {
  id: string
  display_name: string
}

async function findProfileId(displayName: string): Promise<string> {
  const res = await fetch(`${BACKEND}/api/v1/profiles`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
  })
  expect(res.ok, `GET /profiles failed (HTTP ${res.status})`).toBe(true)
  const { profiles } = (await res.json()) as { profiles: ProfileRow[] }
  const row = profiles.find((p) => p.display_name === displayName)
  expect(row, `no profile named "${displayName}" found via GET /profiles`).toBeTruthy()
  return (row as ProfileRow).id
}

// Per-file reset so this file is order-independent in the shared-DB tier.
test.beforeAll(() => {
  resetRealState()
})

test.beforeEach(async () => {
  await requireBackend()
})

test('a guardian creates, edits, and deletes a child profile through the real console and API', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, DEV_GUARDIAN_BEARER)
  const name = `E2E CRUD Reader ${Date.now()}`

  await page.goto('/guardian/profiles')
  await page.getByRole('button', { name: 'Add child' }).click()
  await page.getByLabel(/Name/).fill(name)
  await page.getByLabel(/Age band/).selectOption('8-11')
  await page.getByRole('button', { name: 'Save' }).click()

  // Scoped to this test's own card (see file header #ASSUME: concurrency):
  // a bare page.getByText('Ages 8-11') can match another profile's card too.
  let card = page.locator('li.profiles__card', { hasText: name })
  await expect(card).toBeVisible()
  await expect(card.getByText('Ages 8-11')).toBeVisible()

  // Persisted, not optimistic: after reload the created profile is still there.
  await page.reload()
  card = page.locator('li.profiles__card', { hasText: name })
  await expect(card).toBeVisible()
  await expect(card.getByText('Ages 8-11')).toBeVisible()

  // Edit: tighten the reading-level cap through the real PATCH.
  await page.getByRole('button', { name: `Edit ${name}` }).click()
  await page.getByLabel(/Reading level cap/).fill('4.5')
  await page.getByRole('button', { name: 'Save' }).click()
  card = page.locator('li.profiles__card', { hasText: name })
  await expect(card.getByText('Reading level 4.5')).toBeVisible()

  await page.reload()
  card = page.locator('li.profiles__card', { hasText: name })
  await expect(card).toBeVisible()
  await expect(card.getByText('Reading level 4.5')).toBeVisible()

  // Delete: no UI control exists for this (see file header), so exercise the
  // real DELETE /v1/profiles/{id} directly, then reload the console to prove
  // the erasure (not just a client-side removal) actually landed server-side.
  const profileId = await findProfileId(name)
  const deleteRes = await fetch(`${BACKEND}/api/v1/profiles/${profileId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
  })
  expect(deleteRes.ok, `DELETE /profiles/${profileId} failed (HTTP ${deleteRes.status})`).toBe(true)

  await page.reload()
  await expect(page.getByText(name)).not.toBeVisible()
})
