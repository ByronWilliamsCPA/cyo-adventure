import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BadgeUnlockToast } from './BadgeUnlockToast'

const BADGE = {
  id: 'first_ending',
  name: 'First Ending',
  description: 'You found your very first ending!',
  earned_at: '2026-08-01T00:00:00Z',
}

describe('BadgeUnlockToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the badge name and description as a polite status', () => {
    render(<BadgeUnlockToast badge={BADGE} onDismiss={vi.fn()} autoDismissMs={0} />)
    const toast = screen.getByTestId('badge-unlock-toast')
    expect(toast).toHaveAttribute('role', 'status')
    expect(screen.getByText('First Ending')).toBeInTheDocument()
    expect(screen.getByText('You found your very first ending!')).toBeInTheDocument()
  })

  it('auto-dismisses after the default delay', () => {
    const onDismiss = vi.fn()
    render(<BadgeUnlockToast badge={BADGE} onDismiss={onDismiss} />)
    vi.advanceTimersByTime(7999)
    expect(onDismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('never auto-dismisses when autoDismissMs is 0', () => {
    const onDismiss = vi.fn()
    render(<BadgeUnlockToast badge={BADGE} onDismiss={onDismiss} autoDismissMs={0} />)
    vi.advanceTimersByTime(60_000)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('dismisses on the close button', () => {
    // fireEvent, not userEvent: userEvent's internal delays deadlock under
    // the fake timers this suite needs for the auto-dismiss cases.
    const onDismiss = vi.fn()
    render(<BadgeUnlockToast badge={BADGE} onDismiss={onDismiss} autoDismissMs={0} />)
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('clears the pending auto-dismiss timer on unmount', () => {
    const onDismiss = vi.fn()
    const { unmount } = render(<BadgeUnlockToast badge={BADGE} onDismiss={onDismiss} />)
    unmount()
    vi.advanceTimersByTime(10_000)
    expect(onDismiss).not.toHaveBeenCalled()
  })
})
