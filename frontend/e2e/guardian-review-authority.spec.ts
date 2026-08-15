import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * G6 authority boundary: `/guardian/review/:storybookId`
 * (`frontend/src/guardian/GuardianReviewDetailPage.tsx`).
 *
 * Why this file exists. The route had NO coverage at any E2E tier, and the
 * coverage matrix credited it with `review-edit.spec.ts`, which drives
 * `/admin/review/s1` on all four of its `goto` calls and never reaches this
 * one. The shared passage-edit modules live under `guardian/`, which is how
 * the mix-up happened, but exercising a shared module through the ADMIN route
 * proves nothing about this route's guard.
 *
 * What only a network-tier test can prove. This route is a different
 * authority boundary from the admin review page, not a second door to it:
 * a guardian reaches their OWN family's story to fix prose, and must never be
 * handed Approve, Archive, Send back, cover generation, or version compare
 * (ADR-005: approve/publish is admin-only, with no guardian path).
 * `GuardianReviewDetailPage.test.tsx` asserts that at the component tier by
 * rendering the component directly. That cannot catch the failure this file
 * is aimed at: a widened guard, a shell that leaks an action bar, or a route
 * remapped to the admin component would all leave the component test green
 * while the real page grew the controls.
 *
 * The positive control is the point. Absence assertions are the easiest kind
 * of test to pass for the wrong reason: `toHaveCount(0)` also passes when the
 * page 500s, renders an empty shell, or never mounts. So every control this
 * file asserts absent from `/guardian/review/s1` is asserted PRESENT on
 * `/admin/review/s1` in the same file, from the SAME fixture. If the admin
 * half ever goes quiet, the guardian half's silence stops being evidence and
 * the suite says so.
 */

/**
 * One review surface, served to both routes. Sharing it is deliberate: it
 * removes "the two pages got different data" as an explanation for the two
 * pages rendering different controls, which is what makes the comparison a
 * control rather than two unrelated observations.
 *
 * Shape mirrors `guardian-review.spec.ts`/`review-edit.spec.ts` (n1 -> n2).
 */
