import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { unlockParentalGateIfPresent } from './support/auth'
import { stagingStorageStatePath } from './support/auth-storage'
import {
  createDeviceGrantMintState,
  readPersistedGrantId,
  revokeDeviceGrantBackstop,
} from './support/device-grant'
import { removeDeviceFromConsole } from '../e2e-support/device-grant-ui'
import { gotoResilient, paceNavigation } from '../e2e-support/rate-limit'

/**
 * The staging e2e half of the moderation QA corpus containment contract
 * (docs/planning/safety/moderation-review-redesign-2026-07-28.md section 5):
 * no mqa_ book is ever kid-visible. The seed script, the read gate, and the
 * publishing guard each enforce this structurally; this spec is the #VERIFY
 * that observes the deployed composition of all of them from a real kid
 * session.
 *
 * Two halves, and the order matters:
 *
 * 1. Presence (admin): the corpus books actually exist on staging. Without
 *    this anchor the invisibility assertion below would go silently green
 *    the day a staging database reset wiped the seeded rows, which is the
 *    exact failure mode a safety regression test must not have. A failure
 *    here means "re-run scripts/seed_moderation_qa.py", not a product bug.
 * 2. Invisibility (guardian -> kid): a real device grant opens the seeded
 *    "Test Reader" library and the spec asserts, at both the API and the
 *    rendered-DOM level, that nothing mqa_-prefixed reached the kid surface.
 *
 * Write pattern: this is the tier's second grant-writing spec, deliberately
 * identical to kid-library-smoke.spec.ts's fully-reversible one (exactly one
 * grant, revoked by the final test, backstopped in afterAll). It is safe to
 * run unattended on the daily cron: the only rows it touches are the seeded
 * test guardian's own device grant.
 *
 * Both `beforeAll` hooks below restore a pre-authenticated session
 * (`stagingStorageStatePath`) rather than signing in through the login form;
 * the tier's sign-ins now happen once each, up front, in
 * `e2e-staging/auth.setup.ts`.
 */
const DEVICE_GRANT_KEY = 'device_grant'
const TEST_KID_NAME = 'Test Reader'
const MQA_PREFIX = 'mqa_'

/**
 * The corpus ground truth, mirrored from
 * docs/planning/safety/moderation-qa-corpus.json (v1.0) and
 * tests/fixtures/moderation_qa/books/. Kept literal here rather than read
 * from the repo at runtime so a manifest edit that forgets staging shows up
 * as a presence failure instead of silently shrinking this spec's coverage.
 */
const MQA_BOOK_IDS = [
  'mqa_block_selfharm_reference',
  'mqa_borderline_grief_yearning',
  'mqa_borderline_storm_watch_13_16',
  'mqa_borderline_storm_watch_5_8',
  'mqa_clean_meadow_market',
  'mqa_clean_orchard_riddle',
] as const

// Deduplicated (the two Storm Watch books share a title). Exact-matched
// against the rendered library, so a legitimate book whose title merely
// contains one of these strings cannot false-positive.
const MQA_TITLES = [
  'The Heavy Feeling',
  'The Rosemary Bread House',
  'Storm Watch',
  'Market Day in Meadow Square',
  "The Orchard's Riddle Tree",
] as const

