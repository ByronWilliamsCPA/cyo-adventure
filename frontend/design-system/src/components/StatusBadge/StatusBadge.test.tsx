import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it.each([
    ['connected', 'Connected'],
    ['offline', 'Offline'],
    ['loading', 'Connecting…'],
    ['error', 'Error'],
  ] as const)('renders the default label for status=%s', (status, expectedLabel) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', expectedLabel)
    expect(screen.getByText(expectedLabel)).toBeInTheDocument()
  })

  it('applies the status-specific modifier class', () => {
    render(<StatusBadge status="error" />)
    expect(screen.getByRole('status').className).toContain('cyo-status--error')
  })

  it('uses a custom label over the default when provided', () => {
    render(<StatusBadge status="offline" label="No connection" />)
    expect(screen.getByText('No connection')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'No connection')
  })
})
