import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CoverApi } from '../guardian/coverApi'
import { useCoverGeneration } from './useCoverGeneration'

function makeCoverApi(overrides: Partial<CoverApi> = {}): CoverApi {
  return {
    generate: vi.fn(),
    status: vi.fn(),
    ...overrides,
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('useCoverGeneration', () => {
  it('does nothing when readyVersion is null (the surface has not loaded yet)', async () => {
    const coverApi = makeCoverApi()
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: null, coverApi, isMountedRef })
    )
    await act(async () => {
      await result.current.generateCover()
    })
    expect(coverApi.generate).not.toHaveBeenCalled()
    expect(result.current.coverStatus).toBe('none')
  })

  it('seeds the cover status from the server once a version is ready', async () => {
    const status = vi.fn().mockResolvedValue({ cover_status: 'ready', cover_url: 'https://x/c.png' })
    const coverApi = makeCoverApi({ status })
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 1, coverApi, isMountedRef })
    )
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(status).toHaveBeenCalledWith('s1', 1)
    expect(result.current.coverStatus).toBe('ready')
  })

  it('keeps the default status when the best-effort seed fetch fails', async () => {
    const status = vi.fn().mockRejectedValue(new Error('network blip'))
    const coverApi = makeCoverApi({ status })
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 1, coverApi, isMountedRef })
    )
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(status).toHaveBeenCalledWith('s1', 1)
    expect(result.current.coverStatus).toBe('none')
  })

  it('polls until the job leaves generating, updating status along the way', async () => {
    vi.useFakeTimers()
    const generate = vi.fn().mockResolvedValue({ cover_status: 'generating', cover_url: null })
    const status = vi.fn().mockResolvedValue({ cover_status: 'ready', cover_url: 'https://x/c.png' })
    const coverApi = makeCoverApi({ generate, status })
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 2, coverApi, isMountedRef })
    )

    await act(async () => {
      const pending = result.current.generateCover()
      await vi.advanceTimersByTimeAsync(2000)
      await pending
    })

    expect(generate).toHaveBeenCalledWith('s1', 2)
    // One seed-effect call on mount plus one poll iteration.
    expect(status).toHaveBeenCalledTimes(2)
    expect(result.current.coverStatus).toBe('ready')
    expect(result.current.coverBusy).toBe(false)
    expect(result.current.coverTimedOut).toBe(false)
  })

  it('surfaces a retry affordance when the poll cap is reached while still generating', async () => {
    vi.useFakeTimers()
    const generate = vi.fn().mockResolvedValue({ cover_status: 'generating', cover_url: null })
    const status = vi.fn().mockResolvedValue({ cover_status: 'generating', cover_url: null })
    const coverApi = makeCoverApi({ generate, status })
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 2, coverApi, isMountedRef })
    )

    await act(async () => {
      const pending = result.current.generateCover()
      for (let i = 0; i < 30; i += 1) {
        await vi.advanceTimersByTimeAsync(2000)
      }
      await pending
    })

    // One seed-effect call on mount plus 30 poll iterations (the poll cap).
    expect(status).toHaveBeenCalledTimes(31)
    expect(result.current.coverTimedOut).toBe(true)
    expect(result.current.coverBusy).toBe(false)
  })

  it('sets a failed status and clears busy when generation errors', async () => {
    const generate = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    const coverApi = makeCoverApi({ generate })
    const isMountedRef = { current: true }
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 2, coverApi, isMountedRef })
    )

    await act(async () => {
      await result.current.generateCover()
    })

    expect(result.current.coverStatus).toBe('failed')
    expect(result.current.coverBusy).toBe(false)
    errorSpy.mockRestore()
  })

  it('never writes state once isMountedRef is flipped false (unmount guard)', async () => {
    const generate = vi.fn().mockResolvedValue({ cover_status: 'generating', cover_url: null })
    const status = vi.fn().mockResolvedValue({ cover_status: 'ready', cover_url: null })
    const coverApi = makeCoverApi({ generate, status })
    const isMountedRef = { current: true }
    const { result } = renderHook(() =>
      useCoverGeneration({ storybookId: 's1', readyVersion: 2, coverApi, isMountedRef })
    )

    isMountedRef.current = false
    await act(async () => {
      await result.current.generateCover()
    })

    // The generate POST still fires, but every setState after it is skipped:
    // status stays at its initial 'none', not the 'generating' the poll saw.
    expect(result.current.coverStatus).toBe('none')
  })
})
