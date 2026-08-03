import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { EMPTY_PROGRESS, makeProgressApi, type ProgressSummary } from './progressApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

const FULL_RESPONSE: ProgressSummary = {
  badges: [
    { id: 'first_ending', name: 'First Ending', description: 'You found one!', earned_at: 't' },
  ],
  books: [
    {
      storybook_id: 's1',
      title: 'Story One',
      endings_found: 1,
      total_endings: 3,
      finished: true,
      every_path_walked: false,
      found_endings: [{ ending_id: 'e1', title: 'A Happy End', valence: 'positive' }],
    },
  ],
  totals: { books_finished: 1, endings_found: 1 },
  days_read_this_week: 2,
  lifetime_days_read: 10,
  settings: {
    ring_enabled: true,
    ring_goal_days: 3,
    badges_enabled: true,
    time_capture_paused: false,
  },
}

describe('makeProgressApi', () => {
  it('fetches and returns the full progress payload as-is', async () => {
    const get = vi.fn().mockResolvedValue({ data: FULL_RESPONSE })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(get).toHaveBeenCalledWith('/v1/me/progress')
    expect(result).toEqual(FULL_RESPONSE)
  })

  it('tolerates a malformed response by degrading field-by-field to the empty shape', async () => {
    const get = vi.fn().mockResolvedValue({ data: {} })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result).toEqual(EMPTY_PROGRESS)
  })

  it('tolerates a response missing only some fields', async () => {
    const get = vi.fn().mockResolvedValue({
      data: { badges: FULL_RESPONSE.badges, days_read_this_week: 4 },
    })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result.badges).toEqual(FULL_RESPONSE.badges)
    expect(result.days_read_this_week).toBe(4)
    expect(result.books).toEqual([])
    expect(result.settings).toEqual(EMPTY_PROGRESS.settings)
  })

  /**
   * The case above omits `settings` ENTIRELY, which the old
   * `data.settings ?? FALLBACK_SETTINGS` already handled. The gap was a
   * settings object that is present but incomplete: it passed through
   * wholesale, so `ring_goal_days` reached WeeklyRing as `undefined` and
   * `Math.max(1, undefined)` rendered `strokeDashoffset={NaN}` under an
   * aria-label reading "out of a goal of NaN".
   */
  it('fills in a settings object that is present but incomplete', async () => {
    const get = vi.fn().mockResolvedValue({ data: { settings: { ring_enabled: true } } })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result.settings.ring_enabled).toBe(true)
    expect(result.settings.ring_goal_days).toBe(3)
    expect(Number.isFinite(result.settings.ring_goal_days)).toBe(true)
    expect(result.settings.badges_enabled).toBe(false)
    expect(result.settings.time_capture_paused).toBe(false)
  })

  it('rejects a non-numeric ring goal rather than passing it through', async () => {
    const get = vi.fn().mockResolvedValue({
      data: { settings: { ring_enabled: true, ring_goal_days: 'four', badges_enabled: true } },
    })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result.settings.ring_goal_days).toBe(3)
    expect(result.settings.badges_enabled).toBe(true)
  })

  it('fails the two toggles CLOSED on a non-boolean, never open', async () => {
    // Direction matters: a truthy-but-not-true value must not switch a
    // 3-5 reader's ring on. Hiding a ring that should show costs a
    // decoration; showing one that should not is a visible K14 violation.
    const get = vi.fn().mockResolvedValue({
      data: { settings: { ring_enabled: 'yes', badges_enabled: 1 } },
    })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result.settings.ring_enabled).toBe(false)
    expect(result.settings.badges_enabled).toBe(false)
  })

  it('fills in a totals object that is present but incomplete', async () => {
    const get = vi.fn().mockResolvedValue({ data: { totals: { books_finished: 2 } } })
    const api = makeProgressApi(fakeAxios({ get }))

    const result = await api.getProgress()

    expect(result.totals).toEqual({ books_finished: 2, endings_found: 0 })
  })
})

/**
 * Concurrent-mount coalescing (design review 4.3).
 *
 * A single kid route mounts two or three independent consumers of this
 * endpoint at once (KidNav's ring and badge button, plus LibraryPage or
 * ReaderPage), and each holds its own axios instance because `useApi()`
 * memoises per component. The result was the same GET issued two or three
 * times within milliseconds on a tablet.
 */
