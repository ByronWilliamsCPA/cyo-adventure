import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ReaderChrome } from './ReaderChrome'

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}
afterEach(() => setOnLine(true))

describe('ReaderChrome', () => {
  it('shows connected status and a progressbar', () => {
    setOnLine(true)
    render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
    expect(screen.getByText('Connected')).toBeTruthy()
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('40')
  })

  it('shows offline status when the device is offline', () => {
    setOnLine(false)
    render(<ReaderChrome percent={0} label="Not started" />)
    expect(screen.getByText('Offline')).toBeTruthy()
  })

  it('hides the numeric label by default (the total is not reliable)', () => {
    setOnLine(true)
    render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
    expect(screen.queryByText('2 of 5 pages explored')).toBeNull()
    // The bar is still there and still accessible via aria-label.
    expect(screen.getByRole('progressbar').getAttribute('aria-label')).toBe(
      '2 of 5 pages explored'
    )
  })

  it('shows the numeric label when the caller vouches for it', () => {
    setOnLine(true)
    render(<ReaderChrome percent={40} label="2 of 5 pages explored" showLabel />)
    expect(screen.getByText('2 of 5 pages explored')).toBeTruthy()
  })
})
