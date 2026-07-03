import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FlagBadge, verdictTone } from './FlagBadge'

describe('FlagBadge', () => {
  it('renders the default label for a tone', () => {
    render(<FlagBadge tone="clean" />)
    expect(screen.getByText('Clean')).toBeInTheDocument()
  })

  it('renders a custom label and the tone class', () => {
    const { container } = render(<FlagBadge tone="flag" label="2 flagged" />)
    expect(screen.getByText('2 flagged')).toBeInTheDocument()
    expect(container.querySelector('.flag-badge--flag')).not.toBeNull()
  })

  it('maps verdicts to tones', () => {
    expect(verdictTone('block')).toBe('block')
    expect(verdictTone('flag')).toBe('flag')
    expect(verdictTone('advisory')).toBe('advisory')
    expect(verdictTone('pass')).toBe('advisory')
  })
})
