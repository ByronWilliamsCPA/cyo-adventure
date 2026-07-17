import { useEffect, useRef } from 'react'
import { replayQueue, type ReplayOutcome, type SyncApi } from '../offline/sync'

/**
 * Run `fn` while holding the cross-tab replay lock (ARCH-M4).
 *
 * Two tabs replaying the same offline queue concurrently interleave rebases and
 * manufacture spurious conflicts. `navigator.locks` serializes them across tabs;
 * `ifAvailable` means a tab that cannot get the lock (another tab is mid-replay)
 * skips this round rather than queueing, returning `undefined`. Environments
 * without the Web Locks API (older browsers, jsdom) fall back to running `fn`
 * directly, relying on the in-tab `busy` guard alone as before.
 */
async function withReplayLock(fn: () => Promise<ReplayOutcome>): Promise<ReplayOutcome | undefined> {
  const locks = navigator.locks as LockManager | undefined
  if (!locks?.request) return fn()
  return locks.request('cyo-replay', { ifAvailable: true }, async (lock) =>
    lock === null ? undefined : fn()
  )
}

/** Flush queued offline writes on mount and whenever connectivity returns. */
export function useReplayOnReconnect(
  api: SyncApi,
  onOutcome: (outcome: ReplayOutcome) => void
): void {
  const busy = useRef(false)
  useEffect(() => {
    let cancelled = false
    async function flush(): Promise<void> {
      if (busy.current) return
      busy.current = true
      try {
        const outcome = await withReplayLock(() => replayQueue(api))
        // undefined = another tab holds the replay lock; skip quietly this round.
        if (outcome === undefined) return
        const nonEmpty =
          outcome.replayed > 0 || outcome.conflicts.length > 0 || outcome.failed.length > 0
        if (!cancelled && nonEmpty) onOutcome(outcome)
      } finally {
        busy.current = false
      }
    }
    void flush()
    const onOnline = () => {
      void flush()
    }
    window.addEventListener('online', onOnline)
    return () => {
      cancelled = true
      window.removeEventListener('online', onOnline)
    }
  }, [api, onOutcome])
}
