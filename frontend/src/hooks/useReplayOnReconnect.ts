import { useEffect, useRef } from 'react'
import { replayQueue, type ReplayOutcome, type SyncApi } from '../offline/sync'

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
        const outcome = await replayQueue(api)
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
