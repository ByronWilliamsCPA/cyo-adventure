import { useEffect, useId, useRef, type ReactNode } from 'react'
import './Dialog.css'

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

    const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )
    firstFocusable?.focus()

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return

      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])',
      )
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
    <div
      className="cyo-dialog-backdrop"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="cyo-dialog"
        onClick={(e) => e.stopPropagation()}
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
