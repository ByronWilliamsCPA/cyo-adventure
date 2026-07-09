import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { BookCard } from './BookCard'
import type { LibraryItemView } from './libraryApi'

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
})
