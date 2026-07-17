import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReaderChrome } from './ReaderChrome'

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}
afterEach(() => setOnLine(true))

describe('ReaderChrome', () => {
  it('shows no connection badge while online, just the progressbar', () => {
    setOnLine(true)
    render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
    // Online is the unremarkable normal: no badge (and no jargon) renders.
    expect(screen.queryByText('Connected')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('40')
  })

  it('shows a kid-readable "No internet" badge when the device is offline', () => {
    setOnLine(false)
    render(<ReaderChrome percent={0} label="Not started" />)
    expect(screen.getByText('No internet')).toBeTruthy()
    expect(screen.queryByText('Offline')).toBeNull()
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

  it('renders the back slot when provided', () => {
    setOnLine(true)
    render(
      <ReaderChrome
        percent={40}
        label="2 of 5 pages explored"
        back={<button type="button">Leave</button>}
      />
    )
    expect(screen.getByRole('button', { name: 'Leave' })).toBeTruthy()
  })

  it('renders nothing extra when the back slot is omitted', () => {
    setOnLine(true)
    render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  describe('read-aloud toggle (K7)', () => {
    it('is not rendered when the readAloud prop is omitted', () => {
      render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
      expect(screen.queryByRole('button')).toBeNull()
      expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
      expect(screen.queryByLabelText('Stop reading aloud')).toBeNull()
    })

    it('renders an obvious, unpressed toggle when not speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome
          percent={40}
          label="2 of 5 pages explored"
          readAloud={{ speaking: false, onToggle }}
        />
      )
      const button = screen.getByRole('button', { name: 'Read this page aloud' })
      expect(button).toHaveAttribute('aria-pressed', 'false')
      expect(button.className).not.toContain('reader-tts-toggle--speaking')
      fireEvent.click(button)
      expect(onToggle).toHaveBeenCalledTimes(1)
    })

    it('shows a visually and semantically distinct pressed state while speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome
          percent={40}
          label="2 of 5 pages explored"
          readAloud={{ speaking: true, onToggle }}
        />
      )
      const button = screen.getByRole('button', { name: 'Stop reading aloud' })
      expect(button).toHaveAttribute('aria-pressed', 'true')
      expect(button.className).toContain('reader-tts-toggle--speaking')
    })
  })

  describe('flag slot (K15)', () => {
    it('is not rendered when the flag prop is omitted', () => {
      render(<ReaderChrome percent={40} label="2 of 5 pages explored" />)
      expect(screen.queryByRole('button')).toBeNull()
    })

    it('renders the caller-supplied flag node', () => {
      render(
        <ReaderChrome
          percent={40}
          label="2 of 5 pages explored"
          flag={<button type="button">Tell a grown-up</button>}
        />
      )
      expect(screen.getByRole('button', { name: 'Tell a grown-up' })).toBeTruthy()
    })
  })
})
