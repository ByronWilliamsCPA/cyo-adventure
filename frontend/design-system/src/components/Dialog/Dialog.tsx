import { useEffect, useId, useRef, type ReactNode } from 'react'
import './Dialog.css'

// The set of natively-tabbable elements the focus trap treats as its
// boundary. `textarea` MUST be included: the Send Back (reason) and Edit
// passage dialogs are textarea-primary, and omitting it left them
// keyboard-inoperable (WCAG 2.1.1, Level A) and let Shift+Tab leak focus out
// of the modal. Kept as one constant so the initial-focus and Tab-wrap
// queries can never drift apart again.
const FOCUSABLE_SELECTOR =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

export interface DialogProps {
  title: string
  children: ReactNode
  actions: ReactNode
  open?: boolean
  onClose: () => void
}

export function Dialog({ title, children, actions, open = true, onClose }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  // #ASSUME: timing dependency: callers frequently pass an inline onClose,
  // giving a new function identity every render.
  // #VERIFY: keep onClose out of the effect's dependency array (via ref) so
  // the focus-trap setup only re-runs on open/close, not on every re-render.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return

    const previouslyFocused = document.activeElement as HTMLElement | null

    const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
    // #EDGE: a11y: children/actions may render zero tabbable elements.
    // #VERIFY: fall back to focusing the dialog container itself so focus
    // always moves inside the modal, keeping the trap effective.
    ;(firstFocusable ?? dialogRef.current)?.focus()

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return

      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      if (!focusables || focusables.length === 0) return

      const first = focusables[0]
      const last = focusables[focusables.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [open])

  if (!open) return null

  return (
    // The backdrop is decorative: role="presentation" keeps it out of the
    // accessibility tree, which is correct because it carries no information
    // and must not be a tab stop. Dismissal is not lost for keyboard users:
    // the Escape branch of onKeyDown above closes the dialog, and that is the
    // keyboard equivalent of the backdrop click, not something a listener on
    // this div could provide.
    //
    // Closing is gated on `target === currentTarget` (the click landed on the
    // backdrop itself, not bubbled up from inside) rather than on a
    // stopPropagation handler attached to the dialog. That handler was a
    // mouse-event listener on a role="dialog" element, which is a
    // non-interactive role, so it both tripped jsx-a11y and put behaviour on
    // an element that should have none. This form needs no listener there.
    <div
      className="cyo-dialog-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="cyo-dialog"
        tabIndex={-1}
      >
        <h2 id={titleId} className="cyo-dialog__title">
          {title}
        </h2>
        <div className="cyo-dialog__body">{children}</div>
        <div className="cyo-dialog__actions">{actions}</div>
      </div>
    </div>
  )
}
