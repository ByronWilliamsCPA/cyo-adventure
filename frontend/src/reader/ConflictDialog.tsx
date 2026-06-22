/**
 * The multi-device save-conflict dialog (offline-conflict-ux.md section 1).
 *
 * Shown when a reading-state save returns 409 because another device advanced the
 * same story. Modal and blocking: the reader must choose, so no progress is lost
 * without a decision. The two actions map to the server-contract options
 * `continue_from_this_device` and `use_newer_progress`.
 */

import { useEffect, useRef } from 'react'

export interface ConflictDialogProps {
  onKeepThisDevice: () => void
  onUseNewest: () => void
}

export function ConflictDialog({ onKeepThisDevice, onUseNewest }: ConflictDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const firstButtonRef = useRef<HTMLButtonElement>(null)

  // Focus management for a blocking modal: focus the first action on open, trap
  // Tab within the dialog, and restore focus to the trigger on close. The reader
  // must choose, so the dialog deliberately does not dismiss on Escape.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    firstButtonRef.current?.focus()

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== 'Tab') return
      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>('button')
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
  }, [])

  return (
    <div
      ref={dialogRef}
      data-testid="conflict-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-title"
      className="conflict-dialog"
    >
      <h2 id="conflict-title">You were reading on another device</h2>
      <p>
        Your place in this story is different here than on your other device. Which one do you want
        to keep?
      </p>
      <div className="conflict-actions">
        <button
          ref={firstButtonRef}
          type="button"
          data-testid="conflict-keep"
          onClick={onKeepThisDevice}
        >
          Keep this device
        </button>
        <button type="button" data-testid="conflict-use-newest" onClick={onUseNewest}>
          Use the newest place
        </button>
      </div>
    </div>
  )
}
