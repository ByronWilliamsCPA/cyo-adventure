import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBanner } from './ErrorBanner'

describe('ErrorBanner', () => {
  it('renders message-only with role="alert" and no button when onRetry is absent', () => {
    render(<ErrorBanner>Something went wrong.</ErrorBanner>)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders a "Try again" button that calls onRetry on click when onRetry is present', () => {
    const onRetry = vi.fn()
    render(<ErrorBanner onRetry={onRetry}>Could not load data.</ErrorBanner>)
    const button = screen.getByRole('button', { name: 'Try again' })
    fireEvent.click(button)
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('forwards className alongside the base class', () => {
    render(<ErrorBanner className="console__error">Failed.</ErrorBanner>)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveClass('cyo-error')
    expect(alert).toHaveClass('console__error')
  })

  it('honors a custom retryLabel', () => {
    render(
      <ErrorBanner onRetry={() => {}} retryLabel="Retry loading">
        Failed to load.
      </ErrorBanner>,
    )
    expect(screen.getByRole('button', { name: 'Retry loading' })).toBeInTheDocument()
  })
})
