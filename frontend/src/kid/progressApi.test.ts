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
