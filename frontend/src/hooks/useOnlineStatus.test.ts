import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useOnlineStatus } from './useOnlineStatus'

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}

afterEach(() => setOnLine(true))

describe('useOnlineStatus', () => {
  it('reflects the initial navigator.onLine value', () => {
    setOnLine(false)
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)
  })

  it('updates on online/offline events', () => {
    setOnLine(true)
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)
    act(() => {
      setOnLine(false)
      window.dispatchEvent(new Event('offline'))
    })
    expect(result.current).toBe(false)
    act(() => {
      setOnLine(true)
      window.dispatchEvent(new Event('online'))
    })
    expect(result.current).toBe(true)
  })
})
