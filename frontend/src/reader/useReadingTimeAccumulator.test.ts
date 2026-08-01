import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mocked at the module boundary rather than exercised against real (fake)
// IndexedDB: this hook's own job is orchestration (when to accrue, when to
// flush) under fake timers, which is a poor mix with fake-indexeddb's own
// async event scheduling. offline/readingTimeSync.test.ts covers the real
// accrual/flush math against real (fake) IndexedDB, with real timers.
vi.mock('../offline/readingTimeSync', () => ({
  accrueReadingTime: vi.fn().mockResolvedValue(undefined),
  flushAllReadingTime: vi.fn().mockResolvedValue(undefined),
}))

import { accrueReadingTime, flushAllReadingTime } from '../offline/readingTimeSync'
import {
  FLUSH_INTERVAL_MS,
  IDLE_WINDOW_MS,
  readerLocalDate,
  TICK_INTERVAL_MS,
  useReadingTimeAccumulator,
} from './useReadingTimeAccumulator'

const PROFILE_ID = 'profile-1'
const accrueMock = vi.mocked(accrueReadingTime)
const flushMock = vi.mocked(flushAllReadingTime)
// A dummy api object: attemptFlush no-ops entirely when `api` is undefined
// (see the hook's own doc), so any test asserting on flushAllReadingTime
// calls must pass a defined (even if unused) api port.
const DUMMY_API = { flush: vi.fn() }

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  accrueMock.mockClear()
  flushMock.mockClear()
  setVisibility('visible')
})

afterEach(() => {
  vi.useRealTimers()
})

describe('readerLocalDate', () => {
  it('formats the injected clock as YYYY-MM-DD in local time', () => {
    const date = new Date(2026, 0, 5, 23, 59) // Jan 5, local time
    expect(readerLocalDate(date)).toBe('2026-01-05')
  })

  it('zero-pads single-digit month and day', () => {
    const date = new Date(2026, 2, 4)
    expect(readerLocalDate(date)).toBe('2026-03-04')
  })
})

describe('useReadingTimeAccumulator', () => {
  it("accrues TICK_INTERVAL_MS worth of seconds into today's bucket on each active tick", () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock })
    )
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS)
    })
    expect(accrueMock).toHaveBeenCalledWith(PROFILE_ID, '2026-01-01', TICK_INTERVAL_MS / 1000)
    unmount()
  })

  it('does not accrue while paused', () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock, paused: true })
    )
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS * 5)
    })
    expect(accrueMock).not.toHaveBeenCalled()
    unmount()
  })

  it('stops accruing once the idle window elapses with no interaction', () => {
    let elapsedMs = 0
    const start = new Date(2026, 0, 1, 10, 0, 0).getTime()
    const clock = () => new Date(start + elapsedMs)
    const { unmount } = renderHook(() => useReadingTimeAccumulator({ profileId: PROFILE_ID, now: clock }))

    const ticksToIdle = Math.ceil(IDLE_WINDOW_MS / TICK_INTERVAL_MS) + 2
    for (let i = 0; i < ticksToIdle; i += 1) {
      elapsedMs += TICK_INTERVAL_MS
      act(() => {
        vi.advanceTimersByTime(TICK_INTERVAL_MS)
      })
    }
    // Fewer accrual calls than total ticks: some ticks landed after the idle
    // cutoff and were skipped.
    expect(accrueMock.mock.calls.length).toBeLessThan(ticksToIdle)
    expect(accrueMock.mock.calls.length).toBeGreaterThan(0)
    unmount()
  })

  it('keeps accruing across the idle window when read-aloud is playing', () => {
    let elapsedMs = 0
    const start = new Date(2026, 0, 1, 10, 0, 0).getTime()
    const clock = () => new Date(start + elapsedMs)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: clock, isReadAloudPlaying: true })
    )
    const ticksToIdle = Math.ceil(IDLE_WINDOW_MS / TICK_INTERVAL_MS) + 2
    for (let i = 0; i < ticksToIdle; i += 1) {
      elapsedMs += TICK_INTERVAL_MS
      act(() => {
        vi.advanceTimersByTime(TICK_INTERVAL_MS)
      })
    }
    // Every tick credited: read-aloud playing counts as active with no taps.
    expect(accrueMock.mock.calls.length).toBe(ticksToIdle)
    unmount()
  })

  it('recordInteraction resets the idle window', () => {
    let elapsedMs = 0
    const start = new Date(2026, 0, 1, 10, 0, 0).getTime()
    const clock = () => new Date(start + elapsedMs)
    const { result, unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: clock })
    )
    const almostIdleTicks = Math.floor(IDLE_WINDOW_MS / TICK_INTERVAL_MS) - 1
    for (let i = 0; i < almostIdleTicks; i += 1) {
      elapsedMs += TICK_INTERVAL_MS
      act(() => {
        vi.advanceTimersByTime(TICK_INTERVAL_MS)
      })
    }
    act(() => {
      result.current.recordInteraction()
    })
    accrueMock.mockClear()
    // Advance past what WOULD have been the idle cutoff had interaction not
    // reset the window.
    for (let i = 0; i < almostIdleTicks; i += 1) {
      elapsedMs += TICK_INTERVAL_MS
      act(() => {
        vi.advanceTimersByTime(TICK_INTERVAL_MS)
      })
    }
    // Every tick in this second loop still credited: the interaction reset
    // the idle window right before it.
    expect(accrueMock.mock.calls.length).toBe(almostIdleTicks)
    unmount()
  })

  it('pauses immediately on visibilitychange to hidden (no accrual while hidden) and flushes', () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock, api: DUMMY_API })
    )
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS)
    })
    expect(accrueMock).toHaveBeenCalledTimes(1)

    setVisibility('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(flushMock).toHaveBeenCalled()

    accrueMock.mockClear()
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS * 3)
    })
    expect(accrueMock).not.toHaveBeenCalled()
    unmount()
  })

  it('flushes once on unmount', () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock, api: DUMMY_API })
    )
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS)
    })
    flushMock.mockClear()
    act(() => {
      unmount()
    })
    expect(flushMock).toHaveBeenCalledTimes(1)
  })

  it('flushes opportunistically at most every FLUSH_INTERVAL_MS while active', () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock, api: DUMMY_API })
    )
    const ticksPerFlushWindow = FLUSH_INTERVAL_MS / TICK_INTERVAL_MS
    act(() => {
      vi.advanceTimersByTime(TICK_INTERVAL_MS * ticksPerFlushWindow)
    })
    expect(flushMock.mock.calls.length).toBeGreaterThanOrEqual(1)
    unmount()
  })

  it('never accrues or flushes when never mounted with an api (accrual still local-only, no throw)', () => {
    const clock = new Date(2026, 0, 1, 10, 0, 0)
    const { unmount } = renderHook(() =>
      useReadingTimeAccumulator({ profileId: PROFILE_ID, now: () => clock })
    )
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(TICK_INTERVAL_MS)
      })
    }).not.toThrow()
    unmount()
  })
})
