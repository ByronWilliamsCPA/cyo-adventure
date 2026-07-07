import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ReplayOutcome, SyncApi } from '../offline/sync'

const mockReplayQueue = vi.fn<(api: SyncApi) => Promise<ReplayOutcome>>()

vi.mock('../offline/sync', async () => {
  const actual = await vi.importActual<typeof import('../offline/sync')>('../offline/sync')
  return {
    ...actual,
    replayQueue: (api: SyncApi) => mockReplayQueue(api),
  }
})

import { useReplayOnReconnect } from './useReplayOnReconnect'

const emptyOutcome: ReplayOutcome = { replayed: 0, conflicts: [], failed: [] }
const fakeApi: SyncApi = { putReadingState: vi.fn() }

afterEach(() => {
  mockReplayQueue.mockReset()
  vi.restoreAllMocks()
})

describe('useReplayOnReconnect', () => {
  it('flushes once on mount', async () => {
    mockReplayQueue.mockResolvedValue(emptyOutcome)
    const onOutcome = vi.fn()
    renderHook(() => useReplayOnReconnect(fakeApi, onOutcome))

    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(1))
    expect(mockReplayQueue).toHaveBeenCalledWith(fakeApi)
  })

  it('flushes again on a dispatched online event', async () => {
    mockReplayQueue.mockResolvedValue(emptyOutcome)
    const onOutcome = vi.fn()
    renderHook(() => useReplayOnReconnect(fakeApi, onOutcome))
    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(1))

    // The explicit await flushes the microtask queue inside act() so the
    // hook's replayQueue(...).then(...) chain settles before this act call
    // returns, not just the synchronous dispatchEvent.
    await act(async () => {
      window.dispatchEvent(new Event('online'))
      await Promise.resolve()
    })

    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(2))
  })

  it('does not double-fire while a flush is already in flight', async () => {
    let resolveFlush: (outcome: ReplayOutcome) => void = () => {}
    mockReplayQueue.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFlush = resolve
        })
    )
    const onOutcome = vi.fn()
    renderHook(() => useReplayOnReconnect(fakeApi, onOutcome))

    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(1))

    // The mount flush is still in flight; a reconnect event during that window
    // must not start a second concurrent flush. The trailing await flushes
    // the microtask queue inside act() so any (suppressed) second flush
    // attempt would have already settled by the assertion below.
    await act(async () => {
      window.dispatchEvent(new Event('online'))
      await Promise.resolve()
    })
    expect(mockReplayQueue).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFlush(emptyOutcome)
      await Promise.resolve()
    })

    // Now that the first flush has settled, a fresh online event may flush again.
    await act(async () => {
      window.dispatchEvent(new Event('online'))
      await Promise.resolve()
    })
    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(2))
  })

  it('does not call onOutcome for an all-zero outcome', async () => {
    mockReplayQueue.mockResolvedValue(emptyOutcome)
    const onOutcome = vi.fn()
    renderHook(() => useReplayOnReconnect(fakeApi, onOutcome))

    await waitFor(() => expect(mockReplayQueue).toHaveBeenCalledTimes(1))
    expect(onOutcome).not.toHaveBeenCalled()
  })

  it('calls onOutcome when the outcome is non-empty', async () => {
    mockReplayQueue.mockResolvedValue({ replayed: 1, conflicts: [], failed: [] })
    const onOutcome = vi.fn()
    renderHook(() => useReplayOnReconnect(fakeApi, onOutcome))

    await waitFor(() => expect(onOutcome).toHaveBeenCalledTimes(1))
    expect(onOutcome).toHaveBeenCalledWith({ replayed: 1, conflicts: [], failed: [] })
  })
})
