import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { signInAsProdTestAdmin, unlockParentalGateIfPresent } from './support/auth'
import { gotoResilient } from '../e2e-support/rate-limit'

/**
 * R1 live checklist Sections 3 (guardian books/assign) and 6 (cross-family
 * isolation) against LIVE production, sharing one authenticated page and one
 * login (serial, matching guardian-admin-smoke.spec.ts's pattern). Read-only:
 * the assign dialog is opened to inspect its redacted content-review tags,
 * never confirmed; nothing is assigned, unassigned, approved, or declined.
 *
 * Every /v1/api response body fetched anywhere in this suite is captured (see
 * capturedResponses below) so the redaction test can scan real production
 * payloads rather than a single hand-picked endpoint. This is the automatable
 * half of the guardian-facing redaction contract in
 * src/cyo_adventure/api/review_surface.py::build_content_summary: a guardian
 * must never receive `flagged_passages` (admin-only, each item carries raw
 * node `prose`) or a bare `prose` key at any depth.
 *
 * #CRITICAL: security: the two forbidden keys below (`flagged_passages`,
 * `prose`) are the exact admin-only fields build_content_summary redacts out
 * of ContentSummaryView (see review_surface.py's module docstring and
 * `_content_summary_findings`). If either ever appears in a guardian-facing
 * response body, a child's story content or generation internals are
 * leaking to an account that must never see them.
 * #VERIFY: findForbiddenKeys below; keep it in sync if the admin-only field
 * names in api/schemas.py's FlaggedPassage/ReviewSurfaceView ever change.
 */

/** Admin-only keys that must never appear in a guardian-facing response body. */
const FORBIDDEN_KEYS = ['flagged_passages', 'prose'] as const

/**
 * Recursively scans a parsed JSON value for any of FORBIDDEN_KEYS at any
 * depth, returning a dotted/indexed path to each hit for an actionable
 * failure message (e.g. `books[2].flagged_passages` or `summary.prose`).
 */
function findForbiddenKeys(value: unknown, path = '$'): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => findForbiddenKeys(item, `${path}[${i}]`))
  }
  if (value !== null && typeof value === 'object') {
    const hits: string[] = []
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const childPath = `${path}.${key}`
      if ((FORBIDDEN_KEYS as readonly string[]).includes(key)) {
        hits.push(childPath)
      }
      hits.push(...findForbiddenKeys(child, childPath))
    }
    return hits
  }
  return []
}

