import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SkipLink } from './SkipLink'

describe('SkipLink', () => {
  it('renders a link to the target id with the default label', () => {
    render(<SkipLink targetId="main-content" />)
    const link = screen.getByRole('link', { name: 'Skip to main content' })
    expect(link).toHaveAttribute('href', '#main-content')
  })

  it('honors a custom label', () => {
    render(<SkipLink targetId="admin-main-content">Skip to review queue</SkipLink>)
    expect(screen.getByRole('link', { name: 'Skip to review queue' })).toBeInTheDocument()
  })

  it('forwards className alongside the base class', () => {
    render(<SkipLink targetId="main-content" className="kid-shell__skip-link" />)
    const link = screen.getByRole('link', { name: 'Skip to main content' })
    expect(link).toHaveClass('cyo-skip-link')
    expect(link).toHaveClass('kid-shell__skip-link')
  })
})
