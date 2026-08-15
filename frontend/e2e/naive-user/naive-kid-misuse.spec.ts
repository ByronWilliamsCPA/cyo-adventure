import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from '../support/auth'
import { loadLanternStory } from '../support/fixtures'

const lantern = loadLanternStory()

/**
 * Naive kid misuse: a child using the app alone, unsupervised, prone to
 * double-clicking, refreshing mid-story, and rating things twice. Not a
 * re-run of story-requests-kid.spec.ts / library.spec.ts / reader.spec.ts,
 * which cover the happy paths these tests build on.
 */

// KidNav (mounted by KidShell on every /library/:profileId route) fetches
// GET /api/v1/profiles unconditionally, same as the picker (see
// profiles.spec.ts). Only the describe blocks below that navigate to
// /library/p1 need the mock; "refresh mid-reader" goes straight to a reader
// route, which KidShell does not chrome with KidNav.
const PROFILES = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Remy',
      age_band: '6-8',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

test.describe('double-submitting a story request', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    // ADR-014: an authorized device (grant present) so the kid surface renders.
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
  })

  test('double-clicking Send only creates one story request', async ({ page }) => {
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))

    let createCalls = 0
    let requests: Array<{ id: string; status: string }> = []
    await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
      route.fulfill({ json: { requests } })
    )
    // Deterministic gate instead of a raw 300ms sleep: hold the create POST
    // open until the forced second click has landed, so the impatient-kid
    // window is guaranteed rather than timing-dependent on a CI runner.
    let releaseCreate: () => void = () => {}
    const createGate = new Promise<void>((resolve) => {
      releaseCreate = resolve
    })
    await page.route('**/api/v1/story-requests', async (route) => {
      createCalls += 1
      await createGate
      requests = [{ id: 'req-1', status: 'pending' }]
      return route.fulfill({ json: { id: 'req-1', status: 'pending' } })
    })

    await page.goto('/library/p1')
    await page.getByRole('button', { name: 'Request a story' }).click()
    // WS-B PR 3: RequestStory.tsx now also renders an optional series-name
    // text input while the form is open with no continuation anchor, so an
    // unscoped textbox locator is ambiguous; name the idea textarea.
    await page
      .getByLabel('What should your story be about?')
      .fill('A brave fox who solves mysteries')

    const sendButton = page.getByRole('button', { name: /send/i })
    await sendButton.click()
    // Locator-based wait: RequestStory.tsx's saving-flag guard disables the
    // button synchronously (its label also flips to "Sending…", which the
    // /send/i regex still matches); waiting on disabled is the deterministic
    // in-flight signal. force bypasses Playwright's own enabled-check to
    // simulate a kid mashing it anyway. A genuinely disabled button does not
    // dispatch a click handler even when forced, so this cannot double-count.
    await expect(sendButton).toBeDisabled()
    await sendButton.click({ force: true })
    releaseCreate()

    await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
    expect(createCalls).toBe(1)
  })
})

// F-5: a naive kid's request can genuinely go offline mid-send, not just
// hit the server-side 5-pending cap (already covered by the real-tier
// mashing test). A transport failure (route.abort(), the same OfflineError
// path a real outage throws; see readerApi.ts/classifyApiError.ts) must
// leave a recoverable form, not a stuck "Sending…" button or a lost idea.
test.describe('offline mid-request', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    // ADR-014: an authorized device (grant present) so the kid surface renders.
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
  })

  test('a transport failure while sending shows a recoverable error, not a stuck form', async ({
    page,
  }) => {
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
    let requests: Array<{ id: string; status: string }> = []
    await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
      route.fulfill({ json: { requests } })
    )

    let mode: 'offline' | 'online' = 'offline'
    let createCalls = 0
    // Only POST create requests reach this bare-path pattern (the list GET
    // above always carries a `?profile_id=` query string); see
    // story-requests-kid.spec.ts's identical comment on this convention.
    await page.route('**/api/v1/story-requests', (route) => {
      createCalls += 1
      if (mode === 'offline') {
        return route.abort('internetdisconnected')
      }
      requests = [{ id: 'req-1', status: 'pending' }]
      return route.fulfill({ json: { id: 'req-1', status: 'pending' } })
    })

    await page.goto('/library/p1')
    await page.getByRole('button', { name: 'Request a story' }).click()
    await page
      .getByLabel('What should your story be about?')
      .fill('A brave fox who solves mysteries')
    const sendButton = page.getByRole('button', { name: /^send$/i })
    await sendButton.click()

    await expect(page.getByText('Something went wrong. Try again!')).toBeVisible()
    await expect(sendButton).toBeEnabled()
    // The idea survives the failure so the kid can just retry, not retype it.
    await expect(page.getByLabel('What should your story be about?')).toHaveValue(
      'A brave fox who solves mysteries'
    )

    // Recovery: the same tap succeeds once the network is back.
    mode = 'online'
    await sendButton.click()
    await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
    expect(createCalls).toBe(2)
  })
})

