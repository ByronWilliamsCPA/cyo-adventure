import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EndingsBadge } from './EndingsBadge'

describe('EndingsBadge', () => {
  it('shows the found-of-total text', () => {
    render(<EndingsBadge found={3} total={7} />)
    expect(screen.getByText('3 of 7 endings found')).toBeInTheDocument()
  })

  it('renders a decorative dot for every ending, filled up to found', () => {
    const { container } = render(<EndingsBadge found={2} total={4} />)
    const dots = container.querySelectorAll('.endings-badge__dot')
    expect(dots).toHaveLength(4)
    expect(container.querySelectorAll('.endings-badge__dot--filled')).toHaveLength(2)
  })

  it('renders nothing when total is zero', () => {
    const { container } = render(<EndingsBadge found={0} total={0} />)
    expect(container.firstChild).toBeNull()
  })

  it('clamps a found count above total instead of over-filling the dot row', () => {
    const { container } = render(<EndingsBadge found={9} total={3} />)
    expect(screen.getByText('3 of 3 endings found')).toBeInTheDocument()
    expect(container.querySelectorAll('.endings-badge__dot--filled')).toHaveLength(3)
  })

  it('drops the dot row AND the denominator past the shared milestone threshold (AL-028)', () => {
    const { container } = render(<EndingsBadge found={4} total={20} />)
    expect(screen.getByText('4 endings found')).toBeInTheDocument()
    expect(screen.queryByText(/of 20/)).toBeNull()
    expect(container.querySelector('.endings-badge__dots')).toBeNull()
  })

  it('uses singular framing for one found ending past the threshold', () => {
    render(<EndingsBadge found={1} total={15} />)
    expect(screen.getByText('1 ending found')).toBeInTheDocument()
  })

  it('the dot row is decorative (aria-hidden) so the text is the sole accessible name', () => {
    const { container } = render(<EndingsBadge found={1} total={2} />)
    expect(container.querySelector('.endings-badge__dots')).toHaveAttribute('aria-hidden', 'true')
  })

  it('keeps the "N of M" text and dots exactly at the shared threshold (10)', () => {
    const { container } = render(<EndingsBadge found={3} total={10} />)
    expect(screen.getByText('3 of 10 endings found')).toBeInTheDocument()
    expect(container.querySelector('.endings-badge__dots')).not.toBeNull()
  })
})
