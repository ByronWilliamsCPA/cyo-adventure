import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useOnlineStatus } from './useOnlineStatus'

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}

beforeEach(() => {
  // A reported-online state is now confirmed with an active probe (see
  // probeConnectivity.ts), so every navigator.onLine === true path awaits a
  // fetch. Stub it to resolve immediately so these tests stay deterministic.
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  setOnLine(true)
})

describe('useOnlineStatus', () => {
  it('reflects the initial navigator.onLine value', () => {
    setOnLine(false)
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)
  })

  it('updates on online/offline events', async () => {
    setOnLine(true)
    const { result } = renderHook(() => useOnlineStatus())
    await waitFor(() => expect(result.current).toBe(true))

    act(() => {
      setOnLine(false)
      window.dispatchEvent(new Event('offline'))
    })
    await waitFor(() => expect(result.current).toBe(false))

    act(() => {
      setOnLine(true)
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => expect(result.current).toBe(true))
  })

  it('defaults to online when navigator is unavailable (SSR-style environment)', () => {
    // The initial-state seed guards `typeof navigator === 'undefined'` so the
    // hook is safe outside a browser. Stub navigator to undefined so that arm
    // actually runs; the effect's listeners still attach to window fine.
    vi.stubGlobal('navigator', undefined)
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)
  })
})
