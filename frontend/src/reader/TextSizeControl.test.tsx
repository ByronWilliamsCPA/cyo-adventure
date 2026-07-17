import { fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { TextSizeControl } from './TextSizeControl'
import { useReaderFontScale } from './useReaderFontScale'

function Harness({ profileId }: { profileId: string }) {
  const fontScale = useReaderFontScale(profileId)
  return (
    <div>
      <span data-testid="scale">{fontScale.scale}</span>
      <TextSizeControl fontScale={fontScale} />
    </div>
  )
}

describe('useReaderFontScale', () => {
  afterEach(() => localStorage.clear())

  it('defaults to level 0 (scale 1) with no stored preference', () => {
    const { result } = renderHook(() => useReaderFontScale('p1'))
    expect(result.current.level).toBe(0)
    expect(result.current.scale).toBe(1)
    expect(result.current.label).toBe('A')
  })

  it('reads a persisted level per profile', () => {
    localStorage.setItem('cyo-reader-font-scale-p1', '2')
    const { result } = renderHook(() => useReaderFontScale('p1'))
    expect(result.current.level).toBe(2)
    expect(result.current.scale).toBe(1.3)
  })

  it('ignores an out-of-range stored value', () => {
    localStorage.setItem('cyo-reader-font-scale-p1', '9')
    const { result } = renderHook(() => useReaderFontScale('p1'))
    expect(result.current.level).toBe(0)
  })
})

describe('TextSizeControl', () => {
  afterEach(() => localStorage.clear())

  it('renders a radiogroup with the current size checked', () => {
    render(<Harness profileId="p1" />)
    expect(screen.getByRole('radiogroup', { name: 'Text size' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Text size A' })).toHaveAttribute(
      'aria-checked',
      'true'
    )
  })

  it('changes and persists the size when a larger option is chosen', () => {
    render(<Harness profileId="p1" />)
    fireEvent.click(screen.getByRole('radio', { name: 'Text size A++' }))
    expect(screen.getByTestId('scale').textContent).toBe('1.3')
    expect(localStorage.getItem('cyo-reader-font-scale-p1')).toBe('2')
  })
})
