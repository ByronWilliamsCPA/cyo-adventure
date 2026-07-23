import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BookDetailsDialog } from './BookDetailsDialog'

describe('BookDetailsDialog', () => {
  it('renders age band, themes, content flags, and the caller-supplied moderation badge', () => {
    render(
      <BookDetailsDialog
        title="The Lantern"
        ageBand="8-11"
        themes={['friendship', 'courage']}
        contentFlags={{ violence: 'mild', scariness: 'none', peril: 'moderate' }}
        moderationBadge={<span>2 flags</span>}
        onClose={() => {}}
      />
    )
    expect(screen.getByRole('dialog', { name: 'The Lantern' })).toBeInTheDocument()
    expect(screen.getByText('Ages 8-11')).toBeInTheDocument()
    expect(screen.getByText('friendship, courage')).toBeInTheDocument()
    expect(screen.getByText(/Violence: mild/)).toBeInTheDocument()
    expect(screen.getByText(/Scariness: none/)).toBeInTheDocument()
    expect(screen.getByText(/Peril: moderate/)).toBeInTheDocument()
    expect(screen.getByText('2 flags')).toBeInTheDocument()
  })

  it('omits the age band, themes, and moderation rows when not provided', () => {
    render(
      <BookDetailsDialog
        title="Untitled"
        ageBand={null}
        themes={[]}
        contentFlags={null}
        onClose={() => {}}
      />
    )
    expect(screen.queryByText('Age band')).not.toBeInTheDocument()
    expect(screen.queryByText('Themes')).not.toBeInTheDocument()
    expect(screen.queryByText('Moderation')).not.toBeInTheDocument()
    expect(screen.queryByText('Content flags')).not.toBeInTheDocument()
  })

  it('reports "None reported" when contentFlags is present but every level is none', () => {
    render(
      <BookDetailsDialog
        title="Calm Tale"
        ageBand={null}
        themes={[]}
        contentFlags={{ violence: 'none', scariness: 'none', peril: 'none' }}
        onClose={() => {}}
      />
    )
    expect(screen.getByText('Content flags')).toBeInTheDocument()
    expect(screen.getByText('None reported')).toBeInTheDocument()
  })

  it('defaults a missing content-flag key to "none"', () => {
    render(
      <BookDetailsDialog
        title="Partial Flags"
        ageBand={null}
        themes={[]}
        contentFlags={{ violence: 'mild' }}
        onClose={() => {}}
      />
    )
    expect(screen.getByText(/Violence: mild/)).toBeInTheDocument()
    expect(screen.getByText(/Scariness: none/)).toBeInTheDocument()
    expect(screen.getByText(/Peril: none/)).toBeInTheDocument()
  })

  it('calls onClose when Close is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <BookDetailsDialog
        title="The Lantern"
        ageBand={null}
        themes={[]}
        contentFlags={null}
        onClose={onClose}
      />
    )
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
