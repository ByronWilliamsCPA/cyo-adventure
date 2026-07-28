import { expect, test, type Locator, type Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedGuardianSession } from './support/auth'

/**
 * Keyboard-operability contract for the shared `cyo-dialog` component
 * (design-system/src/components/Dialog/Dialog.tsx), exercised through three
 * representative modals: the admin review Approve dialog (ReviewDetailPage),
 * the guardian Profile form dialog (ProfileFormDialog), and the guardian
 * Assign-children dialog (AssignChildrenDialog). Axe (a11y.spec.ts) catches
 * static ARIA/contrast issues but cannot see focus-trap logic, Escape
 * handling, or focus restoration, so those behaviors are asserted here against
 * the real built app.
 *
 * The contract each dialog must satisfy (WCAG 2.1.2 No Keyboard Trap is about
 * being ABLE to leave; a modal additionally owes ARIA APG's focus-management
 * behaviors, and failing them is a 2.4.3 Focus Order / 2.1.1 Keyboard defect):
 *   1. opening moves focus into the dialog,
 *   2. Tab off the last focusable wraps to the first and Shift+Tab off the
 *      first wraps to the last (focus never escapes to the page behind),
 *   3. Escape closes the dialog and restores focus to the trigger.
 *
 * The Dialog focus-trap selector (Dialog.tsx) is
 *   button:not(:disabled), [href], input:not(:disabled),
 *   select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])
 * so DIALOG_FOCUSABLE below mirrors it exactly: the first/last elements this
 * test wraps around are the same ones the component computes as the trap
 * boundary. `textarea` is included (the Send Back / Edit passage dialogs are
 * textarea-primary; their keyboard reachability is asserted at the bottom of
 * this file).
 */
const DIALOG_FOCUSABLE =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

/** Assert real DOM focus is on the dialog element or a descendant of it. */
async function expectFocusInsideDialog(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]')
        const active = document.activeElement
        return Boolean(dialog && active && (dialog === active || dialog.contains(active)))
      })
    )
    .toBe(true)
}

/**
 * Assert the Tab focus trap wraps at both ends: from the last focusable,
 * forward Tab returns to the first; from the first, Shift+Tab returns to the
 * last. Directly focusing each boundary (rather than tabbing the whole way
 * there) keeps the assertion about the wrap logic, independent of how many
 * controls sit between them.
 */
async function expectTabTrapWraps(page: Page): Promise<void> {
  const focusables = page.getByRole('dialog').locator(DIALOG_FOCUSABLE)
  const count = await focusables.count()
  expect(count, 'dialog should expose at least one focusable control').toBeGreaterThan(0)
  const first = focusables.first()
  const last = focusables.nth(count - 1)

  await last.focus()
  await page.keyboard.press('Tab')
  await expect(first, 'Tab off the last focusable should wrap to the first').toBeFocused()

  await first.focus()
  await page.keyboard.press('Shift+Tab')
  await expect(last, 'Shift+Tab off the first focusable should wrap to the last').toBeFocused()
}

/**
 * The full open -> trap -> Escape-closes-and-restores-focus contract for one
 * dialog. `trigger` is the control that opened it; after Escape, focus must
 * return there.
 */
async function assertDialogKeyboardContract(page: Page, trigger: Locator): Promise<void> {
  await expect(page.getByRole('dialog')).toBeVisible()
  await expectFocusInsideDialog(page)
  await expectTabTrapWraps(page)

  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(trigger, 'Escape should restore focus to the trigger').toBeFocused()
}

// --- Admin review Approve dialog (ReviewDetailPage) --------------------

const REVIEW_SURFACE = {
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
  story_level_findings: [],
}

async function seedReviewDetail(page: Page): Promise<void> {
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.route('**/api/v1/storybooks/s1/review*', (route) =>
    route.fulfill({ json: REVIEW_SURFACE })
  )
  // useCoverGeneration seeds cover status from this GET on mount; mock it so
  // the call never falls through to the absent backend (see review-edit.spec.ts).
  await page.route('**/api/v1/storybooks/s1/versions/1/cover', (route) =>
    route.fulfill({ json: { cover_status: 'none', cover_url: null } })
  )
}

test('admin review Approve dialog: focus moves in, Tab is trapped, Escape restores focus', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await seedReviewDetail(page)

  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()

  const trigger = page.getByRole('button', { name: 'Approve' })
  await trigger.click()

  await assertDialogKeyboardContract(page, trigger)
})

// --- Guardian Profile form dialog (ProfileFormDialog) ------------------

test('guardian Profile form dialog: focus moves in, Tab is trapped, Escape restores focus', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  // A populated list, so the page renders its <h1>Profiles</h1> without also
  // rendering the empty-state <h2>No profiles yet</h2> (which shares the role
  // name under a substring match).
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: ASSIGN_PROFILES }))

  await page.goto('/guardian/profiles')
  await expect(page.getByRole('heading', { name: 'Profiles', exact: true })).toBeVisible()

  const trigger = page.getByRole('button', { name: 'Add child' })
  await trigger.click()

  await assertDialogKeyboardContract(page, trigger)
})

