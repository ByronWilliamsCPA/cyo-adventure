import { expect, test } from '@playwright/test'

import type { DeviceGrant } from '../src/auth/deviceGrant'

import { authorizeDevice, BACKEND, requireBackend, revokeDevice } from './real-stack'

/**
 * Real-API K7 kid read-aloud path: Reader.tsx's read-aloud toggle
 * (ReaderChrome's `reader-tts-toggle` button) is built on the browser's
 * native Web Speech API (useReadAloud.ts), not a backend call; read-aloud
 * itself has no server-side effect to persist or re-fetch. What IS real here
 * is the gate that decides whether the toggle appears at all: the profile's
 * `tts_enabled` flag (db/models.py's ChildProfile.tts_enabled, defaulting to
 * false) is set through a real guardian `PATCH /api/v1/profiles/{id}` before
 * this test, then read back through the real `GET /api/v1/profiles`
 * ProfilePickerPage.tsx fires on every load; the picker caches the value
 * (kid/readAloudPreference.ts) and threads it into Reader as the
 * `ttsEnabled` prop (ReaderRoute.tsx). This spec proves that whole real round
 * trip, then asserts the client-only speak/stop UI contract on top of it.
 *
 * #ASSUME: browser-compat: read-aloud is a UI-contract assertion, not a
 * persisted-state one: `window.speechSynthesis` and
 * `SpeechSynthesisUtterance` are present in headless Chromium (verified
 * directly against this repo's Playwright Chromium build before writing this
 * spec), so useReadAloud's `available` gate passes here. This spec never
 * waits for an utterance's onend/onerror callback, since those depend on an
 * actual TTS voice backend a CI runner may not have; it only asserts the
 * toggle's own state, which useReadAloud sets synchronously inside
 * speak()/stop(), before ever calling into speechSynthesis.
 * #VERIFY: a future CI image without this API would make `available` false
 * and the toggle would never render at all (ReaderChrome omits it entirely,
 * not a disabled button; see the `readAloud.available` check in Reader.tsx),
 * turning this spec's first toggle-visibility assertion red rather than
 * passing on a false premise.
 *
 * #ASSUME: timing dependencies: headless Chromium's speechSynthesis backend
 * can finish a short real utterance near-instantly, firing `onend` and
 * flipping useReadAloud's `speaking` state back to false (see
 * useReadAloud.ts's `last.onend = () => setSpeaking(false)`) before this
 * spec's own click on "Stop reading aloud" runs, a real flake caught by
 * running this suite three times in a row while writing it. `speak()` and
 * `stop()` both set `speaking` synchronously and neither reads from
 * `onend`/`onerror` to decide when the user's own click should take effect,
 * so stubbing `window.speechSynthesis.speak` to never auto-complete removes
 * only the unobserved, out-of-scope real-audio timing above, not any of the
 * app code under test (useReadAloud, the toggle, ReaderChrome all still run
 * for real); it turns "does the click land before or after a browser-timed
 * onend" from a real race into a fact this spec controls.
 * #VERIFY: a regression that made `stop()` depend on `onend` firing (instead
 * of setting `speaking` directly) would hang forever against this stub,
 * failing on timeout rather than passing on a false premise.
 *
 * #EDGE: data-integrity: "The Tide Pool Mystery" is shared with
 * kid-reads.spec.ts, kid-flag-real.spec.ts, and kid-go-back-real.spec.ts (see
 * kid-go-back-real.spec.ts's file header for why this story tolerates shared
 * reading_state). This spec never clicks a choice, so it never changes the
 * row's position for whichever spec reads this story next.
 */

const DEV_GUARDIAN_BEARER = 'dev-guardian'

interface ProfileRow {
  id: string
  display_name: string
}

