import { expect, test } from '@playwright/test'

import { seedGuardianSession } from '../e2e/support/auth'

import { authorizeDevice, requireBackend, resetRealState, revokeDevice } from './real-stack'

/**
 * Real G9 guardian reading-history path. The seeded child reads a real
 * published story to an ending (mirrors kid-reads.spec.ts's flow), which
 * persists a real ``ReadingState`` row and, on reaching the ending, a real
 * ``Completion`` row (api/reading.py). The guardian then opens Reading from
 * the nav and expands the "Dev Reader" card, asserting the real per-child
 * summary (``GET /v1/families/me/reading-summary``) and per-book history
 * (``GET /v1/reading-history/{profile_id}``) reflect that read.
 *
 * "The Clockwork Garden" (not "The Tide Pool Mystery") is read here so this
 * spec's Completion row is independent of kid-reads.spec.ts's; the
 * always-first-choice walk is deterministic (n_start -> n_shed -> n_toolbox
 * -> n_gate -> n_tower -> n_clock_end), so it always lands on the same
 * ending (`e_clock`) and the Completion row's composite primary key
 * (child_profile_id, storybook_id, version, ending_id) makes a second
 * consecutive run idempotent rather than duplicating a row.
 *
 * Serial: the guardian-side assertions depend on the read having happened
 * first.
 */

test.describe.configure({ mode: 'serial' })

// Per-file reset (truncates reading_state and clears the seed family's
// kid_flag rows) so this file starts from a pristine baseline regardless of
// what ran earlier in the same full-suite invocation: a stale reading_state
// row would change which node the read-to-ending walk starts from, and
// accumulated kid-flag toasts would make the "Dev Reader" locator below
// strict-mode-ambiguous even with the role-scoped fix.
test.beforeAll(() => {
  resetRealState()
})

test.beforeEach(async () => {
  await requireBackend()
})

test('the seeded child reads a real story to an ending', async ({ page, context }) => {
  const grant = await authorizeDevice(context)
  try {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
    await page.goto('/kids')
    await page.getByText('Dev Reader').click()
    await expect(page).toHaveURL(/\/library\//)

    await page.getByRole('link', { name: 'The Clockwork Garden' }).click()
    await expect(page).toHaveURL(/\/read\//)
    await expect(page.getByTestId('reader')).toBeVisible()

    for (let i = 0; i < 40; i += 1) {
      if (await page.getByTestId('ending-screen').count()) break
      await page.locator('[data-testid^="choice-"]').first().click()
    }
    await expect(page.getByTestId('ending-screen')).toBeVisible()
  } finally {
    // Revoke the minted grant even if an assertion fails, so a reused dev
    // stack does not keep a live grant row; best-effort (see revokeDevice).
    await revokeDevice(grant)
  }
})

test('the guardian sees the real read reflected in reading history', async ({ page, context }) => {
  await seedGuardianSession(context, 'dev-guardian')
  await page.goto('/guardian')
  await page.getByRole('link', { name: 'Reading', exact: true }).click()
  await expect(page).toHaveURL(/\/guardian\/reading$/)

  // Scoped to the reading-card toggle button (not a bare getByText), which
  // would also match a "Dev Reader flagged a story..." guardian-console toast
  // once kid-flag-real.spec.ts has run earlier in a full-suite invocation.
  const devReaderCard = page.getByRole('button', { name: /Dev Reader/ })
  await expect(devReaderCard).toBeVisible()
  await devReaderCard.click()
  await expect(page.getByText('The Clockwork Garden')).toBeVisible()
  // total_endings (4) is fixed by the fixture's metadata.ending_count;
  // endings_found is exactly 1 because the deterministic walk above always
  // lands on the single `e_clock` ending, and repeat runs never duplicate it
  // (see the module docstring on the Completion primary key).
  await expect(page.getByText('1 of 4 endings found')).toBeVisible()
})