// --- Guardian Assign-children dialog (AssignChildrenDialog) ------------

const ASSIGN_BOOKS = {
  books: [
    {
      storybook_id: 'story-1',
      title: 'The Brave Little Fox',
      version: 1,
      age_band: '10-13',
      screened: true,
      flagged_count: 0,
      assigned_profile_ids: ['p1'],
      visibility: 'family',
    },
  ],
}

const ASSIGN_PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '10-13',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
    {
      id: 'p2',
      display_name: 'Reader A2',
      age_band: '8-11',
      reading_level_cap: 99,
      avatar: 'owl',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

const ASSIGN_CONTENT_SUMMARY = {
  storybook_id: 'story-1',
  version: 1,
  screened: true,
  summary: null,
  flagged_count: 0,
  findings: [],
}

test('guardian Assign-children dialog: focus moves in, Tab is trapped, Escape restores focus', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await mockMe(page)
  await page.route('**/api/v1/guardian/books', (route) => route.fulfill({ json: ASSIGN_BOOKS }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: ASSIGN_PROFILES }))
  await page.route('**/api/v1/storybooks/story-1/content-summary', (route) =>
    route.fulfill({ json: ASSIGN_CONTENT_SUMMARY })
  )
  // assignApi.get() reads the current assignments on open; without this the
  // dialog's load rejects and it renders an error banner instead of the list.
  await page.route('**/api/v1/storybooks/story-1/assignments', (route) =>
    route.fulfill({ json: { storybook_id: 'story-1', profile_ids: ['p1'] } })
  )

  await page.goto('/guardian/books')
  const trigger = page.getByRole('button', { name: /^Assign The Brave Little Fox$/ })
  await trigger.click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  // Wait for the async profile list to render so the trap boundary is the real
  // checklist + actions, not the transient loading state.
  await expect(dialog.getByText('Reader A2')).toBeVisible()

  await expectFocusInsideDialog(page)
  await expectTabTrapWraps(page)

  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(trigger, 'Escape should restore focus to the trigger').toBeFocused()
})

// --- Textarea-field dialogs: keyboard reachability of the primary field -----

/**
 * Regression guard for a fixed WCAG 2.1.1 (Keyboard, Level A) defect.
 *
 * The Dialog focus-trap selector in design-system/src/components/Dialog/Dialog.tsx
 * previously omitted `textarea`, so in a textarea-primary dialog initial focus
 * landed on the first button and Tab/Shift+Tab bounced between buttons WITHOUT
 * ever visiting the textarea; a keyboard-only user could not reach it, and a
 * mouse user who clicked into it could Shift+Tab straight out to the page behind
 * (the trap leaked, because the textarea was neither the computed `first` nor
 * `last`). Impact: a keyboard-only admin could not type a Send Back reason (so
 * could not send a story back) or edit a passage.
 *
 * Fixed 2026-07-27 by including `textarea` in the shared FOCUSABLE_SELECTOR.
 * These two tests exercise the exact surfaces that were broken (Send Back and
 * Edit passage), so a future selector regression re-fails here.
 */
async function tabReachesTextarea(page: Page): Promise<boolean> {
  const textarea = page.getByRole('dialog').locator('textarea')
  // A generous bound: tab more times than any of these dialogs has controls.
  for (let i = 0; i < 12; i++) {
    if (await textarea.evaluate((el) => el === document.activeElement)) return true
    await page.keyboard.press('Tab')
  }
  return textarea.evaluate((el) => el === document.activeElement)
}

test('admin review Send Back dialog: the reason textarea is reachable by keyboard', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await seedReviewDetail(page)

  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  await page.getByRole('button', { name: 'Send Back' }).click()
  await expect(page.getByRole('dialog', { name: 'Send back for revision' })).toBeVisible()

  expect(
    await tabReachesTextarea(page),
    'a keyboard user must be able to tab to the reason textarea to send a story back'
  ).toBe(true)
})

test('admin review Edit passage dialog: the passage-text textarea is reachable by keyboard', async ({
  page,
  context,
}) => {
  await seedGuardianSession(context)
  await seedReviewDetail(page)

  await page.goto('/admin/review/s1')
  await expect(page.getByRole('heading', { name: 'The Cave' })).toBeVisible()
  await page.locator('#passage-n1').getByRole('button', { name: 'Edit passage' }).click()
  await expect(page.getByRole('dialog', { name: 'Edit passage n1' })).toBeVisible()

  expect(
    await tabReachesTextarea(page),
    'a keyboard user must be able to tab to the passage-text textarea to edit a passage'
  ).toBe(true)
})
