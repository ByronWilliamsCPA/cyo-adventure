import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { FoundEndingCard } from '../kid/progressApi'
import { EndingsGallery } from './EndingsGallery'

const FOUND: FoundEndingCard[] = [
  { ending_id: 'e1', title: 'The Happy Ending', valence: 'positive' },
  { ending_id: 'e2', title: 'A Quiet Ending', valence: 'neutral' },
]

describe('EndingsGallery', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <EndingsGallery open={false} onClose={vi.fn()} bookTitle="A Book" totalEndings={3} foundEndings={[]} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders a found card with its real title for each found ending', () => {
    render(
      <EndingsGallery open onClose={vi.fn()} bookTitle="A Book" totalEndings={3} foundEndings={FOUND} />
    )
    expect(screen.getByText('The Happy Ending')).toBeInTheDocument()
    expect(screen.getByText('A Quiet Ending')).toBeInTheDocument()
  })

  it('renders a silhouette placeholder for each unfound ending, below the large-M threshold', () => {
    render(
      <EndingsGallery open onClose={vi.fn()} bookTitle="A Book" totalEndings={3} foundEndings={FOUND} />
    )
    expect(screen.getAllByText('Still hidden')).toHaveLength(1)
  })

  it('never reveals a real title for an unfound ending', () => {
    render(
      <EndingsGallery open onClose={vi.fn()} bookTitle="A Book" totalEndings={5} foundEndings={FOUND} />
    )
    // Only "Still hidden" placeholders for the 3 unfound; nothing else leaks.
    expect(screen.getAllByText('Still hidden')).toHaveLength(3)
  })

  it('switches to milestone framing above the large-M threshold, with no silhouette grid', () => {
    render(
      <EndingsGallery
        open
        onClose={vi.fn()}
        bookTitle="A Big Book"
        totalEndings={200}
        foundEndings={FOUND}
      />
    )
    expect(screen.getByText('2 endings found')).toBeInTheDocument()
    expect(screen.queryByText('Still hidden')).toBeNull()
  })

  it('shows an encouraging empty state when nothing has been found yet', () => {
    render(<EndingsGallery open onClose={vi.fn()} bookTitle="A Book" totalEndings={5} foundEndings={[]} />)
    expect(screen.getByText('Keep reading to start finding endings!')).toBeInTheDocument()
  })

  it('never shows negative framing for a negative-valence found ending (K14)', () => {
    render(
      <EndingsGallery
        open
        onClose={vi.fn()}
        bookTitle="A Book"
        totalEndings={2}
        foundEndings={[{ ending_id: 'e3', title: 'A Brave Turn', valence: 'negative' }]}
      />
    )
    expect(screen.getByText('A Brave Turn')).toBeInTheDocument()
    expect(screen.queryByText(/fail|lost|sad|bad/i)).toBeNull()
  })
})
