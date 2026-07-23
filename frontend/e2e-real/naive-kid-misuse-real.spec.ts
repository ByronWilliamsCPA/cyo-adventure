import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API naive-child misuse: the button-mashing a small child actually does,
 * exercised against the real seeded stack (no route mocks; every /api call hits
 * uvicorn through the preview proxy, authorized as the seeded dev-child subject).
 * The invariant under test across every case is the same: the child always
 * reaches a graceful state, never a raw error or a dead end.
 *
 * This file also keeps the real-API cross-family authorization check: the mocked
 * tier cannot exercise it at all, since authorize_profile(principal, parsed)
 * (library.py:262) is server-side authorization, not frontend behavior a route
 * mock stands in for. Seeded by scripts/seed_dev_data.py's second, unrelated
 * family.
 */

const UNRELATED_PROFILE_ID = '22222222-2222-2222-2222-222222222222'

let deviceGrant: DeviceGrant | null = null

test.beforeEach(async ({ context }) => {
  await requireBackend()
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

test("a hand-edited URL into another family's profile is rejected, not served", async ({
  page,
}) => {
  // #ASSUME: timing dependencies: LibraryPage fires its /api/v1/library
  // fetch during the initial render, which can complete before a listener
  // registered after navigation ever attaches (waitForLoadState('networkidle')
  // resolves only once that request has already settled).
  // #VERIFY: registering waitForResponse before goto() catches the request
  // as it happens, matching the standard Playwright wait-then-navigate order.
  const apiResponsePromise = page.waitForResponse(
    (res) => res.url().includes(`/api/v1/library`) && res.url().includes(UNRELATED_PROFILE_ID),
    { timeout: 5_000 }
  )
  // #ASSUME: data-integrity: page.goto()'s own response is the SPA's static
  // document (client-side routing under Vite preview), which is 200 for any
  // path regardless of API authorization outcome, so it cannot stand in for
  // "was the other family's content served."
  // #VERIFY: assert on the structural signals LibraryPage renders only in
  // its ready state (kid-reads.spec.ts uses the same "Continue Reading"
  // region and .library__shelf selectors for a successful library), not on
  // unverified error-state copy.
  await page.goto(`/library/${UNRELATED_PROFILE_ID}`)
  const apiResponse = await apiResponsePromise

  // No waitForLoadState('networkidle') here: the specific /api/v1/library
  // response is already awaited above, and the toHaveCount(0) assertions below
  // auto-retry, so the networkidle wait (which Playwright discourages as
  // flake-prone) adds nothing.
  //
  // P4-4: this asserts 401, not 403. Under ADR-014 (device-authorized kid
  // access), a kid reads a profile's library with a signed PER-PROFILE child
  // session token. This device-authorized kid never minted a child session for
  // the unrelated family's profile, so the request carries no valid credential
  // FOR THAT RESOURCE and fails authentication (401), before any ownership
  // check runs. That is distinct from, and stronger than, the 403 a fully
  // authenticated wrong-family principal gets (see the guardian cross-family
  // rows in tests/integration/test_authz_matrix.py). The old 403 assertion
  // predates the per-profile-session model. 401 is the intended contract.
  expect(apiResponse.status()).toBe(401)
  await expect(page.getByRole('region', { name: 'Continue Reading' })).toHaveCount(0)
  await expect(page.locator('.library__shelf > li')).toHaveCount(0)
})

/** Walk the seeded child into their own library (the misuse tests below all
 * start here). Mirrors kid-reads.spec.ts's picker -> library step. */
async function openDevReaderLibrary(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)
}

test('mashing "Send" on a story request creates exactly one request', async ({ page }) => {
  await openDevReaderLibrary(page)

  // Count POST creates directly off the wire. The create call is a bare POST to
  // /v1/story-requests; the list GET always carries a ?profile_id query, so this
  // pattern (path end or a query start) counts creates only.
  let createCalls = 0
  page.on('request', (req) => {
    if (req.method() === 'POST' && /\/v1\/story-requests(?:\?|$)/.test(req.url())) {
      createCalls += 1
    }
  })

  await page.getByRole('button', { name: 'Request a story' }).click()
  await page.getByLabel('What should your story be about?').fill('A brave otter explorer')

  // A small child jabs "Send" several times fast. The component guards with a
  // synchronous `saving` flag AND disables the button, and closes the form on
  // success, so only the first tap creates a request; later taps hit a disabled
  // or detached button (force + catch swallow those) and never fire a second
  // create.
  const sendButton = page.getByRole('button', { name: /^send$/i })
  await sendButton.click()
  for (let i = 0; i < 3; i += 1) {
    await sendButton.click({ timeout: 500, force: true }).catch(() => {})
  }

  await expect.poll(() => createCalls).toBe(1)
  // Graceful outcome: either the request is now listed as pending, or (if the
  // 5-pending cap was already hit) the friendly "lots of ideas waiting" copy
  // shows. The raw generic error must never greet the child.
  await expect(
    page
      .getByText('Waiting for a grown-up to say yes')
      .or(page.getByText('You have lots of ideas waiting already!'))
  ).toBeVisible()
  await expect(page.getByText('Something went wrong. Try again!')).toHaveCount(0)
})

test('mashing reader choices never corrupts state or dead-ends', async ({ page }) => {
  await openDevReaderLibrary(page)

  // A standalone, real-prose, multi-node book (same pin as kid-reads.spec.ts):
  // avoids leaving series reading state behind.
  await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
  await expect(page).toHaveURL(/\/read\//)

  // #ASSUME: data-integrity: the shared-DB real tier persists reading_state
  // across spec files, and kid-reads.spec.ts (which runs earlier, same seeded
  // "Dev Reader", same pinned title) reads this book to an ending. The reader
  // restores the last persisted node, so this test can open straight onto the
  // ending screen, which carries data-testid="ending-screen" and no
  // data-testid="reader". Starting the mash there would fail on the missing
  // reader before a single choice is tapped.
  // #VERIFY: wait for whichever surface the restore lands on, and if it is the
  // ending screen, "Read again" (data-testid="restart") returns to a fresh
  // reading passage so the mash starts from a real choice node.
  await expect(page.getByTestId('reader').or(page.getByTestId('ending-screen'))).toBeVisible()
  if (await page.getByTestId('ending-screen').count()) {
    await page.getByTestId('restart').click()
  }
  await expect(page.getByTestId('reader')).toBeVisible()

  // The child jabs at the choice buttons far faster than pages render. The
  // deterministic XState reader processes CHOOSE events one at a time, so a
  // burst of taps must never corrupt state, dead-end, or surface the
  // "that page got stuck" error screen. force + catch tolerate a button that
  // has already detached under a rapid tap.
  for (let i = 0; i < 15; i += 1) {
    if (await page.getByTestId('ending-screen').count()) break
    await page
      .locator('[data-testid^="choice-"]')
      .first()
      .click({ timeout: 1000, force: true })
      .catch(() => {})
  }

  // Graceful end state: never the reader error screen, and either a finished
  // story or a live passage still offering at least one choice (no dead end).
  await expect(page.locator('.reader-error')).toHaveCount(0)
  if ((await page.getByTestId('ending-screen').count()) === 0) {
    await expect(page.locator('[data-testid^="choice-"]').first()).toBeVisible()
  }
})

test('garbage idea input is handled gracefully with no error shown to the child', async ({
  page,
}) => {
  await openDevReaderLibrary(page)

  await page.getByRole('button', { name: 'Request a story' }).click()
  const idea = page.getByLabel('What should your story be about?')
  const sendButton = page.getByRole('button', { name: /^send$/i })

  // Empty and whitespace-only: "Send" stays disabled (the component trims), so a
  // child cannot submit nothing and is never shown a validation error for it.
  await expect(sendButton).toBeDisabled()
  await idea.fill('      ')
  await expect(sendButton).toBeDisabled()

  // Emoji-only and an over-long mash of junk: the textarea caps length at 500
  // (maxlength), so "very long" is truncated client-side, and the child submits
  // whatever is left. Whatever the backend makes of it, the child must land in a
  // graceful state, never the raw generic error.
  await idea.fill('🦊🎈🚀'.repeat(40))
  await expect(sendButton).toBeEnabled()
  await sendButton.click()

  // Graceful outcome: the form closed back to the "Request a story" button
  // (accepted), or the friendly cap copy shows (busy). Never the generic error.
  await expect(
    page
      .getByRole('button', { name: 'Request a story' })
      .or(page.getByText('You have lots of ideas waiting already!'))
  ).toBeVisible()
  await expect(page.getByText('Something went wrong. Try again!')).toHaveCount(0)
})
