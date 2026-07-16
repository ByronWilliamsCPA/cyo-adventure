import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AppErrorBoundary } from './AppErrorBoundary'

function Bomb(): never {
  throw new Error('render boom')
}

describe('AppErrorBoundary', () => {
  it('renders children normally when nothing throws', () => {
    render(
      <AppErrorBoundary>
        <p>all good</p>
      </AppErrorBoundary>
    )
    expect(screen.getByText('all good')).toBeInTheDocument()
  })

  it('renders a styled recovery screen instead of unmounting on a render throw', () => {
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <AppErrorBoundary>
          <Bomb />
        </AppErrorBoundary>
      )
      expect(screen.getByRole('heading', { name: /something went wrong/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /go to the start/i })).toHaveAttribute('href', '/')
    } finally {
      logSpy.mockRestore()
    }
  })
})
