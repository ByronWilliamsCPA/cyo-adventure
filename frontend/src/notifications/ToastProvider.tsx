import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import {
  ToastContext,
  type ToastContextValue,
  type ToastOptions,
  type ToastTone,
} from './toastContext'
import './toast.css'

/** How long a toast stays up before dismissing itself. */
const TOAST_AUTO_DISMISS_MS = 5000

interface ToastEntry {
  id: number
  message: string
  tone: ToastTone
}

/**
 * Global toast provider + viewport. Mounted ONCE at the app root (App.tsx),
 * wrapping the router, so any route component can call useToast(); the
 * viewport renders alongside the routed surface as a fixed bottom-center
 * stack (the shells all keep their chrome at the top, so the bottom edge is
 * free on every surface).
 *
 * The viewport is an always-mounted polite live region: because the region
 * exists BEFORE a toast is appended, screen readers announce the new content
 * instead of ignoring a freshly-inserted region.
 *
 * Built in the app (not the design-system workspace) as a future promotion
 * candidate; visuals come from the shared tokens so promoting it later is a
 * file move, not a redesign.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([])
  const nextIdRef = useRef(0)

  const showToast = useCallback((message: string, options?: ToastOptions) => {
    const id = nextIdRef.current
    nextIdRef.current += 1
    setToasts((current) => [...current, { id, message, tone: options?.tone ?? 'info' }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  // Stable context value: consumers memoize callbacks on showToast (e.g.
  // ReaderRoute's handleReplayOutcome, which sits in useReplayOnReconnect's
  // effect deps), so a fresh object per render would re-fire those effects.
  const value = useMemo<ToastContextValue>(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" role="status" aria-live="polite" data-testid="toast-viewport">
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={dismissToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastCard({ toast, onDismiss }: { toast: ToastEntry; onDismiss: (id: number) => void }) {
  // Hover or focus anywhere inside the toast pauses auto-dismiss (a slow
  // reader mid-sentence must not have the message vanish under the pointer).
  // Un-pausing restarts the full window rather than resuming a remainder:
  // simpler, and it only ever grants MORE reading time, never less.
  //
  // Hover and focus are tracked independently, not as one shared boolean: a
  // keyboard user who hovers the toast and then tabs to its OK button is
  // still hovering AND focused; if the mouse then moves away, a single
  // shared flag would clear on mouseleave and resume the dismiss timer out
  // from under their still-focused button. Pause holds as long as either is
  // true, and only clears once both let go.
  // #CRITICAL: timing dependencies: never resume the dismiss timer while the
  // toast still holds keyboard focus, or a focused control can vanish under
  // the reader mid-interaction.
  // #VERIFY: ToastProvider.test.tsx "stays paused when hover ends while focus
  // remains" (hover then focus then mouse-leave must not resume the timer).
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const paused = hovered || focused

  useEffect(() => {
    if (paused) return undefined
    const timer = window.setTimeout(() => {
      onDismiss(toast.id)
    }, TOAST_AUTO_DISMISS_MS)
    return () => {
      window.clearTimeout(timer)
    }
  }, [paused, onDismiss, toast.id])

  return (
    <div
      className={`toast toast--${toast.tone}`}
      data-testid="toast"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      <span className="toast__message">{toast.message}</span>
      {/* "OK", not "Dismiss": young kids read this button too. */}
      <button type="button" className="toast__ok" onClick={() => onDismiss(toast.id)}>
        OK
      </button>
    </div>
  )
}