// F-5: an anchored "ask for the next book" request can land after the
// anchor storybook stopped being a valid continuation target (404/422); the
// form must surface a distinct message and clear the anchor so a retry sends
// a plain (anchor-less) request instead of repeating the same failure.
test.describe('stale continuation anchor', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
  })

  test('a stale anchor shows the anchor error and clears so a retry sends a fresh request', async ({
    page,
  }) => {
    const stories = {
      stories: [
        {
          id: 's1',
          title: 'The Lantern',
          version: 2,
          age_band: '6-8',
          tier: 1,
          reading_level_target: 2,
          node_count: 10,
          rating: null,
          progress: null,
          series_id: 'ser-1',
          book_index: 1,
        },
      ],
    }
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))
    let requests: Array<{ id: string; status: string }> = []
    await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
      route.fulfill({ json: { requests } })
    )

    let mode: 'stale' | 'recovered' = 'stale'
    let createCalls = 0
    let createBody: unknown = null
    await page.route('**/api/v1/story-requests', (route) => {
      createCalls += 1
      createBody = route.request().postDataJSON()
      if (mode === 'stale') {
        // The anchor storybook is no longer a valid continuation target by
        // the time the request lands (RequestStory.tsx's isStaleAnchor check).
        return route.fulfill({ status: 404, json: { detail: 'not found' } })
      }
      requests = [{ id: 'req-1', status: 'pending' }]
      return route.fulfill({ json: { id: 'req-1', status: 'pending' } })
    })

    await page.goto('/library/p1')
    const shelf = page.getByRole('region', { name: 'More to Explore' })
    await shelf.getByRole('button', { name: 'Ask for the next book' }).click()
    await expect(page.getByText('Continuing: The Lantern')).toBeVisible()
    await page.getByLabel('What should your story be about?').fill('More lantern adventures')
    await page.getByRole('button', { name: /^send$/i }).click()

    await expect.poll(() => createCalls).toBe(1)
    expect(createBody).toEqual({
      profile_id: 'p1',
      request_text: 'More lantern adventures',
      anchor_storybook_id: 's1',
    })
    await expect(
      page.getByText(
        "That story can't be continued right now. Pick another one, or send a new idea!"
      )
    ).toBeVisible()
    // The anchor is cleared: the "Continuing: ..." banner is gone and the
    // ordinary series-name field is back, so a retry cannot repeat the same
    // stale anchor.
    await expect(page.getByText('Continuing: The Lantern')).toHaveCount(0)
    await expect(page.getByLabel('Part of a series? Give it a name! (optional)')).toBeVisible()

    // Retry: the same idea (untouched by the failure) now sends as a plain,
    // anchor-less request.
    mode = 'recovered'
    await page.getByRole('button', { name: /^send$/i }).click()
    await expect.poll(() => createCalls).toBe(2)
    expect(createBody).toEqual({
      profile_id: 'p1',
      request_text: 'More lantern adventures',
    })
    await expect(page.getByText('Waiting for a grown-up to say yes')).toBeVisible()
  })
})

