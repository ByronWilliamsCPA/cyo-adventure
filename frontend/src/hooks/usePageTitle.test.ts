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
})
