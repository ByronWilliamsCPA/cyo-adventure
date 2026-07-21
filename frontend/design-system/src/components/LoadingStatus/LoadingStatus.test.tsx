import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoadingStatus } from './LoadingStatus'

describe('LoadingStatus', () => {
  it('renders the default loading text with role="status" and aria-live="polite"', () => {
    render(<LoadingStatus />)
    const status = screen.getByRole('status')
    expect(status.textContent).toBe('Loading…')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })

  it('renders custom children instead of the default text', () => {
    render(<LoadingStatus>Loading your books…</LoadingStatus>)
    expect(screen.getByRole('status').textContent).toBe('Loading your books…')
  })

  it('applies a passed className alongside the base class', () => {
    render(<LoadingStatus className="route-fallback">Just a sec...</LoadingStatus>)
    const status = screen.getByRole('status')
    expect(status.className).toBe('cyo-loading route-fallback')
  })

  it('applies only the base class when no className is passed', () => {
    render(<LoadingStatus />)
    expect(screen.getByRole('status').className).toBe('cyo-loading')
  })
})
