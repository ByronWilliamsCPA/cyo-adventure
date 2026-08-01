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
        earnedBadges={[
          { id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' },
        ]}
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
        earnedBadges={[
          { id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' },
        ]}
      />
    )
    expect(container.querySelectorAll('.badge-case__card--locked')).toHaveLength(
      BADGE_CATALOG.length - 1
    )
  })

  /**
   * The class-name assertions above are all this file had, and a class name
   * is not perceivable: it satisfies no user. These assert the state reaches
   * a reader who cannot see colour or saturation, which is what WCAG 1.4.1
   * actually asks for.
   */
  it('states earned-vs-locked in text, not only in a styling class', () => {
    render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[
          { id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' },
        ]}
      />
    )
    expect(screen.getAllByText('Earned!')).toHaveLength(1)
    expect(screen.getAllByText('Not yet')).toHaveLength(BADGE_CATALOG.length - 1)
  })

  it('keeps the state word inside the card it describes', () => {
    // A state word rendered somewhere else on the screen would read as
    // correct in a getAllByText count while telling a screen reader nothing
    // about WHICH badge it belongs to.
    const { container } = render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[
          { id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' },
        ]}
      />
    )
    const earned = container.querySelector('.badge-case__card--earned')
    expect(earned?.textContent).toContain('First Ending')
    expect(earned?.textContent).toContain('Earned!')
    for (const locked of container.querySelectorAll('.badge-case__card--locked')) {
      expect(locked.textContent).toContain('Not yet')
    }
  })

  it('shows every badge as locked when nothing has been earned yet', () => {
    const { container } = render(<BadgeCase open onClose={vi.fn()} earnedBadges={[]} />)
    expect(container.querySelectorAll('.badge-case__card--locked')).toHaveLength(
      BADGE_CATALOG.length
    )
    expect(container.querySelectorAll('.badge-case__card--earned')).toHaveLength(0)
  })
})
