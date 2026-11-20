import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { coverGradient } from '../library/coverPalette'
import { BookCover } from './BookCover'

afterEach(cleanup)

describe('BookCover', () => {
  it('renders the cover image, decorative only', () => {
    render(
      <BookCover
        coverUrl="https://covers.example/a.webp"
        title="Owl"
        gradientSeed="Owl"
        size="lg"
      />
    )
    const tile = screen.getByTestId('book-cover')
    expect(tile.getAttribute('aria-hidden')).toBe('true')
    expect(tile.querySelector('img')?.getAttribute('alt')).toBe('')
  })

  it('falls back to the letter tile when the cover fails to load', () => {
    render(
      <BookCover
        coverUrl="https://covers.example/expired.webp"
        title="owl"
        gradientSeed="Owl"
        size="lg"
      />
    )
    const img = screen.getByTestId('book-cover').querySelector('img')
    if (!img) throw new Error('expected an image')
    fireEvent.error(img)
    const tile = screen.getByTestId('book-cover')
    expect(tile.querySelector('img')).toBeNull()
    expect(tile.textContent).toBe('O')
    // Same colour the shelf card hashes from the same seed.
    expect(tile.style.background).toBe(coverGradient('Owl'))
  })

  it('gives a later, different URL its own chance to load', () => {
    const { rerender } = render(
      <BookCover
        coverUrl="https://covers.example/old.webp"
        title="Owl"
        gradientSeed="Owl"
        size="sm"
      />
    )
    const first = screen.getByTestId('book-cover').querySelector('img')
    if (!first) throw new Error('expected an image')
    fireEvent.error(first)
    rerender(
      <BookCover
        coverUrl="https://covers.example/new.webp"
        title="Owl"
        gradientSeed="Owl"
        size="sm"
      />
    )
    expect(screen.getByTestId('book-cover').querySelector('img')?.getAttribute('src')).toBe(
      'https://covers.example/new.webp'
    )
  })

  it('uses the letter tile when there is no cover', () => {
    render(<BookCover coverUrl={null} title="Moon" gradientSeed="Moon" size="sm" />)
    expect(screen.getByTestId('book-cover').textContent).toBe('M')
  })
})