describe('makeProgressApi in-flight coalescing', () => {
  /** A `get` that resolves only when the returned `release` is called, so a
   * test can hold several callers inside the in-flight window deliberately
   * rather than racing the microtask queue and hoping. */
  function deferredGet(data: Partial<ProgressSummary> = {}) {
    const releases: (() => void)[] = []
    const get = vi.fn().mockImplementation(() => {
      // Each request answers with its own 1-based call number in
      // days_read_this_week, so a test can prove WHICH request a caller was
      // served, not merely how many were issued.
      const nth = releases.length + 1
      return new Promise((resolve) => {
        releases.push(() => {
          resolve({ data: { days_read_this_week: nth, ...data } })
        })
      })
    })
    return {
      get,
      releaseAll: () => {
        for (const release of releases) release()
      },
    }
  }

  it('serves concurrent callers on the same profile from one request', async () => {
    const { get, releaseAll } = deferredGet({ days_read_this_week: 4 })
    // Two SEPARATE adapters over two separate axios instances, which is the
    // real arrangement: a per-adapter cache would dedupe nothing here.
    const nav = makeProgressApi(fakeAxios({ get }), 'kid-1')
    const library = makeProgressApi(fakeAxios({ get }), 'kid-1')

    const both = Promise.all([nav.getProgress(), library.getProgress()])
    releaseAll()
    const [a, b] = await both

    expect(get).toHaveBeenCalledTimes(1)
    expect(a.days_read_this_week).toBe(4)
    expect(b.days_read_this_week).toBe(4)
  })

  it('never coalesces across profiles', async () => {
    // #CRITICAL: security: `/v1/me/progress` resolves from the child session
    // token, so joining a request issued under another child's session would
    // hand one reader another reader's progress. Two profiles must always
    // mean two requests, no matter how tightly the mounts overlap.
    const { get, releaseAll } = deferredGet()
    const first = makeProgressApi(fakeAxios({ get }), 'kid-1')
    const second = makeProgressApi(fakeAxios({ get }), 'kid-2')

    const both = Promise.all([first.getProgress(), second.getProgress()])
    releaseAll()
    await both

    expect(get).toHaveBeenCalledTimes(2)
  })

  it('a sequential second call is a fresh request, not the settled first one', async () => {
    // ReaderPage's badge toast diffs a pre-completion snapshot against a
    // post-completion read. If the second call could be served from the
    // first, it would compare a value against itself and no badge would ever
    // toast. The deletion runs inside the promise the caller receives, so a
    // consumer continuation is always after the entry is gone.
    const get = vi
      .fn()
      .mockResolvedValueOnce({ data: { badges: [] } })
      .mockResolvedValueOnce({
        data: { badges: [{ id: 'b1', name: 'B', description: 'd', earned_at: 't' }] },
      })
    const api = makeProgressApi(fakeAxios({ get }), 'kid-1')

    const before = await api.getProgress()
    const after = await api.getProgress()

    expect(get).toHaveBeenCalledTimes(2)
    expect(before.badges).toHaveLength(0)
    expect(after.badges).toHaveLength(1)
  })

  it('clears the in-flight entry when the request rejects', async () => {
    // A failure that left the entry behind would wedge the endpoint for the
    // rest of the session: every later mount would join a permanently
    // rejected promise and the ring would never recover without a reload.
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: { days_read_this_week: 2 } })
    const api = makeProgressApi(fakeAxios({ get }), 'kid-1')

    await expect(api.getProgress()).rejects.toThrow('offline')
    const recovered = await api.getProgress()

    expect(recovered.days_read_this_week).toBe(2)
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('a fresh read never joins one in flight, and never becomes one either', async () => {
    // Both halves matter. Joining would hand the badge diff a snapshot taken
    // before the completion POST existed; BECOMING the shared entry would hand
    // the next mount a read that was deliberately taken out of band.
    const { get, releaseAll } = deferredGet()
    const api = makeProgressApi(fakeAxios({ get }), 'kid-1')

    const mount = api.getProgress()
    const fresh = api.getProgress({ fresh: true })
    const laterMount = api.getProgress()
    releaseAll()
    const [mounted, freshed, later] = await Promise.all([mount, fresh, laterMount])

    // mount + fresh: the third call rejoined the first, not the fresh one.
    expect(get).toHaveBeenCalledTimes(2)
    // Counting calls alone cannot tell "laterMount joined the mount" from
    // "laterMount joined the fresh read", since both are two requests. The
    // per-request payload can: `later` must carry the FIRST request's body.
    expect(mounted.days_read_this_week).toBe(1)
    expect(freshed.days_read_this_week).toBe(2)
    expect(later.days_read_this_week).toBe(1)
  })

  it('does not coalesce at all when no profile id is given', async () => {
    // The documented opt-out. Every existing test in this file constructs the
    // adapter without a profile, so this pins that they still measure one
    // request per call rather than silently sharing one.
    const { get, releaseAll } = deferredGet()
    const api = makeProgressApi(fakeAxios({ get }))

    const both = Promise.all([api.getProgress(), api.getProgress()])
    releaseAll()
    await both

    expect(get).toHaveBeenCalledTimes(2)
  })
})
