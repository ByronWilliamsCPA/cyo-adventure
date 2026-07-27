import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { useReaderFontScale } from './useReaderFontScale'

// Complements the consumer-level coverage in TextSizeControl.test.tsx by driving
// the hook's own API (setLevel) directly and proving the localStorage-backed
// preference survives a genuine unmount/remount, not just a state update within
// one render tree. The persistence mechanism mirrored here is the exact key the
// hook writes: `cyo-reader-font-scale-<profileId>`.
describe('useReaderFontScale setLevel effect and persistence', () => {
  afterEach(() => localStorage.clear())

  it('applies the chosen level to the observable scale and label', () => {
    const { result } = renderHook(() => useReaderFontScale('p1'))
    // Baseline: default level 0 maps to scale 1.
    expect(result.current.scale).toBe(1)

    act(() => result.current.setLevel(1))
    expect(result.current.level).toBe(1)
    expect(result.current.scale).toBe(1.15)
    expect(result.current.label).toBe('A+')

    act(() => result.current.setLevel(2))
    expect(result.current.scale).toBe(1.3)
    expect(result.current.label).toBe('A++')
  })

  it('persists the preference across a full remount via localStorage', () => {
    const first = renderHook(() => useReaderFontScale('p1'))
    act(() => first.result.current.setLevel(2))
    // The choice must have been written through to storage, not just held in
    // component state, for a later reader session to pick it up.
    expect(localStorage.getItem('cyo-reader-font-scale-p1')).toBe('2')
    first.unmount()

    // A fresh mount (new reader session) reads the persisted level back.
    const second = renderHook(() => useReaderFontScale('p1'))
    expect(second.result.current.level).toBe(2)
    expect(second.result.current.scale).toBe(1.3)
  })

  it('scopes the persisted preference per profile', () => {
    const p1 = renderHook(() => useReaderFontScale('p1'))
    act(() => p1.result.current.setLevel(2))
    p1.unmount()

    // A different profile does not inherit p1's larger size; it starts at the
    // default, proving the storage key is profile-scoped.
    const p2 = renderHook(() => useReaderFontScale('p2'))
    expect(p2.result.current.level).toBe(0)
    expect(p2.result.current.scale).toBe(1)
  })
})
