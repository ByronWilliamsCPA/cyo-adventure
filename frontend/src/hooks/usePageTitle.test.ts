import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { usePageTitle } from './usePageTitle'

describe('usePageTitle', () => {
  it('suffixes the app name onto the given title', () => {
    renderHook(() => usePageTitle('My Books'))
    expect(document.title).toBe('My Books - CYO Adventure')
  })

  it('uses the title as-is when bare is set', () => {
    renderHook(() => usePageTitle('CYO Adventure', { bare: true }))
    expect(document.title).toBe('CYO Adventure')
  })

  it('updates document.title when the title prop changes', () => {
    const { rerender } = renderHook(({ title }) => usePageTitle(title), {
      initialProps: { title: 'My Books' },
    })
    expect(document.title).toBe('My Books - CYO Adventure')

    rerender({ title: 'Reading History' })
    expect(document.title).toBe('Reading History - CYO Adventure')
  })

  it('re-runs when only the bare option changes', () => {
    // Pins `bare` as a dependency, not just `title`. Without this the hook
    // could regress to a `[title]` dep array and the three tests above would
    // all still pass, because none of them changes `bare` after mount.
    const { rerender } = renderHook(({ bare }) => usePageTitle('CYO Adventure', { bare }), {
      initialProps: { bare: false },
    })
    expect(document.title).toBe('CYO Adventure - CYO Adventure')

    rerender({ bare: true })
    expect(document.title).toBe('CYO Adventure')
  })

  it('leaves the last title in place on unmount rather than restoring', () => {
    // Pins the no-restore-on-unmount contract the hook's docstring commits to.
    // This is deliberate behavior, not an oversight: during navigation the
    // next page sets its own title before any cleanup would matter, so
    // restoring would only flash the previous title. Asserting it here means
    // a future "fix" that adds a cleanup function fails loudly instead of
    // silently introducing that flash.
    document.title = 'Sentinel'
    const { unmount } = renderHook(() => usePageTitle('My Books'))
    expect(document.title).toBe('My Books - CYO Adventure')

    unmount()
    expect(document.title).toBe('My Books - CYO Adventure')
  })
})
