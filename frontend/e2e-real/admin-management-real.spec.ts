import { expect, test, type Page } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { BACKEND, requireBackend, resetRealState } from './real-stack'

// Bearers mirror scripts/seed_dev_data.py's authn subjects; in
// ENVIRONMENT=local the backend trusts the bearer string directly as the
// principal (see real-stack.ts / contract-smoke-real.spec.ts). dev-admin is
// an admin (is_admin=True) in "Dev Family"; dev-guardian is a plain guardian
// (is_admin=False) in that same family.
const ADMIN_BEARER = 'dev-admin' // scripts/seed_dev_data.py _ADMIN_SUBJECT
const GUARDIAN_BEARER = 'dev-guardian' // scripts/seed_dev_data.py _GUARDIAN_SUBJECT

// Node-side authenticated GET, mirroring contract-smoke-real.spec.ts::apiGet.
// Used to exercise the raw wire boundary (server status codes, audit surface)
// directly, without the SPA's client-side route gate in the way.
async function apiGet(bearer: string, path: string): Promise<Response> {
  return fetch(`${BACKEND}${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
    signal: AbortSignal.timeout(5000),
  })
}

/**
 * Real-API WS-J admin user-management (Phase 3.1 write-path backfill): the
 * Kids tab's real create/edit/deactivate round-trip through
 * /api/v1/admin/profiles, no route mocks (unlike admin-user-management.spec.ts
 * in the mocked tier, which covers the Users tab). Kids was chosen over the
 * other three tabs as the highest-value real write within WS-J's scope: it
 * is the one console-only path (there is no guardian-facing equivalent for
 * creating a profile in a family other than your own) and its deactivate
 * toggle gates whether a profile can still mint a reading session at all
 * (api/child_sessions.py), so a stale client-only "success" would mask a
 * real safety-relevant regression. Kept to this one tab per the work order's
 * "keep it focused" guidance; Users/Families/Connections are not covered
 * here.
 *
 * The tab state (`UserManagementPage`'s `useState<TabKey>`) is
 * component-local, not URL-derived, so a full page reload always lands back
 * on the "Users" tab; every persistence check below re-clicks "Kids" after
 * navigating.
 *
 * #ASSUME: data-integrity: a timestamp-suffixed display name keeps the
 * create idempotent across the two consecutive runs the validation step
 * requires, the same rationale as guardian-profile-crud-real.spec.ts.
 * #VERIFY: the profile this test creates is left deactivated, not deleted
 * (admin/profiles.py has no delete route), so a reused dev stack accumulates
 * one harmless deactivated row per run rather than a stale active one.
 */

// Per-file reset so this file is order-independent in the shared-DB tier.
test.beforeAll(() => {
  resetRealState()
})

test.beforeEach(async () => {
  await requireBackend()
})

async function openKidsTab(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Kids' }).click()
}

test('an admin creates, edits, and deactivates a real kid profile in another family, all persisting across reload', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-admin')
  const originalName = `E2E Admin Kid ${Date.now()}`
  const editedName = `${originalName} Edited`

  await page.goto('/admin/users')
  await expect(page.getByRole('heading', { name: 'User management' })).toBeVisible()
  await openKidsTab(page)

  await page.getByLabel('Family').selectOption({ label: 'Dev Family' })
  await page.getByLabel('Name').fill(originalName)
  await page.getByLabel('Age band').selectOption('8-11')
  await page.getByRole('button', { name: 'Create profile' }).click()

  let row = page.locator('tbody tr', { hasText: originalName })
  await expect(row).toBeVisible()
  await expect(row.getByText('Dev Family')).toBeVisible()
  await expect(row.getByText('active', { exact: true })).toBeVisible()

  // Persisted, not optimistic: after reload (and re-selecting the tab) the
  // real POST's row is still there.
  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: originalName })
  await expect(row).toBeVisible()

  // Edit: rename the profile and change its age band through the real PATCH.
  // Once in edit mode the Name cell is an <input>, not text, so `row`'s
  // hasText-based locator can no longer find it (an input's value is not
  // part of its element's text content); the aria-labels below are unique
  // page-wide (built from the timestamped originalName), so address them
  // directly instead of re-scoping through `row`.
  await row.getByRole('button', { name: 'Edit' }).click()
  await page.getByLabel(`Name for ${originalName}`).fill(editedName)
  await page.getByLabel(`Age band for ${originalName}`).selectOption('13-16')
  await page.getByRole('button', { name: 'Save' }).click()

  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row).toBeVisible()
  await expect(row.getByText('13-16', { exact: true })).toBeVisible()

  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row).toBeVisible()
  await expect(row.getByText('13-16', { exact: true })).toBeVisible()

  // Deactivate: toggles the same real status field the child-session mint
  // gate reads (api/child_sessions.py).
  await row.getByRole('button', { name: 'Deactivate' }).click()
  await expect(row.getByText('deactivated', { exact: true })).toBeVisible()

  await page.reload()
  await openKidsTab(page)
  row = page.locator('tbody tr', { hasText: editedName })
  await expect(row.getByText('deactivated', { exact: true })).toBeVisible()
})

test('a plain guardian visiting the admin user-management console is sent back to the guardian console', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/guardian$/)
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
})

/**
 * SAFETY: admin cross-family PII boundary (#12). An admin manages users and
 * profiles across every family, so the JSON the console receives crosses a
 * tenant boundary that no other GET in the API does. The three tests below
 * assert the WIRE boundary the backend enforces (admin_profiles.py /
 * admin_users.py / audit.py), not merely the client-side SPA redirect the
 * rest of this file and the mocked tier cover.
 */

// #12a: the real cross-family profile JSON returned to the admin must omit the
// two sensitive fields the serializer deliberately drops. admin_profiles.py::
// _view exposes only the derived has_pin bool in pin_hash's place, and never
// serializes authn_subject at all (that field is not even on ChildProfile).
test('#12a admin cross-family profile JSON carries no pin_hash and no authn_subject', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context, ADMIN_BEARER)

  // #ASSUME: timing dependencies: register the response wait BEFORE navigating
  // so UserManagementPage's mount-time load (loadAll -> listProfiles ->
  // GET /api/v1/admin/profiles, unfiltered = all families) cannot resolve
  // before the listener is attached.
  // #VERIFY: waitForResponse is created before page.goto below.
  const profilesResponse = page.waitForResponse(
    (res) =>
      res.url().includes('/api/v1/admin/profiles') &&
      res.request().method() === 'GET' &&
      res.status() === 200,
    { timeout: 10_000 }
  )

  await page.goto('/admin/users')
  const res = await profilesResponse
  const body = (await res.json()) as { profiles: Record<string, unknown>[] }

  // Guard against a vacuous pass: the seeded "Unrelated Reader" lives in
  // "Unrelated Family" (scripts/seed_dev_data.py::_seed_unrelated_family), a
  // family dev-admin does NOT belong to, so its presence proves the admin
  // really received cross-family profile JSON, not just its own family's rows.
  expect(body.profiles.length, 'admin cross-family profile list is empty').toBeGreaterThan(0)
  const crossFamily = body.profiles.find((p) => p.display_name === 'Unrelated Reader')
  expect(
    crossFamily,
    'seeded cross-family "Unrelated Reader" profile missing from the admin list'
  ).toBeDefined()

  for (const profile of body.profiles) {
    const label = String(profile.display_name)
    // pin_hash is write-only credential material; it must never cross the wire.
    expect('pin_hash' in profile, `pin_hash leaked for profile "${label}"`).toBe(false)
    // authn_subject is bearer-adjacent identity material with no console use.
    expect('authn_subject' in profile, `authn_subject leaked for profile "${label}"`).toBe(false)
    // The safe substitute the serializer exposes in pin_hash's place.
    expect(typeof profile.has_pin, `has_pin (derived flag) missing for "${label}"`).toBe('boolean')
  }
})

// #12b: the SERVER-SIDE 403, not the SPA redirect. A plain guardian bearer
// hitting the admin endpoints directly must be refused by _require_admin, so
// the cross-family PII stays protected even if the client-side route gate is
// bypassed (a direct API call, a stale token, a non-browser client).
test('#12b a plain guardian is refused GET /admin/profiles and /admin/users with a server 403', async () => {
  const profiles = await apiGet(GUARDIAN_BEARER, '/api/v1/admin/profiles')
  expect(profiles.status, 'guardian must be refused admin profiles with 403').toBe(403)

  const users = await apiGet(GUARDIAN_BEARER, '/api/v1/admin/users')
  expect(users.status, 'guardian must be refused admin users with 403').toBe(403)

  // Positive control: the same endpoints answer 200 for an admin bearer, so
  // the 403s above are an authorization decision, not a broken/absent route.
  const adminProfiles = await apiGet(ADMIN_BEARER, '/api/v1/admin/profiles')
  expect(adminProfiles.status, 'admin must be allowed admin profiles (positive control)').toBe(200)
})

// #12c: the Article-30 compensating control. list_admin_profiles records one
// PROFILE_VIEWED event per cross-family read (admin_profiles.py ~119-134);
// observe it through the admin audit surface (api/audit.py, register A13) that
// the admin console exposes. This is a real, frontend-tier-observable control,
// so it is asserted rather than skipped. The deeper invariants (exactly one
// event per call, never one per row, actor identity) are pinned by
// tests/integration/test_admin_profiles_api.py.
test('#12c listing cross-family profiles emits a PROFILE_VIEWED audit event', async () => {
  // #ASSUME: timing dependencies: a small back-buffer on `since` absorbs any
  // clock skew between the test runner and the DB's occurred_at, so the event
  // this list emits is not missed by the >= since filter (audit.py::
  // _parse_timestamp). Both run on the same local host, so 5s is ample.
  // #VERIFY: the list call below happens strictly after `since`.
  const since = new Date(Date.now() - 5_000).toISOString()

  const list = await apiGet(ADMIN_BEARER, '/api/v1/admin/profiles')
  expect(list.status, 'admin profiles list failed to set up the audit assertion').toBe(200)

  const audit = await apiGet(
    ADMIN_BEARER,
    `/api/v1/admin/audit?kind=profile_viewed&since=${encodeURIComponent(since)}`
  )
  expect(audit.status, 'admin audit query failed').toBe(200)
  const body = (await audit.json()) as {
    events: { event_type: string; entity_type: string; payload: Record<string, unknown> }[]
  }
  const viewed = body.events.find((event) => event.event_type === 'profile_viewed')
  expect(viewed, 'no PROFILE_VIEWED event recorded for the cross-family list').toBeDefined()
  expect(viewed!.entity_type, 'PROFILE_VIEWED entity_type').toBe('child_profile')
  // The payload carries the row count, never per-row PII (admin_profiles.py:
  // "one event per call, never one per row").
  expect('count' in viewed!.payload, 'PROFILE_VIEWED payload should carry a count').toBe(true)
})
