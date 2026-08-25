import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, resetRealState, revokeDevice } from './real-stack'

/**
 * Real-API series continuation: the seeded dev reader plays "Ember Trail 1"
 * (the WS-G PR2 dev seed's two-book, state-carrying series, scripts/
 * seed_dev_data.py) to its ending, follows "Continue the series", and lands
 * on "Ember Trail 2"'s opening passage. No route mocks; every /api call hits
 * uvicorn through the preview proxy, authorized as the seeded dev-child
 * subject (ENVIRONMENT=local trusts the bearer token).
 */

let deviceGrant: DeviceGrant | null = null

test.beforeEach(async ({ context }) => {
  await requireBackend()
  // Truncate reading_state (among other seed-family fixture state) so each test
  // starts with NO server-side reading row for either Ember book. This matters
  // because ReaderPage applies a continuation seed only when saved server state
  // is undefined (ReaderPage.tsx: "the continuation seed applies ONLY to a fresh
  // read"): without the reset, one test's persisted book-2 row would suppress
  // the other test's carry/no-carry play and make the courage-gate assertions
  // order-dependent. resetRealState preserves the seeded s_dev_ember_1/_2 books
  // (it deletes only worker-generated UUID-shaped storybook ids).
  resetRealState()
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
})

test.afterEach(async () => {
  // Revoke the per-test grant so a reused dev stack does not accumulate one
  // live grant row per run; best-effort (see revokeDevice), never fails a test.
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('the seeded child continues a real series into book 2', async ({ page }) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Locate the seeded "Ember Trail 1" card by title rather than a fixed
  // shelf position: the profile id in the URL is dynamic, so a direct
  // /read/<profileId>/s_dev_ember_1/1 navigation is not possible here.
  await page.getByRole('link', { name: 'Ember Trail 1' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  // TWO clicks, not five. This series is band 10-13, a flowed band (ADR-026,
  // FLOWED_BANDS in reader/readerProgress.ts), so a single-choice node never
  // renders a button: it flows into the same stop as the branch it leads to.
  // Only real decisions are tappable here.
  //
  // The walk: stop 1 is n_e1_start flowed into n_e1_decision1, where the
  // brave fork (c_n_e1_brave, sets courage=3, the value this test proves
  // carries into book 2 below) is taken; that flows n_e1_fork_brave into the
  // shared hub n_e1_hub, where explore (c_n_e1_explore) is taken; that flows
  // n_e1_explore straight into the success ending.
  //
  // The prelude/onward ids (c_n_e1_start_on, c_n_e1_fork_brave_on,
  // c_n_e1_explore_on) are real choices the ENGINE still takes; they are just
  // never rendered as buttons at this band, so clicking them timed out.
  await page.getByTestId('choice-c_n_e1_brave').click()
  await page.getByTestId('choice-c_n_e1_explore').click()
  await expect(page.getByTestId('ending-screen')).toBeVisible()

  const continueButton = page.getByTestId('continue-series')
  await expect(continueButton).toBeVisible()
  await continueButton.click()

  // Book 2 opens at its declared series entry node (metadata.series
  // .series_entry_node = n_e2_start), which is single-choice and therefore
  // flows into n_e2_decision1 at this band, so the opening stop renders BOTH
  // bodies concatenated.
  //
  // The expected prose is book 2's OWN, from _BOOK_PROSE[1] in
  // scripts/seed_dev_data.py, which is the source of truth for these strings.
  // Until 2026-08-23 every node body was shared between the two books and
  // differed only by the "Ember Trail N: " title prefix; the SR-10 diversity
  // fix gave book 2 its own leg of the journey (a river crossing rather than a
  // ridge trail), and this assertion was left expecting book 1's
  // "the trail begins." Keep these strings in step with _BOOK_PROSE.
  await expect(page).toHaveURL(/\/read\/[^/]+\/s_dev_ember_2\//)
  await expect(page.getByTestId('passage-body')).toContainText(
    'Ember Trail 2: the river crossing waits below.'
  )

  // Walk book 2's PLAIN fork, never its brave one, to reach the shared hub
  // (n_e2_hub) where the gated choice lives. This is deliberate: book 2 has
  // its OWN c_n_e2_brave choice that sets courage=3 locally (see
  // _series_blob), so taking the brave fork here would unlock
  // c_n_e2_carried regardless of anything carried from book 1, and the
  // carries_state proof below would show nothing. By taking the plain fork
  // instead (c_n_e2_plain, the one tappable choice on the way), book 2's own
  // courage stays at its initial 0, so the only way c_n_e2_carried's
  // courage>=2 condition can be true is a real carry-in from book 1's brave
  // path above. c_n_e2_start_on and c_n_e2_fork_plain_on are flowed, not
  // tapped, at this band.
  await page.getByTestId('choice-c_n_e2_plain').click()

  // carries_state:true proof (the point of the whole flow): book 1's brave path
  // set courage=3, and that var_state carried through the real reading-state
  // persistence into book 2, unlocking the choice gated on courage>=2. That
  // choice is hidden on a fresh, non-carried play of book 2 (asserted by the
  // next test), and it cannot have been unlocked by book 2's own brave fork
  // because the walk above deliberately avoided it, so its presence here
  // proves the carry happened rather than being a choice that is simply
  // always shown or one that book 2 unlocked on its own. See
  // scripts/seed_dev_data.py's _series_blob for the gated choice and its
  // condition.
  await expect(page.getByTestId('choice-c_n_e2_carried')).toBeVisible()
})

test('book 2 played fresh, without a carried courage, hides the gated choice', async ({ page }) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  // Open book 2 directly from the shelf: a fresh read with no book-1 state to
  // carry in, so courage stays at its initial 0. This is the negative half of
  // the carries_state proof: the courage>=2 choice unlocked in the test above
  // is genuinely gated, not unconditionally rendered.
  await page.getByRole('link', { name: 'Ember Trail 2' }).click()
  await expect(page).toHaveURL(/\/read\/[^/]+\/s_dev_ember_2\//)
  await expect(page.getByTestId('reader')).toBeVisible()
  // Book 2's own entry prose, per _BOOK_PROSE[1]; see the note in the test
  // above for why this is not book 1's "the trail begins."
  await expect(page.getByTestId('passage-body')).toContainText(
    'Ember Trail 2: the river crossing waits below.'
  )

  // n_e2_start's single prelude choice is flowed, not tapped (band 10-13), so
  // the opening stop already reaches n_e2_decision1 and its choices are on
  // screen without any click.
  //
  // The plain choice is always offered on the decision node.
  await expect(page.getByTestId('choice-c_n_e2_plain')).toBeVisible()

  // Walk the PLAIN fork to the shared hub, exactly like the positive test
  // above, so this negative assertion is checked at the same node
  // (n_e2_hub) rather than on the entry passage where the gated choice
  // does not even live anymore.
  await page.getByTestId('choice-c_n_e2_plain').click()

  // Assert we are actually ON the hub (its own always-visible choices are
  // present, and its passage body matches) IN THE SAME assertion block as
  // the count-0 check below. A bare toHaveCount(0) on a test id is
  // satisfied both by a correctly-hidden choice AND by a choice that does
  // not exist anywhere on the page (a renamed id, or a walk that landed on
  // the wrong node entirely), so it can pass for the wrong reason. Pinning
  // the node first makes a wrong-node walk fail loudly here instead of
  // letting the count-0 check pass vacuously.
  await expect(page.getByTestId('passage-body')).toContainText(
    'Ember Trail 2: both bridges land on the same warm rock.'
  )
  await expect(page.getByTestId('choice-c_n_e2_explore')).toBeVisible()
  await expect(page.getByTestId('choice-c_n_e2_rush')).toBeVisible()

  // The courage-gated choice is hidden (visibleChoices drops a
  // false-condition choice, matching runtime semantics) because no book-1
  // courage was carried in, and book 2's own brave fork (which would also
  // set courage=3) was never taken on this walk.
  await expect(page.getByTestId('choice-c_n_e2_carried')).toHaveCount(0)
})
