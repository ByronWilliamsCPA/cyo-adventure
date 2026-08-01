import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReaderChrome } from './ReaderChrome'

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}
afterEach(() => setOnLine(true))

describe('ReaderChrome', () => {
  it('shows no connection badge while online, just the position pill', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 2' }} />)
    // Online is the unremarkable normal: no badge (and no jargon) renders.
    expect(screen.queryByText('Connected')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    // W1.2/AL-029: no percent bar while reading, just the visible text pill.
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByTestId('reader-position').textContent).toBe('Page 2')
  })

  it('shows a kid-readable "No internet" badge when the device is offline', () => {
    setOnLine(false)
    render(<ReaderChrome position={{ label: 'Page 1' }} />)
    expect(screen.getByText('No internet')).toBeTruthy()
    expect(screen.queryByText('Offline')).toBeNull()
  })

  it('the position pill text is always visible (no hidden numeric label to withhold)', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 2' }} />)
    expect(screen.getByText('Page 2')).toBeInTheDocument()
  })

  it('shows a real, true 100% progress bar when the position is complete', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'You finished this story!', complete: true }} />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('100')
    expect(bar.getAttribute('aria-label')).toBe('You finished this story!')
    // showLabel defaults to false: the ProgressBar's own numeric text stays
    // hidden (aria-label still carries it), matching the pre-W1.2 chrome.
    expect(screen.queryByText('You finished this story!')).toBeNull()
  })

  it('shows the complete bar numeric label when the caller vouches for it', () => {
    setOnLine(true)
    render(
      <ReaderChrome position={{ label: 'You finished this story!', complete: true }} showLabel />
    )
    expect(screen.getByText('You finished this story!')).toBeTruthy()
  })

  it('renders the back slot when provided', () => {
    setOnLine(true)
    render(
      <ReaderChrome position={{ label: 'Page 1' }} back={<button type="button">Leave</button>} />
    )
    expect(screen.getByRole('button', { name: 'Leave' })).toBeTruthy()
  })

  it('renders nothing extra when the back slot is omitted', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 1' }} />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  describe('read-aloud toggle (K7)', () => {
    it('is not rendered when the readAloud prop is omitted', () => {
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      expect(screen.queryByRole('button')).toBeNull()
      expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
      expect(screen.queryByLabelText('Stop reading aloud')).toBeNull()
    })

    it('renders an obvious, unpressed toggle when not speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome
          position={{ label: 'Page 1' }}
          readAloud={{ speaking: false, onToggle }}
        />
      )
      const button = screen.getByRole('button', { name: 'Read this page aloud' })
      // The unpressed state is fully observable: aria-pressed=false plus the
      // "Listen" visible affordance. (Dropped a redundant assertion on the
      // reader-tts-toggle--speaking class token, which is driven by the same
      // `speaking` flag as aria-pressed and carries no extra user-facing signal.)
      expect(button).toHaveAttribute('aria-pressed', 'false')
      expect(screen.getByText('Listen')).toBeInTheDocument()
      fireEvent.click(button)
      expect(onToggle).toHaveBeenCalledTimes(1)
    })

    it('shows a visually and semantically distinct pressed state while speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome position={{ label: 'Page 1' }} readAloud={{ speaking: true, onToggle }} />
      )
      const button = screen.getByRole('button', { name: 'Stop reading aloud' })
      // The pressed state is fully observable: aria-pressed=true plus the
      // "Stop" visible affordance. (Dropped a redundant assertion on the
      // reader-tts-toggle--speaking class token, which is driven by the same
      // `speaking` flag as aria-pressed and carries no extra user-facing signal.)
      expect(button).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByText('Stop')).toBeInTheDocument()
    })
  })

  describe('flag slot (K15)', () => {
    it('is not rendered when the flag prop is omitted', () => {
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      expect(screen.queryByRole('button')).toBeNull()
    })

    it('renders the caller-supplied flag node', () => {
      render(
        <ReaderChrome
          position={{ label: 'Page 1' }}
          flag={<button type="button">Tell a grown-up</button>}
        />
      )
      expect(screen.getByRole('button', { name: 'Tell a grown-up' })).toBeTruthy()
    })
  })
})
