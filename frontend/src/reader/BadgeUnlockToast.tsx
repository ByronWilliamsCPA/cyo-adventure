/**
 * Badge-unlock toast (W3.2): shown at the ending screen when a completion
 * earns a new badge. Purely presentational and celebratory -- no dismiss
 * consequence, no repeat mechanic, nothing punitive (K14). "Seen" state
 * (so a badge never re-toasts) lives client-side in IndexedDB
 * (`offline/db.ts`'s `badge_seen` store), read/written by the caller before
 * this component ever mounts; this component itself has no storage
 * awareness, it just renders the one badge it was handed.
 */

import { useEffect, useRef } from 'react'

import { Mascot } from '../kid/Mascot'
import type { EarnedBadgeCard } from '../kid/progressApi'
import './badgeUnlockToast.css'

export interface BadgeUnlockToastProps {
  badge: EarnedBadgeCard
  onDismiss: () => void
  /** Auto-dismiss delay in ms; 0 disables auto-dismiss (tests, reduced motion
   * callers that prefer a manual close only). Defaults to a generous 8s so a
   * young reader has time to read it without it feeling naggy or sticking
   * around forever. */
  autoDismissMs?: number
}

export function BadgeUnlockToast({
  badge,
  onDismiss,
  autoDismissMs = 8000,
}: BadgeUnlockToastProps) {
  // #ASSUME: timing dependency: the only call site (Reader.tsx) passes an
  // inline `onDismiss={() => onDismissBadgeToast?.()}`, so the prop has a new
  // identity on every parent render. With it in the dependency array the
  // effect tore down and rebuilt the timer each time, restarting the 8s
  // countdown from zero; a reader whose ending screen re-renders more often
  // than every 8s would never see the toast auto-dismiss at all.
  // #VERIFY: keep onDismiss out of the dependency array (via ref) so the
  // timer is armed once per mount. Covered by BadgeUnlockToast.test.tsx
  // "auto-dismisses on schedule even when the parent re-renders".
  const onDismissRef = useRef(onDismiss)
  useEffect(() => {
    onDismissRef.current = onDismiss
  })

  useEffect(() => {
    if (autoDismissMs <= 0) return
    const timer = setTimeout(() => onDismissRef.current(), autoDismissMs)
    return () => clearTimeout(timer)
  }, [autoDismissMs])

  return (
    <div
      className="badge-unlock-toast"
      role="status"
      aria-live="polite"
      data-testid="badge-unlock-toast"
    >
      <Mascot size={48} className="badge-unlock-toast__mascot" />
      <div className="badge-unlock-toast__text">
        <p className="badge-unlock-toast__title">New badge!</p>
        <p className="badge-unlock-toast__name">{badge.name}</p>
        <p className="badge-unlock-toast__description">{badge.description}</p>
      </div>
      <button
        type="button"
        className="badge-unlock-toast__close"
        aria-label="Dismiss"
        onClick={onDismiss}
      >
        ×
      </button>
    </div>
  )
}
