import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle, isBadgeSeen } from '../offline/db'
import type { PutResponse, SyncApi } from '../offline/sync'
import type { Storybook } from '../player/types'
import type { ProgressSummary } from '../kid/progressApi'
import { ReaderPage } from './ReaderPage'

// W3.2: this file isolates the badge-unlock-toast pre/post comparison, which
// needs a controllable `/v1/me/progress` response sequence -- mocking the
// shared axios instance ReaderPage now builds internally (useApi()), rather
// than the many other ReaderPage.test.tsx cases that never touch this port.
// The real useApi() memoizes its returned AxiosInstance (useMemo internally),
// so a stable object here matters: a fresh object per render would break
// every useMemo/useEffect in ReaderPage.tsx keyed on its identity (e.g. the
// settings-fetch effect re-firing on every render instead of once on mount).
const getMock = vi.fn()
const fakeAxiosInstance = { get: getMock }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeAxiosInstance,
}))

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

function okApi(): SyncApi {
  let rev = 0
  return {
    putReadingState: (_p, _s, body) =>
      Promise.resolve<PutResponse>({ status: 200, row: { ...body, state_revision: ++rev } }),
  }
}

function progressWithBadges(badgeIds: string[], badgesEnabled = true): ProgressSummary {
  return {
    badges: badgeIds.map((id) => ({ id, name: id, description: `earned ${id}`, earned_at: 't' })),
    books: [],
    totals: { books_finished: 0, endings_found: 0 },
    days_read_this_week: 0,
    lifetime_days_read: 0,
    settings: {
      ring_enabled: true,
      ring_goal_days: 3,
      badges_enabled: badgesEnabled,
      time_capture_paused: false,
    },
  }
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  vi.stubGlobal('scrollTo', vi.fn())
  getMock.mockReset()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

async function reachEnding(profileId: string) {
  render(
    <MemoryRouter>
      <ReaderPage
        api={okApi()}
        fetchStory={() => Promise.resolve(lantern)}
        recordCompletion={() => Promise.resolve({ is_new: true, found: 1, total: 4 })}
        profileId={profileId}
        storybookId="s_lantern_cave"
        version={1}
      />
    </MemoryRouter>
  )
  fireEvent.click(await screen.findByTestId('choice-c_take_lantern'))
  fireEvent.click(await screen.findByTestId('choice-c_dark_passage'))
  await screen.findByTestId('ending-screen')
}

describe('ReaderPage badge-unlock toast (W3.2)', () => {
  it('shows a toast for a badge present after the completion but not before', async () => {
    getMock.mockImplementation((url: string) => {
      if (url === '/v1/me/progress') {
        // Call 1 is the mount-time settings fetch; call 2 is handleComplete's
        // "badgesBefore" snapshot (fired the instant the ending is reached,
        // before the completion POST resolves). Both must still read "no
        // badge yet" for the diff below to see it as newly earned; call 3+
        // (post-completion) carries the new badge.
        const calls = getMock.mock.calls.filter((c) => c[0] === '/v1/me/progress').length
        return Promise.resolve({
          data: calls <= 2 ? progressWithBadges([]) : progressWithBadges(['first_ending']),
        })
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    await reachEnding('p_badge_1')

    const toast = await screen.findByTestId('badge-unlock-toast')
    expect(toast).toHaveTextContent('first_ending')
    expect(await isBadgeSeen('p_badge_1', 'first_ending')).toBe(true)
  })

  it('does not toast a badge already marked seen on this device', async () => {
    getMock.mockResolvedValue({ data: progressWithBadges(['first_ending']) })
    // Pre-mark as seen, simulating an earlier session on this device.
    const { markBadgeSeen } = await import('../offline/db')
    await markBadgeSeen('p_badge_2', 'first_ending')

    await reachEnding('p_badge_2')

    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(screen.queryByTestId('badge-unlock-toast')).toBeNull()
  })

  it('suppresses the toast when badges_enabled is off, even if the mount-time settings fetch never resolved', async () => {
    // The G19 gate's fail-open window: `badgesEnabledRef` defaults to true and
    // is read before any await, so a child who reaches an ending before the
    // mount fetch resolves would pass it. Here that fetch NEVER resolves, so
    // only the post-completion re-check can suppress the toast.
    getMock.mockImplementation((url: string) => {
      if (url !== '/v1/me/progress') return Promise.reject(new Error(`unexpected GET ${url}`))
      const calls = getMock.mock.calls.filter((c) => c[0] === '/v1/me/progress').length
      if (calls === 1) return new Promise(() => {}) // mount fetch: still in flight
      if (calls === 2) return Promise.resolve({ data: progressWithBadges([], false) })
      return Promise.resolve({ data: progressWithBadges(['first_ending'], false) })
    })

    await reachEnding('p_badge_off')

    await waitFor(() => expect(getMock.mock.calls.length).toBeGreaterThanOrEqual(3))
    expect(screen.queryByTestId('badge-unlock-toast')).toBeNull()
    // The badge must NOT be consumed: a paused celebration is one the guardian
    // can turn back on, and marking it seen here would burn it permanently.
    expect(await isBadgeSeen('p_badge_off', 'first_ending')).toBe(false)
  })

  it('does not toast when the badge set is unchanged by this completion', async () => {
    getMock.mockResolvedValue({ data: progressWithBadges(['first_ending']) })
    const { markBadgeSeen } = await import('../offline/db')
    // Not pre-marked seen, but before/after are identical (no new badge).
    await reachEnding('p_badge_3')
    await markBadgeSeen('p_badge_3', 'never-shown-marker')

    await waitFor(() => expect(getMock).toHaveBeenCalled())
    // before === after (both ['first_ending']) so nothing is "new"; no toast.
    expect(screen.queryByTestId('badge-unlock-toast')).toBeNull()
  })
})
