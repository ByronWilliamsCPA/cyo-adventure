import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RecommendationChip } from './RecommendationChip'

describe('RecommendationChip', () => {
  it('shows the family-ring wording with no "Cousin" prefix', () => {
    render(
      <RecommendationChip summary={{ firstName: 'Maya', firstRing: 'family', moreCount: 0 }} />
    )
    expect(screen.getByText('Maya loved this')).toBeInTheDocument()
    expect(screen.queryByText(/cousin/i)).not.toBeInTheDocument()
  })

  it('shows the connection-ring wording with a "Cousin" prefix', () => {
    render(
      <RecommendationChip summary={{ firstName: 'Leo', firstRing: 'connection', moreCount: 0 }} />
    )
    expect(screen.getByText('Cousin Leo loved this')).toBeInTheDocument()
  })

  it('appends "and N more" when additional recommenders share the book', () => {
    render(
      <RecommendationChip summary={{ firstName: 'Maya', firstRing: 'family', moreCount: 2 }} />
    )
    expect(screen.getByText('Maya loved this and 2 more')).toBeInTheDocument()
  })

  it('applies the "and N more" suffix to a connection-ring first recommender too', () => {
    render(
      <RecommendationChip summary={{ firstName: 'Leo', firstRing: 'connection', moreCount: 1 }} />
    )
    expect(screen.getByText('Cousin Leo loved this and 1 more')).toBeInTheDocument()
  })

  it('marks the decorative glyph aria-hidden so the sentence is the sole accessible name', () => {
    const { container } = render(
      <RecommendationChip summary={{ firstName: 'Maya', firstRing: 'family', moreCount: 0 }} />
    )
    expect(container.querySelector('.recommendation-chip__glyph')).toHaveAttribute(
      'aria-hidden',
      'true'
    )
  })
})
