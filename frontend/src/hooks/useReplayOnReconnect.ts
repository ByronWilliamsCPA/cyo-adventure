import { useEffect, useRef } from 'react'
import {
  QUEUE_APPENDED_EVENT,
  replayQueue,
  type ReplayOutcome,
  type SyncApi,
} from '../offline/sync'

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
async function withReplayLock(
  fn: () => Promise<ReplayOutcome>
): Promise<ReplayOutcome | undefined> {
  const locks = navigator.locks as LockManager | undefined
  if (!locks?.request) return fn()
  return locks.request('cyo-replay', { ifAvailable: true }, async (lock) =>
    lock === null ? undefined : fn()
  )
}

/**
 * Flush queued offline writes on mount, whenever connectivity returns, and
 * whenever a write is appended while the device is online.
 *
 * The third trigger is what keeps an append from stranding. `navigator.onLine`
 * does not move for a request timeout, a DNS failure or a dropped socket, so
 * those raise OfflineError and queue a write without ever producing an 'online'
 * event; once the row has a queued write every later save appends behind it, and
 * before this listener existed nothing drained the queue until the next reader
 * mount. Routing the append through this hook rather than calling replayQueue
 * from saveProgress keeps both guards below (the in-tab `busy` flag and the
 * cross-tab Web Lock) on every drain.
 */
export function useReplayOnReconnect(
  api: SyncApi,
  onOutcome: (outcome: ReplayOutcome) => void
): void {
  const busy = useRef(false)
  // Set when a trigger arrives while a drain is already running, so the drain
  // repeats instead of dropping it.
  const rerun = useRef(false)
  useEffect(() => {
    let cancelled = false
    async function flush(): Promise<void> {
      // #CRITICAL: concurrency: coalesce rather than drop. replayQueue re-lists
      // the queue between passes, so an append made mid-drain is usually picked
      // up by the drain itself; the exception is an append that commits after
      // the LAST pass read an empty queue but before `busy` is released, which
      // this flag catches. Dropping it would strand the write with no further
      // trigger (the device never went offline, so no 'online' event follows).
      // #VERIFY: useReplayOnReconnect.test.ts "repeats the drain for a trigger
      // that arrived while one was in flight" resolves the in-flight drain and
      // asserts a second replayQueue call with no further event dispatched.
      if (busy.current) {
        rerun.current = true
        return
      }
      busy.current = true
      try {
        do {
          rerun.current = false
          const outcome = await withReplayLock(() => replayQueue(api))
          // undefined = another tab holds the replay lock; it will drain, and
          // repeating here would only spin against a lock we cannot take.
          if (outcome === undefined) return
          const nonEmpty =
            outcome.replayed > 0 || outcome.conflicts.length > 0 || outcome.failed.length > 0
          if (!cancelled && nonEmpty) onOutcome(outcome)
        } while (rerun.current)
      } finally {
        busy.current = false
      }
    }
    // flush() owns its failures: replayQueue can reject on an IndexedDB fault,
    // and an unhandled rejection here is invisible (no outcome, no log, no
    // banner). Log it so a wedged queue is diagnosable.
    const run = () => {
      void flush().catch((cause: unknown) => {
        console.error('[reader] offline replay failed', { cause })
      })
    }
    run()
    window.addEventListener('online', run)
    window.addEventListener(QUEUE_APPENDED_EVENT, run)
    return () => {
      cancelled = true
      window.removeEventListener('online', run)
      window.removeEventListener(QUEUE_APPENDED_EVENT, run)
    }
  }, [api, onOutcome])
}
