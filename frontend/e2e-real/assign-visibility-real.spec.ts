import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import {
  BACKEND,
  authorizeDevice,
  requireBackend,
  resetRealState,
  revokeDevice,
} from './real-stack'

/**
 * The full approve -> assign -> child-sees loop, end to end against the real
 * stack. This proves the product's most non-obvious required step: approval
 * alone does NOT put a book on a child's shelf; a guardian must also ASSIGN it
 * to that specific child (api/library.py::list_library gates on BOTH
 * approved_by IS NOT NULL AND an assignment row for the profile). No mocked or
 * component test exercises that coupling end to end.
 *
 * The seed (scripts/seed_dev_data.py) assigns s_bridge_builder to the built-in
 * "Dev Reader", so this spec creates its own two fresh child profiles to get
 * genuinely unassigned shelves: `assignChild` (the assign target) and
 * `controlChild` (never assigned, the concurrent negative). Both are created
 * Node-side as the seeded dev-guardian and deleted in afterAll, mirroring
 * guardian-profile-crud-real.spec.ts's direct-fetch setup/teardown rather than
 * adding a helper to real-stack.ts for a single-file need.
 *
 * Serial: test 1 approves, test 3 assigns, and the child-shelf tests observe
 * the persisted result of each in order.
 *
 * #ASSUME: data-integrity: timestamp-suffixed display names keep the two
 * created profiles uniquely findable and collision-free across consecutive
 * runs; resetRealState never touches hand-created profiles, so afterAll's
 * DELETE is what keeps the row count from growing.
 * #VERIFY: the afterAll DELETE removes both rows a normal run creates.
 */

test.describe.configure({ mode: 'serial' })

const DEV_GUARDIAN_BEARER = 'dev-guardian'
const REVIEW_STORY_ID = 's_bridge_builder'
const REVIEW_STORY_TITLE = 'The Bridge Builder'

const stamp = Date.now()
const ASSIGN_CHILD_NAME = `Assign Target ${stamp}`
const CONTROL_CHILD_NAME = `Assign Control ${stamp}`

interface ProfileRow {
  id: string
  display_name: string
}

async function createChild(displayName: string): Promise<string> {
  const res = await fetch(`${BACKEND}/api/v1/profiles`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ display_name: displayName, age_band: '10-13' }),
  })
  expect(res.ok, `POST /profiles for "${displayName}" failed (HTTP ${res.status})`).toBe(true)
  const row = (await res.json()) as ProfileRow
  return row.id
}

async function deleteChild(id: string): Promise<void> {
  // Best-effort teardown: a stray profile is harmless (uniquely named) and the
  // local dev stack is disposable, so a failed delete must not fail the run.
  try {
    const res = await fetch(`${BACKEND}/api/v1/profiles/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    })
    if (!res.ok && res.status !== 404) {
      console.warn(`[assign-visibility] profile ${id} delete did not confirm (HTTP ${res.status}).`)
    }
  } catch (err) {
    console.warn(
      `[assign-visibility] profile ${id} delete errored: ` +
        `${err instanceof Error ? err.message : String(err)}`
    )
  }
}

let assignChildId = ''
let controlChildId = ''

// Per-file reset so this file is order-independent in the shared-DB tier
// (reverts s_bridge_builder to in_review), then two fresh unassigned children.
test.beforeAll(async () => {
  resetRealState()
  assignChildId = await createChild(ASSIGN_CHILD_NAME)
  controlChildId = await createChild(CONTROL_CHILD_NAME)
})

test.afterAll(async () => {
  await deleteChild(assignChildId)
  await deleteChild(controlChildId)
})

test.beforeEach(async () => {
  await requireBackend()
})

test('the admin approves the review story to the family', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-admin')
  await page.goto(`/admin/review/${REVIEW_STORY_ID}`)
  await expect(page.getByRole('heading', { name: REVIEW_STORY_TITLE })).toBeVisible()

  await page.getByRole('button', { name: /^Approve$/ }).click()
  // Default (family) visibility: the assign gate, not catalog reach, is what
  // this spec is about.
  await page.getByRole('button', { name: 'Confirm approve' }).click()
  await expect(page).toHaveURL(/\/admin$/)

  // Persisted, not optimistic: after reload the story is out of the queue.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByRole('link', { name: new RegExp(REVIEW_STORY_TITLE) })).toHaveCount(0)
})

test('the newly created child does not see the approved-but-unassigned book', async ({
  page,
  context,
}) => {
  // Approved is not enough: this child was never assigned the book, so its
  // shelf must stay empty. This is the causal half of the proof (the same
  // child gains the book only after the assign in the next test).
  const grant = await authorizeDevice(context)
  try {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await page.goto('/kids')
    await page.getByText(ASSIGN_CHILD_NAME).click()
    await expect(page).toHaveURL(/\/library\//)
    // The empty-state confirms the shelf rendered (not an unauthenticated or
    // still-loading page), so the absence below is a true "not assigned".
    await expect(page.getByText('No books yet')).toBeVisible()
    await expect(page.getByText(REVIEW_STORY_TITLE)).toHaveCount(0)
  } finally {
    await revokeDevice(grant)
  }
})

test('the guardian assigns the approved book to the target child', async ({ page, context }) => {
  await seedGuardianSession(context, DEV_GUARDIAN_BEARER)
  await page.goto('/guardian/books')

  const bookRow = page.locator('li.books__row', { hasText: REVIEW_STORY_TITLE })
  await expect(bookRow).toBeVisible()
  await bookRow.getByRole('button', { name: `Assign ${REVIEW_STORY_TITLE}` }).click()

  const dialog = page.getByRole('dialog', { name: 'Assign to children' })
  await expect(dialog).toBeVisible()
  // Scope the checkbox to this child's own row: "Dev Reader" is already
  // seed-assigned (checked + disabled) and the control child is also listed.
  const childRow = dialog.locator('li.assign__row', { hasText: ASSIGN_CHILD_NAME })
  await childRow.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Assign', exact: true }).click()

  // Persisted, not optimistic: reload and confirm the assignment stuck.
  await page.reload()
  const reloadedRow = page.locator('li.books__row', { hasText: REVIEW_STORY_TITLE })
  await expect(reloadedRow.getByText(ASSIGN_CHILD_NAME)).toBeVisible()
})

test('the assigned child now sees the book in their library', async ({ page, context }) => {
  const grant = await authorizeDevice(context)
  try {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await page.goto('/kids')
    await page.getByText(ASSIGN_CHILD_NAME).click()
    await expect(page).toHaveURL(/\/library\//)
    await expect(page.getByText(REVIEW_STORY_TITLE)).toBeVisible()
  } finally {
    await revokeDevice(grant)
  }
})

test('a different, unassigned child still does not see the book', async ({ page, context }) => {
  // The concurrent negative: assignment is per-child, so approving and
  // assigning to one child must never leak the book onto a sibling's shelf.
  const grant = await authorizeDevice(context)
  try {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await page.goto('/kids')
    await page.getByText(CONTROL_CHILD_NAME).click()
    await expect(page).toHaveURL(/\/library\//)
    await expect(page.getByText('No books yet')).toBeVisible()
    await expect(page.getByText(REVIEW_STORY_TITLE)).toHaveCount(0)
  } finally {
    await revokeDevice(grant)
  }
})
