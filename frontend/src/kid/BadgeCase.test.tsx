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

  it('shows an earned badge the local catalog does not know about', () => {
    // The runtime pairing badgeCatalog.test.ts cannot reach. That test parses
    // progress/badges.py and pins the two catalogs id-for-id, so they cannot
    // drift within one repo; it says nothing about an older CACHED bundle
    // (this is a PWA with a service worker) talking to a newer backend. In
    // that pairing the child gets a BadgeUnlockToast reading the server's
    // `badge.name`, then finds the badge missing from the case a tap later.
    const { container, getByText } = render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[
          {
            id: 'wish_come_true',
            name: 'Wish Come True',
            description: 'A story you asked for came true!',
            earned_at: 't',
          },
        ]}
      />
    )
    expect(getByText('Wish Come True')).toBeInTheDocument()
    // The server's description, not a placeholder: these are the wire fields
    // BadgeUnlockToast already treats as authoritative, and the point of the
    // fix is that this component stops discarding them.
    expect(getByText('A story you asked for came true!')).toBeInTheDocument()
    // Earned, never locked: it is in the earned list by construction.
    const earned = container.querySelectorAll('.badge-case__card--earned')
    expect(earned).toHaveLength(1)
    expect(earned[0]?.textContent).toContain('Earned!')
    // The known roster is untouched and still fully locked.
    expect(container.querySelectorAll('.badge-case__card--locked')).toHaveLength(
      BADGE_CATALOG.length
    )
  })

  it('does not duplicate an earned badge that IS in the catalog', () => {
    // Guards the obvious wrong fix (appending every earned badge rather than
    // only the uncatalogued ones), which would render 'First Ending' twice:
    // once earned from the roster, once again from the server list.
    const { container, getAllByText } = render(
      <BadgeCase
        open
        onClose={vi.fn()}
        earnedBadges={[
          { id: 'first_ending', name: 'First Ending', description: 'x', earned_at: 't' },
        ]}
      />
    )
    expect(getAllByText('First Ending')).toHaveLength(1)
    expect(container.querySelectorAll('.badge-case__card')).toHaveLength(BADGE_CATALOG.length)
  })
})