// F-5 / F-6a: hardware/OS back on the kid surface. Neither an open request
// form nor an in-progress reader session should leave the browser's own back
// button producing a dead end or a broken page; a bfcache restore can hand
// back a frozen pre-navigation snapshot, so each case forces a real remount
// (page.reload()) after goBack/goForward, mirroring the admin "browser back
// after a successful approve" test's own bfcache handling in
// naive-misuse-shared.spec.ts.
test.describe('hardware back button', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
  })

  test('pressing back with the request form open returns to the picker, not a broken page (F-5)', async ({
    page,
  }) => {
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
    await page.route('**/api/v1/story-requests?profile_id=p1', (route) =>
      route.fulfill({ json: { requests: [] } })
    )

    await page.goto('/kids')
    await page.getByRole('link', { name: 'Remy' }).click()
    await expect(page).toHaveURL('/library/p1')
    await page.getByRole('button', { name: 'Request a story' }).click()
    await page.getByLabel('What should your story be about?').fill('A brave fox')

    await page.goBack()
    await expect(page).toHaveURL(/\/kids$/)
    await page.reload()

    // Graceful: the form's open client state is simply discarded by the
    // navigation, not a broken or half-rendered page; the picker still works.
    await expect(page.getByRole('link', { name: 'Remy' })).toBeVisible()

    // Forward again remounts a fresh library page: no leftover open form or
    // stale error survives the round trip.
    await page.goForward()
    await expect(page).toHaveURL('/library/p1')
    await page.reload()
    await expect(page.getByRole('button', { name: 'Request a story' })).toBeVisible()
    await expect(page.getByLabel('What should your story be about?')).toHaveCount(0)
  })

  test('pressing back mid-reading returns to the library, not a stuck reader (F-6a)', async ({
    page,
  }) => {
    const stories = {
      stories: [
        {
          id: 's_lantern_cave',
          title: 'The Lantern Cave',
          version: 1,
          age_band: '6-8',
          tier: 1,
          reading_level_target: 2,
          node_count: 6,
          rating: null,
          progress: null,
        },
      ],
    }
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))
    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ status: 404, json: { error: 'not found' } })
      }
      return route.fulfill({
        status: 200,
        json: {
          current_node: 'n_entrance',
          var_state: {},
          path: ['n_entrance'],
          visit_set: ['n_entrance'],
          version: 1,
          state_revision: 1,
          save_slots: {},
        },
      })
    })

    await page.goto('/kids')
    await page.getByRole('link', { name: 'Remy' }).click()
    await expect(page).toHaveURL('/library/p1')
    await page.getByRole('link', { name: /the lantern cave/i }).click()
    await expect(page).toHaveURL(/\/read\/p1\/s_lantern_cave\/1$/)
    await expect(page.getByTestId('reader')).toBeVisible()
    await page.getByTestId('choice-c_take_lantern').click()
    await expect(page.getByTestId('passage-body')).toContainText('The cave splits.')

    await page.goBack()
    await expect(page).toHaveURL(/\/library\/p1$/)
    await page.reload()

    // Graceful recovery: no dead end, and never the "Hmm, that page got
    // stuck." error screen; the browser's own back lands on the library.
    await expect(page.locator('.reader-error')).toHaveCount(0)
    await expect(page.getByRole('link', { name: /the lantern cave/i })).toBeVisible()

    // Forward again reopens the reader cleanly, not stuck on the error state.
    await page.goForward()
    await expect(page).toHaveURL(/\/read\/p1\/s_lantern_cave\/1$/)
    await page.reload()
    await expect(page.getByTestId('reader')).toBeVisible()
    await expect(page.locator('.reader-error')).toHaveCount(0)
  })
})

test.describe('refresh mid-reader', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    // ADR-014: an authorized device (grant present) so /read/* renders.
    await seedDeviceGrant(context)
  })

  test('a clean refresh (not the offline/409 case) does not lose reading position', async ({
    page,
  }) => {
    const READER_PATH = '/read/child-fox/s_lantern_cave/1'
    let currentNode = 'n_entrance'

    await page.route('**/api/v1/storybooks/**', (route) => route.fulfill({ json: lantern }))
    await page.route('**/api/v1/reading-state/**', (route) => {
      if (route.request().method() === 'GET') {
        if (currentNode === 'n_entrance') {
          return route.fulfill({ status: 404, json: { error: 'not found' } })
        }
        return route.fulfill({
          status: 200,
          json: {
            current_node: currentNode,
            var_state: { has_lantern: true },
            path: ['n_entrance', currentNode],
            visit_set: ['n_entrance', currentNode],
            version: 1,
            state_revision: 2,
            save_slots: {},
          },
        })
      }
      const body = route.request().postDataJSON() as { current_node: string }
      currentNode = body.current_node
      return route.fulfill({
        status: 200,
        json: {
          current_node: currentNode,
          var_state: { has_lantern: true },
          path: ['n_entrance', currentNode],
          visit_set: ['n_entrance', currentNode],
          version: 1,
          state_revision: 2,
          save_slots: {},
        },
      })
    })

    await page.goto(READER_PATH)
    await expect(page.getByTestId('reader')).toBeVisible()

    // Deterministically wait for the reading-state save to land before
    // refreshing, rather than waitForLoadState('networkidle') (which Playwright
    // discourages and which can resolve before a debounced save fires).
    // readerApi persists via PUT /v1/reading-state/... (see readerApi.ts).
    // Register the wait before the click so it catches the save as it happens.
    const savePersisted = page.waitForResponse(
      (res) => res.url().includes('/api/v1/reading-state/') && res.request().method() === 'PUT'
    )
    await page.getByTestId('choice-c_take_lantern').click()
    await savePersisted
    await page.reload()

    await expect(page.getByTestId('reader')).toBeVisible()
    // The gated dark-passage choice requires has_lantern: true, which only
    // holds if the refreshed reader resumed past the entrance, not reset to it.
    await expect(page.getByTestId('choice-c_dark_passage')).toBeVisible()
  })
})