test.describe('guardian books, assignment, and cross-family isolation', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page
  // Every /api/v1 JSON response body observed anywhere in this suite,
  // installed BEFORE sign-in so the /v1/me call and everything after it is
  // covered too.
  const capturedResponses: { url: string; body: unknown }[] = []

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
    sharedPage.on('response', (response) => {
      const url = response.url()
      if (!url.includes('/api/v1/')) return
      const contentType = response.headers()['content-type'] ?? ''
      if (!contentType.includes('application/json')) return
      // #ASSUME: timing dependency: response bodies are read asynchronously
      // off the synchronous 'response' event; a body that fails to parse (a
      // truncated stream, an already-consumed body) is dropped rather than
      // failing the run, since this collector is a passive observer, not
      // something any test awaits directly.
      // #VERIFY: the positive-control assertion in the redaction test below
      // (capturedResponses.length > 0) is what would catch a collector that
      // silently captured nothing.
      void response
        .json()
        .then((body: unknown) => {
          capturedResponses.push({ url, body })
        })
        .catch(() => {
          /* non-JSON or unreadable body; nothing to scan */
        })
    })
    await signInAsProdTestAdmin(sharedPage)
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  test("the books page lists the family's assigned books with a content-review badge each", async () => {
    await gotoResilient(sharedPage, '/guardian/books')
    await unlockParentalGateIfPresent(sharedPage)
    // Positive control: a failed render (error boundary, ErrorBanner, or a
    // stuck loading state) also shows zero rows, so the heading must be
    // visible before the row count below means anything.
    await expect(sharedPage.getByRole('heading', { name: 'Books', level: 1 })).toBeVisible()
    // The E2E Test Family (84b96700) has 5 storybook assignments, so this
    // page is never legitimately empty; a zero count here is a real
    // regression, not live-data noise.
    const rows = sharedPage.locator('.books__list > li')
    await expect(rows).not.toHaveCount(0)
    // Every row renders exactly one ContentBadge (BooksPage.tsx: screened/
    // flagged/clean/unscreened, class `flag-badge`); assert the first row's
    // badge without pinning to a specific tone, which live moderation data
    // could change at any time.
    await expect(rows.first().locator('.flag-badge')).toBeVisible()
  })

  test('opening the assign dialog surfaces only redacted content-review tags', async () => {
    await sharedPage
      .getByRole('button', { name: /^Assign / })
      .first()
      .click()
    const dialog = sharedPage.getByRole('dialog', { name: 'Assign to children' })
    await expect(dialog).toBeVisible()

    // AssignChildrenDialog.tsx fires the content-summary fetch on mount as a
    // second, best-effort request that can degrade to an "unavailable"
    // notice without blocking assignment; accept either outcome here so a
    // transient content-summary failure does not make this test flaky on the
    // daily cron. The actual redaction guarantee is asserted independently
    // below over the raw response bodies, so it holds even when this
    // projection fails to render.
    const reviewHeading = dialog.getByRole('heading', { name: 'Content review', level: 3 })
    const unavailable = dialog.getByText('Content review unavailable right now.', { exact: false })
    await expect(reviewHeading.or(unavailable)).toBeVisible({ timeout: 10_000 })

    // When findings did render, spot-check the redacted row shape (category/
    // verdict/message text, a node COUNT, never a node id or raw prose;
    // ContentSummarySection in AssignChildrenDialog.tsx). Conditional because
    // whether this particular story has any threshold-surfaced finding right
    // now is a property of live moderation data, not of the code under test.
    const findingRows = dialog.locator('.review-finding')
    if ((await findingRows.count()) > 0) {
      const first = findingRows.first()
      await expect(first.locator('.review-finding__category')).toBeVisible()
      await expect(first.locator('.review-finding__message')).toBeVisible()
    }

    // Never confirm: close via Cancel only, so nothing is assigned.
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('no /api/v1 response body in this suite ever carries flagged_passages or raw prose', () => {
    // Positive control against a vacuous pass: if the collector captured
    // nothing (a wiring mistake, every response failing to parse, or the
    // suite issuing no requests at all), the scan below would trivially find
    // zero violations, indistinguishable from the redaction guarantee
    // actually holding.
    expect(
      capturedResponses.length,
      'the response collector captured no /api/v1 JSON bodies in this suite; ' +
        'the redaction assertion below would otherwise pass vacuously'
    ).toBeGreaterThan(0)

    const violations = capturedResponses.flatMap(({ url, body }) =>
      findForbiddenKeys(body).map((path) => `${url} -> ${path}`)
    )
    expect(violations).toEqual([])
  })

  test('the requests queue and profiles list both prove cross-family isolation', async () => {
    await gotoResilient(sharedPage, '/guardian/requests')
    await unlockParentalGateIfPresent(sharedPage)
    // Positive control: the page's own heading must render before the
    // zero-count claim below means anything.
    await expect(
      sharedPage.getByRole('heading', { name: 'Requests from your kids', level: 1 })
    ).toBeVisible()
    // The zero-count claim itself, rendered as StoryRequestQueue's own
    // EmptyState copy (title AND description), not just an absent list, so a
    // genuinely-empty state is distinguishable from one that never finished
    // loading. This is a real isolation signal, not a tautology: the real
    // family (3a152319) has 1 pending story request right now, and this
    // account lives in its own, separately-seeded E2E Test Family
    // (84b96700), which has 0. An account sharing the real family would also
    // see zero once that one request resolved; it is the account's isolation
    // into its own family, not the number itself, that makes this
    // meaningful.
    await expect(
      sharedPage.getByRole('heading', { name: 'No requests to review', level: 2 })
    ).toBeVisible()
    await expect(
      sharedPage.getByText('New story ideas from your children appear here.')
    ).toBeVisible()

    await gotoResilient(sharedPage, '/guardian/profiles')
    await unlockParentalGateIfPresent(sharedPage)
    await expect(sharedPage.getByRole('heading', { name: 'Profiles', level: 1 })).toBeVisible()
    // The real family has 2 child profiles; the E2E Test Family has 1. Seeing
    // 1 here (not 2, and certainly not 3, the sum across every family in the
    // database) is the same cross-family isolation signal as the zero
    // requests above.
    await expect(sharedPage.locator('.profiles__list > li')).toHaveCount(1)
  })
})