const SURFACE = {
  storybook_id: 's1',
  version: 1,
  status: 'in_review',
  screened: true,
  summary: {
    count: 1,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
  blob: {
    title: 'The Cave',
    start_node: 'n1',
    nodes: [
      {
        id: 'n1',
        body: 'A dark cave yawned ahead.',
        choices: [{ id: 'c1', label: 'Step inside', target: 'n2' }],
      },
      { id: 'n2', body: 'The path forked left and right.', choices: [] },
    ],
  },
  flagged_passages: [
    {
      node_id: 'n1',
      prose: 'A dark cave yawned ahead.',
      findings: [
        {
          stage: 1,
          source: 'llm_safety',
          category: 'safety',
          node_id: 'n1',
          verdict: 'flag',
          score: null,
          message: 'possibly scary',
        },
      ],
    },
  ],
  // Required, not optional: the page does
  // `surface.story_level_findings.flatMap(...)` unconditionally, so omitting
  // this throws inside render and the route degrades to the RouteError
  // boundary. That failure mode is worth naming here, because the symptom is
  // a heading that never appears, which reads like a routing or auth problem
  // rather than a fixture one.
  story_level_findings: [],
}

/**
 * The controls that separate the two routes. Each is matched the way a user
 * meets it, by accessible role and name, not by test id: a test id can stay
 * attached to a control that has been relabelled or restyled into something
 * a reviewer would no longer recognise, and the claim here is about what the
 * page OFFERS, not about what it is built from.
 */
const ADMIN_ONLY_CONTROLS = [
  { role: 'button' as const, name: 'Approve' },
  { role: 'button' as const, name: 'Archive' },
  { role: 'button' as const, name: 'Generate cover' },
]

/**
 * Endpoints no guardian visit may ever reach. Registered as failing routes
 * rather than asserted after the fact, so a stray call fails the test at the
 * moment it fires and names itself, instead of surfacing as a confusing
 * downstream expectation miss.
 */
const ADMIN_ONLY_ENDPOINTS = [
  '**/api/v1/storybooks/*/approve',
  '**/api/v1/storybooks/*/archive',
  '**/api/v1/storybooks/*/send-back',
  '**/api/v1/storybooks/*/versions/*/cover',
]

async function forbidAdminEndpoints(page: Page, calls: string[]): Promise<void> {
  for (const pattern of ADMIN_ONLY_ENDPOINTS) {
    await page.route(pattern, (route) => {
      calls.push(route.request().url())
      // Fulfil rather than abort: an abort can surface as a generic network
      // error the page might render as its ordinary "please reload" state,
      // which would read as an unrelated failure. A 403 is what the real
      // backend would answer a guardian here, so the page's own handling
      // stays realistic while `calls` records that it was reached at all.
      return route.fulfill({ status: 403, json: { detail: 'forbidden' } })
    })
  }
}

async function mockSurface(page: Page): Promise<void> {
  await page.route('**/api/v1/storybooks/s1/review*', (route) => route.fulfill({ json: SURFACE }))
}

test.beforeEach(async ({ context }) => {
  await seedGuardianSession(context)
})

test('the guardian review route renders the story but offers no admin control', async ({
  page,
}) => {
  const forbiddenCalls: string[] = []
  await mockMe(page)
  await mockEmptyConsole(page)
  await mockSurface(page)
  await forbidAdminEndpoints(page, forbiddenCalls)

  await page.goto('/guardian/review/s1')

  // Establish the page actually rendered BEFORE asserting anything is absent.
  // Without this the whole test degrades into "nothing is on the screen",
  // which is exactly the false pass the positive control below guards.
  await expect(page.getByRole('heading', { name: 'The Cave', level: 1 })).toBeVisible()
  // Scoped to the read-through passage by id: this prose also renders in the
  // flagged-passage panel above, so an unscoped text match is a strict-mode
  // violation rather than a stronger assertion.
  await expect(page.locator('#passage-n1')).toContainText('A dark cave yawned ahead.')

  for (const control of ADMIN_ONLY_CONTROLS) {
    await expect(page.getByRole(control.role, { name: control.name })).toHaveCount(0)
  }
  // 'Send back' is a dialog title on the admin page rather than a bare
  // button label, so it is matched as text.
  await expect(page.getByText('Send back for revision')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /compar/i })).toHaveCount(0)

  // The guardian's own way back is present: refusing the actions must not
  // also strand them.
  await expect(page.getByRole('link', { name: 'Back to My Requests' })).toBeVisible()

  expect(forbiddenCalls).toEqual([])
})

test('POSITIVE CONTROL: the same fixture on the admin route does render those controls', async ({
  page,
}) => {
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await mockSurface(page)

  await page.goto('/admin/review/s1')

  await expect(page.getByRole('heading', { name: 'The Cave', level: 1 })).toBeVisible()

  // If any of these ever stops rendering here, the sibling test's
  // `toHaveCount(0)` assertions stop being evidence of a guard and start
  // being evidence of nothing. That is the failure this test exists to make
  // loud, so it is deliberately asserted control-by-control rather than
  // collapsed into a single smoke check.
  for (const control of ADMIN_ONLY_CONTROLS) {
    await expect(page.getByRole(control.role, { name: control.name })).toBeVisible()
  }
})

test("another family's story is refused with a way back, not a dead end", async ({ page }) => {
  const forbiddenCalls: string[] = []
  await mockMe(page)
  await mockEmptyConsole(page)
  await forbidAdminEndpoints(page, forbiddenCalls)
  // What `_load_review_target` (api/approval.py) answers a guardian asking
  // for a story their family does not own.
  await page.route('**/api/v1/storybooks/s9/review*', (route) =>
    route.fulfill({ status: 403, json: { detail: 'forbidden' } })
  )

  await page.goto('/guardian/review/s9')

  await expect(page.getByRole('alert')).toContainText('This story belongs to a different family.')
  // The refusal is not a dead end: a parent who mistyped a link, or followed
  // a stale one, still has a route back into their own console.
  await expect(page.getByRole('link', { name: 'Back to My Requests' })).toBeVisible()
  // No prose from any story leaks alongside the refusal.
  await expect(page.getByText('A dark cave yawned ahead.')).toHaveCount(0)

  expect(forbiddenCalls).toEqual([])
})