test.describe('fresh device, never authorized (ADR-014)', () => {
  // A device that has never been authorized has no device grant, so
  // DeviceAuthorizedRoute intercepts the whole kid surface BEFORE any page
  // mounts or fetches, and routes to guardian login carrying the
  // authorize-device intent. The kid-safe "ask a grown-up" in-page gate
  // (covered by the sibling block below) is one layer down and never reached
  // here: this is the new, correct handoff for an unauthorized device.
  // Deliberately no auth_token and no device grant seeded.

  test('the kid picker redirects to guardian login with the authorize-device intent', async ({
    page,
  }) => {
    await page.goto('/kids')

    await expect(page).toHaveURL('/guardian/login?intent=authorize-device')
  })

  test('a kid deep link into the library also redirects to authorize this device', async ({
    page,
  }) => {
    await page.goto('/library/p1')

    await expect(page).toHaveURL('/guardian/login?intent=authorize-device')
  })
})

test.describe('authorized device, session no longer valid (ADR-014)', () => {
  // This is issue #196/#137 F1's naive-UX scenario as it now presents: the
  // device WAS authorized (a grant is present and not yet expired per the
  // client clock), so DeviceAuthorizedRoute lets the kid surface mount, but
  // the server rejects the grant's bearer (revoked, or its own exp reached) so
  // every profiles/library fetch comes back 401. The kid-safe in-page
  // "ask a grown-up" gate must render instead of a scary retryable error.
  test.beforeEach(async ({ context }) => {
    await seedDeviceGrant(context)
  })

  test('the profile picker shows an ask-a-grown-up gate, not a retryable error', async ({
    page,
  }) => {
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
    )

    await page.goto('/kids')

    await expect(page.getByText('Ask a grown-up to help')).toBeVisible()
    await expect(page.getByRole('link', { name: 'I am a grown-up' })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
    await expect(page.getByText(/hit a snag/i)).toHaveCount(0)
    await expect(page.getByRole('button', { name: /try again/i })).toHaveCount(0)
  })

  test('the library shows an ask-a-grown-up gate, not a retryable error', async ({ page }) => {
    // KidNav (mounted alongside LibraryPage) fetches profiles too, on the same
    // rejected request; it swallows that failure into a generic "My books"
    // label (see KidNav.tsx), so only the page-level gate below is expected
    // to render even though both routes 401.
    await page.route('**/api/v1/profiles', (route) =>
      route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
    )
    await page.route('**/api/v1/library*', (route) =>
      route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
    )

    await page.goto('/library/p1')

    await expect(page.getByText('Time to find your grown-up')).toBeVisible()
    await expect(page.getByRole('link', { name: /Who's reading/i })).toHaveAttribute(
      'href',
      '/kids'
    )
    await expect(page.getByRole('link', { name: 'I am a grown-up' })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
    await expect(page.getByText(/lost the bookshelf/i)).toHaveCount(0)
    await expect(page.getByRole('button', { name: /try again/i })).toHaveCount(0)
  })
})

test.describe('rating twice', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'child-fox')
    })
    // ADR-014: an authorized device (grant present) so the kid surface renders.
    await seedDeviceGrant(context)
    await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: PROFILES }))
  })

  test('rating a story twice keeps only the latest value', async ({ page }) => {
    const stories = {
      stories: [
        {
          id: 's3',
          title: 'Acorn Detectives',
          version: 1,
          age_band: '6-8',
          tier: 1,
          reading_level_target: 2,
          node_count: 8,
          rating: null,
          progress: null,
        },
      ],
    }
    await page.route('**/api/v1/library*', (route) => route.fulfill({ json: stories }))

    const ratingBodies: unknown[] = []
    await page.route('**/api/v1/ratings', (route) => {
      ratingBodies.push(route.request().postDataJSON())
      return route.fulfill({
        json: {
          child_profile_id: 'p1',
          storybook_id: 's3',
          value: 3,
          rated_at: '2026-07-05T00:00:00Z',
          updated_at: '2026-07-05T00:00:00Z',
        },
      })
    })

    await page.goto('/library/p1')
    const shelf = page.getByRole('region', { name: 'More to Explore' })
    await shelf.getByRole('button', { name: 'Rate 5 stars' }).click()
    await shelf.getByRole('button', { name: 'Rate 3 stars' }).click()

    expect(ratingBodies).toEqual([
      { profile_id: 'p1', storybook_id: 's3', value: 5 },
      { profile_id: 'p1', storybook_id: 's3', value: 3 },
    ])
    await expect(shelf.getByRole('button', { name: 'Rate 3 stars' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    await expect(shelf.getByRole('button', { name: 'Rate 5 stars' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })
})