test.describe('moderation QA corpus is present on staging (admin view)', () => {
  let adminPage: Page

  test.beforeAll(async ({ browser }) => {
    adminPage = await browser.newPage({ storageState: stagingStorageStatePath('admin') })
  })

  test.afterAll(async () => {
    await adminPage.close()
  })

  test('the admin master library lists every seeded mqa book', async () => {
    // #ASSUME: external-resources: the corpus was seeded by an owner-run
    // ENVIRONMENT=staging scripts/seed_moderation_qa.py; staging fixtures are
    // disposable, so a database reset legitimately empties this.
    // #VERIFY: on failure, re-run the seed script (idempotent), then re-run
    // this tier. Do NOT weaken this to "at least one mqa book": partial
    // presence means a partial seed, and the invisibility half below would
    // then be asserting over an incomplete corpus.
    const result = await adminPage.evaluate(async () => {
      const token = window.localStorage.getItem('auth_token')
      if (!token) {
        return { status: 0, items: [] as Array<{ storybook_id: string; status: string }> }
      }
      const res = await fetch('/api/v1/admin/storybooks', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        return { status: res.status, items: [] }
      }
      const body = (await res.json()) as {
        items: Array<{ storybook_id: string; status: string }>
      }
      return { status: res.status, items: body.items }
    })

    expect(
      result.status,
      'GET /api/v1/admin/storybooks should succeed for the seeded staging admin'
    ).toBe(200)

    const mqaById = new Map(
      result.items
        .filter((item) => item.storybook_id.startsWith(MQA_PREFIX))
        .map((item) => [item.storybook_id, item.status])
    )
    for (const id of MQA_BOOK_IDS) {
      expect(
        mqaById.has(id),
        `${id} is missing from staging; re-run scripts/seed_moderation_qa.py ` +
          `(found mqa books: ${[...mqaById.keys()].sort().join(', ') || 'none'})`
      ).toBe(true)

      // #CRITICAL: security: the single-layer-sensitive half of this spec. The
      // invisibility assertions below are guarded by five conjunctive
      // conditions in list_library (family/catalog visibility, published
      // status, a current published version, an approval, and an EXISTS on
      // StorybookAssignment), and the QA family holds no ChildProfile for an
      // assignment to target, so they cannot go red until several layers fail
      // at once. This one goes red the moment the publishing guard alone slips,
      // which is the regression most likely to actually happen.
      // #VERIFY: asserted as "not published" rather than "is draft" on purpose.
      // seed_moderation_qa.py inserts at status="draft", but the corpus exists
      // to be run through moderation, so a legitimate sweep may move a book to
      // another non-published state; pinning to "draft" would fail on correct
      // behaviour. "published" is the only status that breaks containment.
      expect(
        mqaById.get(id),
        `${id} is ${String(mqaById.get(id))} on staging; a moderation QA book ` +
          `must never reach "published", which is the one status that makes it ` +
          `eligible for the kid library. Check the publishing guard.`
      ).not.toBe('published')
    }
  })
})

