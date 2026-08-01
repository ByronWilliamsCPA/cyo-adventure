import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BadgeCase } from './BadgeCase'
import { BADGE_CATALOG } from './badgeCatalog'

describe('BadgeCase', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<BadgeCase open={false} onClose={vi.fn()} earnedBadges={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows every catalog badge, earned and unearned alike', () => {
    render(<BadgeCase open onClose={vi.fn()} earnedBadges={[]} />)
    for (const entry of BADGE_CATALOG) {
      expect(screen.getByText(entry.name)).toBeInTheDocument()
    }
  })

  it('marks an earned badge with the earned styling class', () => {
    const { container } = render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[{ id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' }]}
      />
    )
    const cards = container.querySelectorAll('.badge-case__card--earned')
    expect(cards).toHaveLength(1)
  })

  it('marks every other badge as locked', () => {
    const { container } = render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[{ id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' }]}
      />
    )
    expect(container.querySelectorAll('.badge-case__card--locked')).toHaveLength(BADGE_CATALOG.length - 1)
  })

  it('shows every badge as locked when nothing has been earned yet', () => {
    const { container } = render(<BadgeCase open onClose={vi.fn()} earnedBadges={[]} />)
    expect(container.querySelectorAll('.badge-case__card--locked')).toHaveLength(BADGE_CATALOG.length)
    expect(container.querySelectorAll('.badge-case__card--earned')).toHaveLength(0)
  })
})
