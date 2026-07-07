import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConflictDialog } from './ConflictDialog'
import { DownloadNeeded } from './DownloadNeeded'

afterEach(cleanup)

describe('ConflictDialog', () => {
  it('shows the conflict copy and wires both choices', () => {
    const onKeep = vi.fn()
    const onUseNewest = vi.fn()
    render(<ConflictDialog onKeepThisDevice={onKeep} onUseNewest={onUseNewest} />)
    expect(screen.getByTestId('conflict-dialog')).toBeTruthy()
    expect(screen.getByText(/reading on another device/i)).toBeTruthy()
    fireEvent.click(screen.getByTestId('conflict-keep'))
    fireEvent.click(screen.getByTestId('conflict-use-newest'))
    expect(onKeep).toHaveBeenCalledOnce()
    expect(onUseNewest).toHaveBeenCalledOnce()
  })

  // F23: focus-trap coverage. The dialog is blocking (no Escape dismiss), so
  // a keyboard user relies entirely on this behavior to both reach the
  // actions and get back to wherever they started.
  it('focuses the first action button on open', () => {
    render(<ConflictDialog onKeepThisDevice={() => {}} onUseNewest={() => {}} />)
    expect(document.activeElement).toBe(screen.getByTestId('conflict-keep'))
  })

  it('wraps Tab from the last button back to the first', () => {
    render(<ConflictDialog onKeepThisDevice={() => {}} onUseNewest={() => {}} />)
    const last = screen.getByTestId('conflict-use-newest')
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByTestId('conflict-keep'))
  })

  it('wraps Shift+Tab from the first button to the last', () => {
    render(<ConflictDialog onKeepThisDevice={() => {}} onUseNewest={() => {}} />)
    const first = screen.getByTestId('conflict-keep')
    first.focus()
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByTestId('conflict-use-newest'))
  })

  it('restores focus to the previously-focused element on close', () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const { unmount } = render(
      <ConflictDialog onKeepThisDevice={() => {}} onUseNewest={() => {}} />
    )
    expect(document.activeElement).not.toBe(trigger)

    unmount()
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })
})

describe('DownloadNeeded', () => {
  it('shows the eviction copy and retries', () => {
    const onRetry = vi.fn()
    render(<DownloadNeeded onRetry={onRetry} />)
    expect(screen.getByTestId('download-needed')).toBeTruthy()
    expect(screen.getByText(/needs to download again/i)).toBeTruthy()
    fireEvent.click(screen.getByTestId('download-retry'))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('offers a back-to-library action when provided', () => {
    const onBack = vi.fn()
    render(<DownloadNeeded onRetry={() => {}} onBackToLibrary={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: 'Back to my books' }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
