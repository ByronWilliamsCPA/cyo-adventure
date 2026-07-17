import { expect, test } from '@playwright/test'

import { seedDeviceGrant } from './support/auth'
import { loadLanternStory } from './support/fixtures'

/**
 * Coverage for K7 (Phase 4b read-aloud): the reader's speaker toggle only
 * appears for a profile whose `tts_enabled` flag is on, and it is threaded
 * from the picker's `GET /v1/profiles` fetch through the real pick flow
 * (mint a child session, land on the library, open a book), not a direct
 * deep link to `/read/...` (see readAloudPreference.ts's doc comment on why
 * a deep link cannot know the flag). Mocked tier only: no live backend, no
 * live speech output; this checks the UI states the toggle drives, not
 * actual audio.
 */

const lantern = loadLanternStory()

const READER_PROFILE_ID = 'child-listener'

function profilesResponse(ttsEnabled: boolean) {
  return {
    profiles: [
      {
        id: READER_PROFILE_ID,
        display_name: 'Remy',
        age_band: '5-8',
        reading_level_cap: 3,
        avatar: 'fox',
        tts_enabled: ttsEnabled,
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
  }
}

const LIBRARY = {
  stories: [
    {
      id: 's_lantern_cave',
      title: 'The Lantern Cave',
      version: 1,
      age_band: '5-8',
      tier: 1,
      reading_level_target: 2,
      node_count: 6,
      rating: null,
      progress: null,
    },
  ],
}

test.beforeEach(async ({ context, page }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'guardian-jwt')
  })
  // Headless Chromium's real SpeechSynthesis has no voices installed, so a
  // real speak() call fires its error event almost immediately, which makes
  // the "currently speaking" UI state too transient to assert against
  // reliably. A minimal fake speechSynthesis (mirroring the Vitest mock in
  // useReadAloud.test.ts) makes the toggle's speaking state deterministic
  // for this mocked-tier spec, while still exercising the real
  // speechSynthesisSupported() feature check (the properties genuinely
  // exist on `window`, this only replaces what speak()/cancel() do).
  await context.addInitScript(() => {
    class FakeSpeechSynthesisUtterance {
      text: string
      onend: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor(text: string) {
        this.text = text
      }
    }
    const fakeSpeechSynthesis = {
      speak: () => {
        // Deliberately never fires onend/onerror: this spec only asserts UI
        // states the toggle drives (speaking on tap, cancel on
        // toggle-off/navigation), not real audio completion.
      },
      cancel: () => {},
    }
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {
      value: FakeSpeechSynthesisUtterance,
      configurable: true,
    })
    Object.defineProperty(window, 'speechSynthesis', {
      value: fakeSpeechSynthesis,
      configurable: true,
    })
  })
  // ADR-014: the kid surface is gated by DeviceAuthorizedRoute.
  await seedDeviceGrant(context)
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: LIBRARY }))
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
})

async function pickProfileIntoReader(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/child-sessions', (route) =>
    route.fulfill({
      json: {
        token: 'child-token',
        expires_at: '2099-01-01T00:00:00Z',
        profile_id: READER_PROFILE_ID,
      },
    })
  )
  await page.goto('/kids')
  await page.getByRole('link', { name: 'Remy' }).click()
  await expect(page).toHaveURL(`/library/${READER_PROFILE_ID}`)
  await page.getByRole('link', { name: /the lantern cave/i }).click()
  await expect(page).toHaveURL(new RegExp(`/read/${READER_PROFILE_ID}/s_lantern_cave/1$`))
  await expect(page.getByTestId('reader')).toBeVisible()
}

test('shows the read-aloud toggle for a tts_enabled profile picked through the picker, and it starts/stops speaking', async ({
  page,
}) => {
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: profilesResponse(true) }))
  await pickProfileIntoReader(page)

  const toggle = page.getByRole('button', { name: 'Read this page aloud' })
  await expect(toggle).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')

  await toggle.click()
  const stopToggle = page.getByRole('button', { name: 'Stop reading aloud' })
  await expect(stopToggle).toBeVisible()
  await expect(stopToggle).toHaveAttribute('aria-pressed', 'true')

  // Re-tapping while speaking stops it.
  await stopToggle.click()
  await expect(page.getByRole('button', { name: 'Read this page aloud' })).toBeVisible()

  // Navigating (a choice tap) also cancels speech and resets the toggle.
  await page.getByRole('button', { name: 'Read this page aloud' }).click()
  await page.getByTestId('choice-c_take_lantern').click()
  await expect(page.getByRole('button', { name: 'Read this page aloud' })).toBeVisible()
})

test('does not show the read-aloud toggle for a profile with tts_enabled false', async ({
  page,
}) => {
  await page.route('**/api/v1/profiles', (route) =>
    route.fulfill({ json: profilesResponse(false) })
  )
  await pickProfileIntoReader(page)

  await expect(page.getByRole('button', { name: 'Read this page aloud' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Stop reading aloud' })).toHaveCount(0)
})