async function findDevReaderProfileId(): Promise<string> {
  const res = await fetch(`${BACKEND}/api/v1/profiles`, {
    headers: { Authorization: `Bearer ${DEV_GUARDIAN_BEARER}` },
    signal: AbortSignal.timeout(5000),
  })
  expect(res.ok, `GET /profiles failed (HTTP ${res.status})`).toBe(true)
  const { profiles } = (await res.json()) as { profiles: ProfileRow[] }
  const row = profiles.find((p) => p.display_name === 'Dev Reader')
  expect(row, 'no profile named "Dev Reader" found via GET /profiles').toBeTruthy()
  return (row as ProfileRow).id
}

async function setTtsEnabled(profileId: string, ttsEnabled: boolean): Promise<void> {
  const res = await fetch(`${BACKEND}/api/v1/profiles/${profileId}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${DEV_GUARDIAN_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ tts_enabled: ttsEnabled }),
    signal: AbortSignal.timeout(5000),
  })
  expect(res.ok, `PATCH /profiles/${profileId} failed (HTTP ${res.status})`).toBe(true)
}

let deviceGrant: DeviceGrant | null = null
let devReaderProfileId: string | null = null

test.beforeEach(async ({ context }) => {
  await requireBackend()
  devReaderProfileId = await findDevReaderProfileId()
  // Real guardian action (K7): turn the profile's read-aloud flag on before
  // the kid picker is ever loaded, so ProfilePickerPage's GET /v1/profiles
  // picks up the real value at pick time.
  await setTtsEnabled(devReaderProfileId, true)
  deviceGrant = await authorizeDevice(context)
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'dev-child')
  })
  // See file header #ASSUME: timing dependencies. Only the real-audio side
  // effect is stubbed; useReadAloud's speak()/stop() state machine, and every
  // component under test, run unmodified.
  await context.addInitScript(() => {
    window.speechSynthesis.speak = () => {}
  })
})

test.afterEach(async () => {
  // Restore the profile's default so a reused dev stack does not leave K7
  // permanently on for the seeded profile; best-effort, mirroring
  // revokeDevice's cleanup convention.
  if (devReaderProfileId) {
    try {
      await setTtsEnabled(devReaderProfileId, false)
    } catch (err) {
      console.warn(
        `[kid-read-aloud-real] tts_enabled revert failed for profile ` +
          `${devReaderProfileId}: ${err instanceof Error ? err.message : String(err)}`
      )
    }
    devReaderProfileId = null
  }
  if (deviceGrant) {
    await revokeDevice(deviceGrant)
    deviceGrant = null
  }
})

test('a kid toggles real read-aloud on and off once the real tts_enabled flag is set', async ({
  page,
}) => {
  await page.goto('/kids')
  await page.getByText('Dev Reader').click()
  await expect(page).toHaveURL(/\/library\//)

  await page.getByRole('link', { name: 'The Tide Pool Mystery' }).click()
  await expect(page).toHaveURL(/\/read\//)
  await expect(page.getByTestId('reader')).toBeVisible()

  // The passage actually available for narration is real content: the toggle
  // speaks whatever PassageText currently renders (Reader.tsx's
  // handleToggleSpeak reads node.body directly), not a placeholder.
  const passageText = await page.getByTestId('passage-body').textContent()
  expect(passageText?.trim().length ?? 0).toBeGreaterThan(0)

  const listenToggle = page.getByRole('button', { name: 'Read this page aloud' })
  await expect(listenToggle).toBeVisible()
  await expect(listenToggle).toHaveAttribute('aria-pressed', 'false')

  await listenToggle.click()
  const stopToggle = page.getByRole('button', { name: 'Stop reading aloud' })
  await expect(stopToggle).toBeVisible()
  await expect(stopToggle).toHaveAttribute('aria-pressed', 'true')

  await stopToggle.click()
  const listenToggleAgain = page.getByRole('button', { name: 'Read this page aloud' })
  await expect(listenToggleAgain).toBeVisible()
  await expect(listenToggleAgain).toHaveAttribute('aria-pressed', 'false')
})
