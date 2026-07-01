import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Dialog, type DialogProps } from './Dialog'

function renderDialog(overrides: Partial<DialogProps> = {}) {
  const onClose = vi.fn()
  const utils = render(
    <Dialog title="Chapter complete!" onClose={onClose} actions={<button type="button">Continue</button>} {...overrides}>
      <p>You reached the end of this chapter.</p>
    </Dialog>,
  )
  return { onClose, ...utils }
}

describe('Dialog', () => {
  it('renders title, children, and actions when open', () => {
    renderDialog()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Chapter complete!')).toBeInTheDocument()
    expect(screen.getByText('You reached the end of this chapter.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
  })

  it('renders nothing when open is false', () => {
    renderDialog({ open: false })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('calls onClose when the backdrop is clicked', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not call onClose when the dialog content is clicked', () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when Escape is pressed', () => {
    const { onClose } = renderDialog()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('moves focus to the first tabbable element on open', () => {
    renderDialog()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Continue' }))
  })

  it('falls back to focusing the dialog container when there are no tabbable children', () => {
    renderDialog({ actions: null, children: <p>No interactive elements here.</p> })
    expect(document.activeElement).toBe(screen.getByRole('dialog'))
  })

  it('wraps focus from the last to the first tabbable element on Tab', () => {
    renderDialog({
      actions: (
        <>
          <button type="button">First</button>
          <button type="button">Last</button>
        </>
      ),
    })
    const last = screen.getByRole('button', { name: 'Last' })
    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'First' }))
  })

  it('wraps focus from the first to the last tabbable element on Shift+Tab', () => {
    renderDialog({
      actions: (
        <>
          <button type="button">First</button>
          <button type="button">Last</button>
        </>
      ),
    })
    const first = screen.getByRole('button', { name: 'First' })
    first.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Last' }))
  })

  it('restores focus to the previously focused element on close', () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    const { rerender, onClose } = renderDialog()
    expect(document.activeElement).not.toBe(trigger)

    rerender(
      <Dialog title="Chapter complete!" onClose={onClose} open={false} actions={<button type="button">Continue</button>}>
        <p>You reached the end of this chapter.</p>
      </Dialog>,
    )
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })
})
