import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { BookCard } from './BookCard'
import type { LibraryItemView } from './libraryApi'
import { coverGradient } from './coverPalette'

const BASE_ITEM: LibraryItemView = {
  id: 's1',
  title: 'The Lantern',
  version: 2,
  age_band: '6-8',
  tier: 1,
  reading_level_target: 2,
  node_count: 10,
  rating: null,
  progress: null,
  series_id: null,
  book_index: null,
  cover_url: null,
}

function renderCard(item: LibraryItemView, onContinue?: (item: LibraryItemView) => void) {
  return render(
    <MemoryRouter>
      <BookCard item={item} profileId="p1" onRate={() => {}} onContinue={onContinue} />
    </MemoryRouter>
  )
}

describe('BookCard', () => {
  it('does not render a continue button when the book has no series_id', () => {
    renderCard(BASE_ITEM, vi.fn())
    expect(screen.queryByRole('button', { name: /continue this story/i })).not.toBeInTheDocument()
  })

  it('does not render a continue button when onContinue is not provided, even for a series book', () => {
    renderCard({ ...BASE_ITEM, series_id: 'ser1', book_index: 1 })
    expect(screen.queryByRole('button', { name: /continue this story/i })).not.toBeInTheDocument()
  })

  it('renders a continue button for a series-tagged book and fires onContinue with the item', () => {
    const onContinue = vi.fn()
    const item = { ...BASE_ITEM, series_id: 'ser1', book_index: 1 }
    renderCard(item, onContinue)
    const button = screen.getByRole('button', { name: /continue this story/i })
    fireEvent.click(button)
    expect(onContinue).toHaveBeenCalledWith(item)
  })

  it('renders the cover image when cover_url is set', () => {
    renderCard({ ...BASE_ITEM, cover_url: 'https://cdn/x.webp' })
    // <img alt=""> has the implicit accessibility role "presentation", not
    // "img" (HTML-AAM); the `hidden` query option does not change that.
    const img = screen.getByRole<HTMLImageElement>('presentation', { hidden: true })
    expect(img.src).toContain('https://cdn/x.webp')
  })

  it('falls back to the first-letter tile when cover_url is null', () => {
    renderCard({ ...BASE_ITEM, title: 'Zephyr', cover_url: null })
    expect(screen.getByText('Z')).toBeInTheDocument()
    expect(screen.queryByRole('presentation', { hidden: true })).not.toBeInTheDocument()
  })

  it('paints the tile with the title-derived gradient when cover_url is absent', () => {
    const { container } = renderCard({ ...BASE_ITEM, title: 'Zephyr', cover_url: null })
    const tile = container.querySelector('.book-card__tile')
    expect(tile).toHaveClass('book-card__tile--painted')
    expect(tile).toHaveStyle({ background: coverGradient('Zephyr') })
  })

  it('does not paint the tile when cover_url is present', () => {
    const { container } = renderCard({ ...BASE_ITEM, cover_url: 'https://cdn/x.webp' })
    const tile = container.querySelector('.book-card__tile')
    expect(tile).not.toHaveClass('book-card__tile--painted')
    expect(tile).not.toHaveAttribute('style')
  })
})
