import { createContext } from 'react'

/**
 * Success and info tones only, on purpose: danger/error feedback stays inline
 * next to whatever failed (e.g. ReaderRoute's replay-failed banner), matching
 * the app's existing error patterns. A toast is for confirming that a
 * background/async action finished, not for surfacing problems.
 */
export type ToastTone = 'success' | 'info'

export interface ToastOptions {
  /** Visual tone of the toast. Defaults to 'info'. */
  tone?: ToastTone
}

export interface ToastContextValue {
  /**
   * Enqueues a toast in the always-mounted viewport. Toasts auto-dismiss
   * after a few seconds (paused while hovered or focused) and always carry a
   * manual "OK" button so a reader can dismiss them sooner.
   */
  showToast: (message: string, options?: ToastOptions) => void
}

export const ToastContext = createContext<ToastContextValue | undefined>(undefined)