test.describe('mqa books are invisible to a kid profile on staging', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  /**
   * Captured at mint time, not re-read at teardown: a device-grant 401 makes
   * useApi.ts clear the localStorage record, so the backstop's only input
   * would be gone in exactly the runs where the backstop is the only cleanup
   * left. The `mintAttempted` half is what makes an uncaptured id still
   * reportable. See support/device-grant.ts.
   */
  const grantState = createDeviceGrantMintState()

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage({ storageState: stagingStorageStatePath('guardian') })
  })

  test.afterAll(async () => {
    // Same best-effort DELETE backstop as kid-library-smoke.spec.ts, for the
    // same reason: if the explicit revoke test below never ran, do not leave
    // a live grant on shared staging.
    await revokeDeviceGrantBackstop(sharedPage, grantState, '[moderation-qa-invisibility]')
    await sharedPage.close()
  })

  test('the guardian authorizes this device for kid access', async () => {
    await gotoResilient(sharedPage, '/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

    const setUp = sharedPage.getByRole('button', { name: 'Set up this device for your kids' })
    const reauthorize = sharedPage.getByRole('button', { name: 'Re-authorize this device' })

    // Armed BEFORE the click, for the same reason as kid-library-smoke.spec.ts:
    // the POST can mint server-side and still leave this test with no id, and
    // teardown must report that as a leak rather than as nothing to do.
    grantState.mintAttempted = true
    if (await setUp.isVisible().catch(() => false)) {
      await setUp.click()
    } else {
      await reauthorize.click()
    }

    await expect(sharedPage.getByRole('button', { name: 'Hand device to a child' })).toBeVisible()
    grantState.grantId = await readPersistedGrantId(sharedPage)
    expect(
      grantState.grantId,
      'a device grant carrying an id should be persisted after authorize; the ' +
        'afterAll backstop has no other way to revoke it if a later test fails'
    ).not.toBeNull()
  })

  test('the kid library response and render contain no mqa book', async () => {
    await gotoResilient(sharedPage, '/kids')
    await expect(
      sharedPage.getByRole('heading', { name: "Who's reading?", level: 1 })
    ).toBeVisible()

    // Paced by hand for the same reason as kid-library-smoke.spec.ts: the
    // in-app route change below fans out into the library list and
    // recommendations fetches, spending request budget like a navigation.
    await paceNavigation(sharedPage)

    // Arm the capture BEFORE the click: the library list request fires during
    // the route change. The `?` keeps this from matching the versioned
    // /api/v1/library/{...} blob route.
    // Audited in the #290 sweep and found safe: the profile-picker link click
    // is the only action here that requests the kid library, and the
    // route-change fan-out this file paces around (recommendations, etc.)
    // does not hit /api/v1/library itself, so there is no second in-flight
    // GET of the same shape for queue position to disambiguate.
    const libraryResponse = sharedPage.waitForResponse(
      (res) => res.url().includes('/api/v1/library?') && res.request().method() === 'GET'
    )
    await sharedPage.getByRole('link', { name: TEST_KID_NAME }).click()
    await expect(sharedPage).toHaveURL(/\/library\//)

    const response = await libraryResponse
    // A 429 here would make the JSON assertion below fail confusingly; name
    // the real cause instead. paceNavigation above is what prevents this.
    expect(
      response.status(),
      'library list should not be rate-limited or erroring; see e2e-support/rate-limit.ts'
    ).toBe(200)

    // #CRITICAL: security: this is the contract under test. The kid library
    // API response is the exact payload every kid surface renders from, so an
    // mqa_ id here means the containment layers (draft status, no approval,
    // profile-less QA family, assignment gate) have ALL failed at once.
    // #VERIFY: this assertion plus the rendered-DOM sweep below; the
    // presence describe above keeps both non-vacuous.
    const body = (await response.json()) as { stories: Array<{ id: string; title: string }> }
    const leaked = body.stories.filter((story) => story.id.startsWith(MQA_PREFIX))
    expect(
      leaked,
      `moderation QA books leaked into a kid library: ${leaked
        .map((story) => `${story.id} ("${story.title}")`)
        .join(', ')}`
    ).toEqual([])

    // DOM-level sweep on top of the API check: covers whatever the render
    // path shows (including recommendation rails fed by other requests),
    // not just the one captured response.
    await expect(
      sharedPage.getByRole('heading', { name: 'My Books' }),
      'the kid library should have rendered; without it the title sweep below ' +
        'would pass against an unrendered page rather than against a real library'
    ).toBeVisible()
    for (const title of MQA_TITLES) {
      await expect(
        sharedPage.getByText(title, { exact: true }),
        `the moderation QA title "${title}" is rendered on a kid library page. ` +
          'The API assertion above passed, so this reached the DOM by some ' +
          'other path (a recommendation rail, an offline cache, or a ' +
          'prefetch), not through GET /api/v1/library.'
      ).toHaveCount(0)
    }
  })

  test('the guardian revokes the device authorization', async () => {
    await gotoResilient(sharedPage, '/guardian')
    await unlockParentalGateIfPresent(sharedPage, 'guardian')

    await removeDeviceFromConsole(sharedPage)
    const stored = await sharedPage.evaluate(
      (key) => window.localStorage.getItem(key),
      DEVICE_GRANT_KEY
    )
    expect(stored, 'the device grant should be cleared after remove').toBeNull()
    // Revoked explicitly, so the backstop has nothing left to do: clear both
    // halves, or the uncaptured-mint branch would report a phantom leak.
    grantState.grantId = null
    grantState.mintAttempted = false
  })
})
