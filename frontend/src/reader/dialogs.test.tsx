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
