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

  it('auto-dismisses on schedule even when the parent re-renders', () => {
    // The regression this guards: Reader.tsx passes an inline arrow, so
    // `onDismiss` changes identity on every parent render. While it sat in
    // the effect's dependency array, each re-render tore down and rebuilt
    // the timer, restarting the countdown; an ending screen that re-rendered
    // more often than the delay would never auto-dismiss. Re-rendering with
    // a FRESH function each time is the whole point, so passing a stable
    // `onDismiss` here would test nothing.
    const onDismiss = vi.fn()
    const { rerender } = render(
      <BadgeUnlockToast badge={BADGE} onDismiss={() => void onDismiss()} />
    )
    for (let elapsed = 0; elapsed < 7500; elapsed += 500) {
      vi.advanceTimersByTime(500)
      rerender(<BadgeUnlockToast badge={BADGE} onDismiss={() => void onDismiss()} />)
    }
    expect(onDismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(500)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('calls the LATEST onDismiss, not the one captured at mount', () => {
    // The ref pattern must not freeze the first callback: the timer fires
    // once, and it has to reach whatever handler is current by then.
    const first = vi.fn()
    const second = vi.fn()
    const { rerender } = render(<BadgeUnlockToast badge={BADGE} onDismiss={first} />)
    rerender(<BadgeUnlockToast badge={BADGE} onDismiss={second} />)
    vi.advanceTimersByTime(8000)
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
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
