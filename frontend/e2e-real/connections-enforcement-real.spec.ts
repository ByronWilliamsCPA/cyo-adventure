import { expect, test } from '@playwright/test'

import { BACKEND, requireBackend } from './real-stack'

/**
 * Real-API ADR-016 (register G17) family-connection ENFORCEMENT: not just
 * the guardian consent UI in isolation (guardian-connections.spec.ts already
 * covers that against a MOCKED backend), but whether an admin-created
 * connection plus dual-guardian consent actually changes what a DIFFERENT
 * family's guardian can see, against the real backend, end to end.
 *
 * #ASSUME (corrected from the task brief this spec was requested against):
 * "visibility" here is NOT a guardian-facing reading-history surface.
 * /guardian/reading (ReadingPage.tsx) is scoped entirely to the CALLING
 * guardian's own family ("We could not load your family's reading
 * activity") and is never gated by FamilyConnection at all --
 * api/family_connections.py and api/recommendations.py are the only two
 * backend modules that read that table. The real cross-family visibility
 * surface ADR-016 gates is the K17 RECOMMENDATION feed,
 * GET /api/v1/recommendations/{profile_id}
 * (src/cyo_adventure/api/recommendations.py), rendered on the KID's own
 * library page as a "Cousin <name> loved this" chip
 * (frontend/src/library/RecommendationChip.tsx). This spec proves that
 * mechanism end to end: first at the wire boundary through every gating
 * state, then once through the real rendered UI at full consent.
 *
 * Setup, entirely through the real API (zero route mocks anywhere here):
 * - A CATALOG-visible storybook, produced by approving the seeded in_review
 *   story `s_bridge_builder` ("The Bridge Builder", scripts/seed_dev_data.py
 *   `_REVIEW_STORY`) with `visibility: "catalog"` through the real approve
 *   endpoint. A catalog book is required because ring 2 needs BOTH families
 *   to be able to assign/see the SAME book (api/recommendations.py::
 *   _visible_books: same family OR catalog), and no seeded dev story is
 *   catalog-visible -- approving one is the only real HTTP path that sets it.
 *   Until 2026-09-05 this file generated a fresh book through the real RQ
 *   worker first and approved THAT; that stopped being possible when PRs
 *   #769/#776 made a mock-moderated book auto-reject to needs_revision with a
 *   permanently unapprovable report (see full-pipeline-real.spec.ts's header
 *   for the full account), which is why this spec 409ed on approve on every
 *   nightly since (issue #290). The seeded review story's report carries a
 *   genuinely independent reviewer, so it is the one real book on this stack
 *   an admin can approve. The `real-backend-setup` dependency (playwright
 *   .config.ts) reverts it to in_review / visibility=family before every
 *   invocation of this project (scripts/reset_e2e_real_state.py), so this
 *   approve is idempotent across runs and cannot collide with
 *   approval-flow.spec.ts, which approves the same story in the separate
 *   `real-backend` invocation. This file stays in the `real-backend-pipeline`
 *   project only because that is where it has always lived and its sibling
 *   there needs the worker; this spec itself no longer drives the worker.
 * - Two brand-new guardian families, JIT-provisioned via
 *   POST /api/v1/onboarding with fresh, never-seen bearer subjects
 *   (ENVIRONMENT=local trusts the bearer as the verified subject; see
 *   api/deps.py::require_onboarding_identity), then admin-approved from
 *   "awaiting_approval" to "active" (api/admin_users.py) so each can
 *   authenticate for everything else below. Neither is the seeded "Dev
 *   Family", so this file cannot collide with any other real-backend spec's
 *   fixture state.
 * - Each guardian creates one child profile and assigns the catalog book to
 *   it; the "sharer" guardian's profile then rates it 5 stars.
 *
 * The enforcement sequence: the viewer's recommendation feed is asserted
 * EMPTY at every gate that has not yet been cleared (no connection at all;
 * a connection with zero consent; a connection with only the viewer's OWN
 * consent) and populated only once BOTH guardians have actively consented --
 * proving dual consent is enforced, not merely connection existence. A
 * final revoke proves ADR-016's "revoking is unilateral and immediate"
 * against the real backend too.
 *
 * #CRITICAL: security: every step below is scoped through each family's OWN
 * guardian bearer (never dev-admin standing in for a guardian consent, and
 * never one family's bearer touching the other's resources); the admin
 * bearer is used ONLY for the two operations that are genuinely admin-only
 * (creating the connection row, approving the two new accounts), per
 * family_connections.py's "admin action never substitutes for consent"
 * (register A15).
 * #VERIFY: the recommendation feed is asserted `toEqual([])` (not merely
 * "missing the expected item") at every unconsented gate, so a regression
 * that leaked SOME ring-2 data early would fail this spec even if it did
 * not leak the exact expected item.
 */

