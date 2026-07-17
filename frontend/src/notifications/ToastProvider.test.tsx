import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from './ToastProvider'
import { useToast } from './useToast'
import type { ToastTone } from './toastContext'

function ShowToastButton({ message, tone }: { message: string; tone?: ToastTone }) {
  const { showToast } = useToast()
  return (
    <button type="button" onClick={() => showToast(message, tone ? { tone } : undefined)}>
      show toast
    </button>
  )
}

function renderWithProvider(message: string, tone?: ToastTone) {
  return render(
    <ToastProvider>
      <ShowToastButton message={message} tone={tone} />
    </ToastProvider>
  )
}

afterEach(() => {
  vi.useRealTimers()
})

describe('ToastProvider', () => {
  it('always mounts a polite live region, even with no toasts', () => {
    render(
      <ToastProvider>
        <p>content</p>
      </ToastProvider>
    )
    const viewport = screen.getByTestId('toast-viewport')
    expect(viewport).toHaveAttribute('role', 'status')
    expect(viewport).toHaveAttribute('aria-live', 'polite')
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('renders a shown toast inside the live region', () => {
    renderWithProvider('Nice work!')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))
    const viewport = screen.getByTestId('toast-viewport')
    expect(viewport).toHaveTextContent('Nice work!')
  })

  it('defaults to the info tone and applies the success tone when asked', () => {
    render(
      <ToastProvider>
        <ShowToastButton message="info message" />
        <ShowToastButton message="success message" tone="success" />
      </ToastProvider>
    )
    const showButtons = screen.getAllByRole('button', { name: 'show toast' })
    fireEvent.click(showButtons[0])
    fireEvent.click(showButtons[1])
    const toasts = screen.getAllByTestId('toast')
    expect(toasts[0].className).toContain('toast--info')
    expect(toasts[1].className).toContain('toast--success')
  })

  it('auto-dismisses a toast after 5 seconds', () => {
    vi.useFakeTimers()
    renderWithProvider('Bye soon')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))
    expect(screen.getByTestId('toast')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('dismisses immediately when the OK button is clicked', () => {
    renderWithProvider('Click me away')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))
    expect(screen.getByTestId('toast')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'OK' }))
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('pauses auto-dismiss while hovered and resumes a full window on leave', () => {
    vi.useFakeTimers()
    renderWithProvider('Hover pause')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))

    fireEvent.mouseEnter(screen.getByTestId('toast'))
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    // Well past the auto-dismiss window, but hovered: still here.
    expect(screen.getByTestId('toast')).toBeInTheDocument()

    fireEvent.mouseLeave(screen.getByTestId('toast'))
    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(screen.getByTestId('toast')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('pauses auto-dismiss while the OK button holds focus', () => {
    vi.useFakeTimers()
    renderWithProvider('Focus pause')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))

    // Real focus()/blur() so jsdom emits the bubbling focusin/focusout events
    // React's onFocus/onBlur listen for; fireEvent.focus would not bubble.
    const okButton = screen.getByRole('button', { name: 'OK' })
    act(() => {
      okButton.focus()
    })
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByTestId('toast')).toBeInTheDocument()

    act(() => {
      okButton.blur()
    })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('stays paused when hover ends while focus remains', () => {
    // A keyboard user who hovers the toast then tabs to its OK button is
    // both hovered and focused; if the mouse then moves away, the timer must
    // stay paused (not resume) because the button still holds focus.
    vi.useFakeTimers()
    renderWithProvider('Overlap pause')
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))

    fireEvent.mouseEnter(screen.getByTestId('toast'))
    const okButton = screen.getByRole('button', { name: 'OK' })
    act(() => {
      okButton.focus()
    })
    fireEvent.mouseLeave(screen.getByTestId('toast'))
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    // Well past the auto-dismiss window, but still focused: must still be here.
    expect(screen.getByTestId('toast')).toBeInTheDocument()

    act(() => {
      okButton.blur()
    })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('stacks multiple toasts and dismisses them independently', () => {
    renderWithProvider('First of two')
    const show = screen.getByRole('button', { name: 'show toast' })
    fireEvent.click(show)
    fireEvent.click(show)
    expect(screen.getAllByTestId('toast')).toHaveLength(2)

    fireEvent.click(screen.getAllByRole('button', { name: 'OK' })[0])
    expect(screen.getAllByTestId('toast')).toHaveLength(1)
  })
})

describe('useToast outside a ToastProvider', () => {
  it('throws a clear error', () => {
    // Silence React's console noise for the intentional render crash.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    expect(() => render(<ShowToastButton message="nope" />)).toThrow(
      'useToast must be used within a ToastProvider'
    )
    errorSpy.mockRestore()
  })
})
