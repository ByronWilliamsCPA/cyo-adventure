import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import {
  authorizeDevice,
  BACKEND,
  requireBackend,
  resetRealState,
  revokeDevice,
} from './real-stack'

/**
 * Real-API K15 kid flag path: the reader's "Tell a grown-up" affordance
 * (FlagButton.tsx) POSTs a real, structured flag to `POST /api/v1/flags`
 * (api/flags.py::create_flag), no free text, exactly the closed three-reason
 * contract the backend enforces. No route mocks, every /api call hits
 * uvicorn through the preview proxy, authorized as the seeded dev-child
 * subject (ENVIRONMENT=local trusts the bearer token).
 *
 * #EDGE: data-integrity: "The Tide Pool Mystery" (s_tide_pools) is also read
 * by kid-reads.spec.ts and kid-go-back-real.spec.ts. This spec never clicks
 * a choice (submitting a flag does not touch reading_state), so it never
 * changes the row's position for whichever spec reads this story next; see
 * kid-go-back-real.spec.ts's file header for the fuller shared-story note.
 *
 * The flag this test creates is resolved via the real admin
 * `POST /api/v1/admin/flags/{id}/resolve` in a best-effort afterEach: flags.py's
 * MAX_OPEN_FLAGS_PER_PROFILE caps a profile at 5 open flags, and this cleanup
 * (mirroring revokeDevice's per-test cleanup convention) keeps a repeatedly
 * run dev stack from ever exhausting it and turning this spec's own 201 into
 * a 409.
 */

const DEV_ADMIN_BEARER = 'dev-admin'

let deviceGrant: DeviceGrant | null = null
let createdFlagId: string | null = null

// Per-file reset so this file's own flag lands against the seed family's
// clean kid_flag baseline (MAX_OPEN_FLAGS_PER_PROFILE headroom), regardless
// of what ran earlier in the same full-suite invocation.
test.beforeAll(() => {
  resetRealState()
})

test.beforeEach(async ({ context }) => {
  await requireBackend()
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test.afterEach(async () => {
  // Resolve the flag this test created so MAX_OPEN_FLAGS_PER_PROFILE
  // (flags.py) never accumulates across runs; best-effort, never fails the
  // test, mirroring revokeDevice below.
  // #EDGE: external-resource: the backend may be stopped, or the flag already
  // resolved/gone, by the time this runs; both are swallowed with a warning.
  // #VERIFY: a leaked open flag is visible via GET /admin/flags, not silent:
  // the cap (5) would surface as a real 409 on a later run of this spec.
  if (createdFlagId) {
    try {
      const res = await fetch(`${BACKEND}/api/v1/admin/flags/${createdFlagId}/resolve`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${DEV_ADMIN_BEARER}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ resolution: 'dismissed' }),
        signal: AbortSignal.timeout(5000),
      })
      if (!res.ok) {
        console.warn(
          `[kid-flag-real] flag resolve did not confirm (HTTP ${res.status}) ` +
            `for flag ${createdFlagId}`
        )
      }
    } catch (err) {
      console.warn(
        `[kid-flag-real] flag resolve errored for flag ${createdFlagId}: ` +
          `${err instanceof Error ? err.message : String(err)}`
      )
    }
    createdFlagId = null
  }
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('a kid tells a grown-up through the real flag path and it lands in the admin queue', async ({
  page,
}) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  await page.getByRole('button', { name: 'Tell a grown-up' }).click()
  await expect(page.getByText('What happened?')).toBeVisible()

  // #ASSUME: timing dependencies: registering waitForResponse before the
  // click (not after) so the real POST /v1/flags is caught as it happens,
  // matching naive-kid-misuse-real.spec.ts's wait-then-act ordering.
  // #VERIFY: the response body asserted below is the exact 201 the click
  // below triggers, not a later unrelated request.
  const flagResponsePromise = page.waitForResponse(
    (res) => res.url().includes('/api/v1/flags') && res.request().method() === 'POST',
    { timeout: 5_000 }
  )
  await page.getByRole('button', { name: 'It scared me' }).click()
  const flagResponse = await flagResponsePromise
  expect(flagResponse.status()).toBe(201)
  const created = (await flagResponse.json()) as { id: string; reason: string }
  expect(created.reason).toBe('scared_me')
  createdFlagId = created.id

  await expect(page.getByText('Thanks for telling us. A grown-up will take a look.')).toBeVisible()

  // Re-fetch via the real admin queue, not just the POST's own response body,
  // to confirm the flag actually persisted server-side: open, and carrying
  // this exact reason.
  const adminRes = await fetch(`${BACKEND}/api/v1/admin/flags`, {
    headers: { Authorization: `Bearer ${DEV_ADMIN_BEARER}` },
    signal: AbortSignal.timeout(5000),
  })
  expect(adminRes.ok, `GET /admin/flags failed (HTTP ${adminRes.status})`).toBe(true)
  const { flags } = (await adminRes.json()) as {
    flags: Array<{ id: string; reason: string; resolved_at: string | null }>
  }
  const persisted = flags.find((f) => f.id === created.id)
  expect(persisted, `flag ${created.id} not found in the real admin queue`).toBeTruthy()
  expect(persisted?.reason).toBe('scared_me')
  expect(persisted?.resolved_at).toBeNull()
})