test.describe.configure({ mode: 'serial' })

// dev-admin is used everywhere admin authority is genuinely required
// (approve, admin/family-connections, admin/users); the two JIT-provisioned
// guardians below drive everything family-scoped with their own bearers.
const ADMIN_BEARER = 'dev-admin'

// The seeded in_review story this spec approves to catalog visibility
// (scripts/seed_dev_data.py `_REVIEW_STORY` -> `s_bridge_builder`, title from
// its blob). scripts/reset_e2e_real_state.py pins both the id and the
// in_review/visibility=family baseline this spec starts from.
const SEEDED_REVIEW_STORY_ID = 's_bridge_builder'
const SEEDED_REVIEW_TITLE = 'The Bridge Builder'

async function apiFetch(path: string, bearer: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${BACKEND}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
    signal: AbortSignal.timeout(10_000),
  })
}

interface OnboardResult {
  bearer: string
  familyId: string
  userId: string
}

/** JIT-provisions a fresh guardian family (POST /onboarding), then admin-approves it to "active". */
async function provisionActiveGuardian(label: string): Promise<OnboardResult> {
  // #ASSUME: security: this bearer is trusted as the verified subject ONLY
  // because the real backend runs with ENVIRONMENT=local for this whole
  // real-backend e2e tier (see api/deps.py's dev/test auth seam); the random
  // suffix keeps two concurrent runs (or two calls in the same run) from
  // colliding on the unique authn_subject index.
  const bearer = `e2e-conn-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const onboardRes = await apiFetch('/api/v1/onboarding', bearer, { method: 'POST' })
  expect(onboardRes.ok, `POST /onboarding failed (HTTP ${onboardRes.status})`).toBe(true)
  const onboarded = (await onboardRes.json()) as {
    family_id: string
    user_id: string
    status: string
  }
  expect(onboarded.status).toBe('awaiting_approval')

  const approveRes = await apiFetch(`/api/v1/admin/users/${onboarded.user_id}`, ADMIN_BEARER, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'active' }),
  })
  expect(
    approveRes.ok,
    `PATCH /admin/users/${onboarded.user_id} failed (HTTP ${approveRes.status})`
  ).toBe(true)

  return { bearer, familyId: onboarded.family_id, userId: onboarded.user_id }
}

async function createProfile(bearer: string, displayName: string): Promise<string> {
  const res = await apiFetch('/api/v1/profiles', bearer, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName, age_band: '8-11' }),
  })
  expect(res.ok, `POST /profiles failed (HTTP ${res.status})`).toBe(true)
  const { id } = (await res.json()) as { id: string }
  return id
}

async function assignBook(bearer: string, storybookId: string, profileId: string): Promise<void> {
  const res = await apiFetch(`/api/v1/storybooks/${storybookId}/assignments`, bearer, {
    method: 'POST',
    body: JSON.stringify({ profile_ids: [profileId] }),
  })
  expect(res.ok, `POST /assignments failed (HTTP ${res.status}): ${await res.text()}`).toBe(true)
}

interface RecommendationItem {
  storybook_id: string
  title: string
  recommender_name: string
  rating: number
  ring: 'family' | 'connection'
}

async function fetchRecommendations(
  bearer: string,
  profileId: string
): Promise<RecommendationItem[]> {
  const res = await apiFetch(`/api/v1/recommendations/${profileId}`, bearer)
  expect(res.ok, `GET /recommendations/${profileId} failed (HTTP ${res.status})`).toBe(true)
  const body = (await res.json()) as { items: RecommendationItem[] }
  return body.items
}

interface FamilyConnectionMineItem {
  id: string
  active: boolean
  my_consent: boolean
}

test.beforeAll(async () => {
  await requireBackend()
})

let storybookId: string
let viewer: OnboardResult
let sharer: OnboardResult
let viewerProfileId: string
let sharerProfileId: string
const sharerDisplayName = `E2E Cousin ${Date.now()}`
let connectionId = ''

test('the seeded in-review storybook is approved to catalog visibility through the real API', async () => {
  // The reset dependency guarantees the baseline; assert it rather than
  // assume it, so a reset regression reads as its own failure here instead
  // of as a mysterious 409 on the approve below.
  const beforeRes = await apiFetch(
    `/api/v1/storybooks/${SEEDED_REVIEW_STORY_ID}/review`,
    ADMIN_BEARER
  )
  expect(beforeRes.ok, `GET /review failed (HTTP ${beforeRes.status})`).toBe(true)
  const before = (await beforeRes.json()) as { status: string; blob: { title?: string } }
  expect(before.status, 'reset_e2e_real_state.py should have left the seeded story in_review').toBe(
    'in_review'
  )
  expect(before.blob.title).toBe(SEEDED_REVIEW_TITLE)

  storybookId = SEEDED_REVIEW_STORY_ID
  const approveRes = await apiFetch(`/api/v1/storybooks/${storybookId}/approve`, ADMIN_BEARER, {
    method: 'POST',
    body: JSON.stringify({ visibility: 'catalog' }),
  })
  // Drain the body only on the error path (a Response stream is single-use).
  if (!approveRes.ok) {
    throw new Error(`POST /approve failed (HTTP ${approveRes.status}): ${await approveRes.text()}`)
  }
  const approved = (await approveRes.json()) as { visibility: string }
  expect(approved.visibility).toBe('catalog')
})

test('two brand-new families are provisioned, each with a profile assigned the catalog book', async () => {
  viewer = await provisionActiveGuardian('viewer')
  sharer = await provisionActiveGuardian('sharer')
  expect(viewer.familyId).not.toBe(sharer.familyId)

  viewerProfileId = await createProfile(viewer.bearer, `E2E Viewer Kid ${Date.now()}`)
  sharerProfileId = await createProfile(sharer.bearer, sharerDisplayName)

  await assignBook(viewer.bearer, storybookId, viewerProfileId)
  await assignBook(sharer.bearer, storybookId, sharerProfileId)

  const rateRes = await apiFetch('/api/v1/ratings', sharer.bearer, {
    method: 'POST',
    body: JSON.stringify({ profile_id: sharerProfileId, storybook_id: storybookId, value: 5 }),
  })
  expect(rateRes.ok, `POST /ratings failed (HTTP ${rateRes.status}): ${await rateRes.text()}`).toBe(
    true
  )
})

test('with no connection at all, the viewer sees nothing from the sharer family', async () => {
  const items = await fetchRecommendations(viewer.bearer, viewerProfileId)
  expect(items).toEqual([])
})

test('an admin-created connection alone, with zero consent, still shows nothing', async () => {
  const createRes = await apiFetch('/api/v1/admin/family-connections', ADMIN_BEARER, {
    method: 'POST',
    body: JSON.stringify({ family_id: viewer.familyId, connected_family_id: sharer.familyId }),
  })
  expect(
    createRes.ok,
    `POST /admin/family-connections failed (HTTP ${createRes.status}): ${await createRes.text()}`
  ).toBe(true)
  const created = (await createRes.json()) as { id: string }
  connectionId = created.id

  const items = await fetchRecommendations(viewer.bearer, viewerProfileId)
  expect(items).toEqual([])
})

test('only the viewer guardian consenting (the sharer has not) still shows nothing', async () => {
  const res = await apiFetch(`/api/v1/family-connections/${connectionId}/consent`, viewer.bearer, {
    method: 'POST',
  })
  expect(res.ok, `POST .../consent (viewer) failed (HTTP ${res.status})`).toBe(true)
  const updated = (await res.json()) as FamilyConnectionMineItem
  expect(updated.my_consent).toBe(true)
  expect(updated.active).toBe(false)

  const items = await fetchRecommendations(viewer.bearer, viewerProfileId)
  expect(items).toEqual([])
})

test('once BOTH guardians have consented, the viewer sees the real ring-2 recommendation', async () => {
  const res = await apiFetch(`/api/v1/family-connections/${connectionId}/consent`, sharer.bearer, {
    method: 'POST',
  })
  expect(res.ok, `POST .../consent (sharer) failed (HTTP ${res.status})`).toBe(true)
  const updated = (await res.json()) as FamilyConnectionMineItem
  expect(updated.active).toBe(true)

  const items = await fetchRecommendations(viewer.bearer, viewerProfileId)
  expect(items).toHaveLength(1)
  expect(items[0]).toMatchObject({
    storybook_id: storybookId,
    title: SEEDED_REVIEW_TITLE,
    recommender_name: sharerDisplayName,
    rating: 5,
    ring: 'connection',
  })
})

test('the real rendered kid library shows the "Cousin" recommendation chip once fully consented', async ({
  browser,
}) => {
  const context = await browser.newContext()
  let grantId = ''
  try {
    // A real child-session JWT for the viewer's own profile, minted by the
    // viewer's own guardian bearer (api/child_sessions.py: callable by a
    // guardian for a profile in its own family), plus a real device grant so
    // DeviceAuthorizedRoute (ADR-014) lets `/library/:profileId` load at all.
    const sessionRes = await apiFetch('/api/v1/child-sessions', viewer.bearer, {
      method: 'POST',
      body: JSON.stringify({ profile_id: viewerProfileId }),
    })
    expect(sessionRes.ok, `POST /child-sessions failed (HTTP ${sessionRes.status})`).toBe(true)
    const session = (await sessionRes.json()) as { token: string }

    const grantRes = await apiFetch('/api/v1/device-grants', viewer.bearer, {
      method: 'POST',
      body: JSON.stringify({ label: 'e2e-connections-enforcement' }),
    })
    expect(grantRes.ok, `POST /device-grants failed (HTTP ${grantRes.status})`).toBe(true)
    const grant = (await grantRes.json()) as {
      token: string
      expires_at: string
      family_id: string
      id: string
    }
    grantId = grant.id
    const deviceGrantValue = JSON.stringify({
      token: grant.token,
      expiresAt: grant.expires_at,
      familyId: grant.family_id,
      id: grant.id,
    })

    await context.addInitScript(
      ([grantKey, grantValue, authKey, tokenValue]) => {
        window.localStorage.setItem(grantKey, grantValue)
        window.localStorage.setItem(authKey, tokenValue)
      },
      ['device_grant', deviceGrantValue, 'auth_token', session.token] as const
    )

    const page = await context.newPage()
    await page.goto(`/library/${viewerProfileId}`)
    await expect(page.getByText(`Cousin ${sharerDisplayName} loved this`)).toBeVisible()
  } finally {
    if (grantId) {
      // Best-effort, but never silent: a device grant that fails to revoke is a
      // live credential left behind, so it must be visible in the run log rather
      // than swallowed (mirrors the connection-delete warn in test.afterAll).
      try {
        const res = await apiFetch(`/api/v1/device-grants/${grantId}`, viewer.bearer, {
          method: 'DELETE',
        })
        if (!res.ok && res.status !== 404) {
          console.warn(
            `[connections-enforcement] device-grant revoke did not confirm (HTTP ${res.status}) for ${grantId}`
          )
        }
      } catch (err) {
        console.warn(
          `[connections-enforcement] device-grant revoke errored for ${grantId}: ${err instanceof Error ? err.message : String(err)}`
        )
      }
    }
    await context.close()
  }
})

test('revoking the sharer side is immediate: the recommendation disappears on the very next fetch', async () => {
  const res = await apiFetch(`/api/v1/family-connections/${connectionId}/consent`, sharer.bearer, {
    method: 'DELETE',
  })
  expect(res.ok, `DELETE .../consent (sharer) failed (HTTP ${res.status})`).toBe(true)
  const updated = (await res.json()) as FamilyConnectionMineItem
  expect(updated.active).toBe(false)

  const items = await fetchRecommendations(viewer.bearer, viewerProfileId)
  expect(items).toEqual([])
})

test.afterAll(async () => {
  // Best-effort: an admin hard-delete of the connection row, so a reused dev
  // stack does not accumulate one connection per run. Never throws (mirrors
  // real-stack.ts's revokeDevice); the two provisioned families and their
  // profiles are left in place, exactly as other real-backend specs leave
  // their minted fixtures (a disposable local dev stack, not identity data
  // worth cleaning up here).
  if (!connectionId) return
  try {
    const res = await apiFetch(`/api/v1/admin/family-connections/${connectionId}`, ADMIN_BEARER, {
      method: 'DELETE',
    })
    if (!res.ok && res.status !== 404) {
      console.warn(
        `[connections-enforcement] connection delete did not confirm (HTTP ${res.status}) for ${connectionId}`
      )
    }
  } catch (err) {
    console.warn(
      `[connections-enforcement] connection delete errored for ${connectionId}: ${err instanceof Error ? err.message : String(err)}`
    )
  }
})
