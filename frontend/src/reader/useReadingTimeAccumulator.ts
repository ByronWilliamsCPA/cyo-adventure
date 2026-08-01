/**
 * Client reading-time accumulator (W3.3, gamification recommendation
 * 2026-08-01 section 2.4): the reader-side half of active-reading-time
 * measurement, feeding the day buckets `offline/readingTimeSync.ts`
 * accrues and flushes.
 *
 * "Active" per the recommendation: (a) this hook is mounted (the reader
 * route), (b) the document is foregrounded (`visibilityState === 'visible'`),
 * and (c) the most recent interaction is within the idle window, OR
 * read-aloud is actively playing (read-aloud counts as active with no taps,
 * or the 3-5 band -- read TO, not tapping -- would register zero).
 *
 * Interaction is both explicit (callers may call `recordInteraction()`
 * directly, e.g. on a choice tap or go-back) and passive: this hook attaches
 * `pointerdown`/`keydown`/`scroll` listeners to the given container ref, so
 * every tap inside the reader shell counts, including controls this hook's
 * touch scope does not extend to (text-size, theme) -- a tap on ANY control
 * inside the reader shell is an interaction regardless of which specific
 * control it lands on, satisfying the recommendation's interaction list
 * without this hook needing to instrument each control individually.
 */

import { useCallback, useEffect, useRef } from 'react'
import type { RefObject } from 'react'

import { accrueReadingTime, flushAllReadingTime, type ReadingTimeApi } from '../offline/readingTimeSync'

// #ASSUME: timing dependencies: 90 seconds, per the recommendation's own
// number ("long enough for a slow reader on a long passage at the teen
// bands, short enough that a tablet left open on the sofa does not accrue
// hours"). Not user-configurable; a future band-specific tuning would live
// here.
// #VERIFY: useReadingTimeAccumulator.test.ts "stops accruing once the idle
// window elapses with no interaction".
export const IDLE_WINDOW_MS = 90_000

// How often the accumulator wakes to check activity and, if active, credit
// elapsed time to today's bucket. Short enough that a child who reads for
// only a minute or two still accrues a meaningful bucket before leaving;
// long enough not to spam IndexedDB writes or the flush endpoint.
// #ASSUME: timing dependencies: a tick credits exactly TICK_INTERVAL_MS of
// wall time when active, not the ACTUAL elapsed time since the last tick
// (which browser timer throttling, e.g. a backgrounded/throttled tab, can
// make longer than the nominal interval). This can under-count slightly on a
// throttled tab; acceptable for a literacy signal, not a billing ledger, and
// the alternative (crediting actual elapsed wall time) would let a laptop
// that slept mid-read credit the whole sleep duration as active reading.
// #VERIFY: useReadingTimeAccumulator.test.ts pins the per-tick credit at
// exactly TICK_INTERVAL_MS / 1000 seconds.
export const TICK_INTERVAL_MS = 5_000

// Flush at most this often; every active tick attempts a flush is unnecessary
// network chatter, but waiting too long risks losing the opportunistic-sync
// promise if the tab closes between flushes. A multiple of TICK_INTERVAL_MS
// so the flush check aligns with tick boundaries.
export const FLUSH_INTERVAL_MS = 30_000

/** Reader-local calendar date (device timezone, not UTC) as `YYYY-MM-DD`.
 * #ASSUME: data integrity: matches offline/db.ts::ReadingTimeDayBucket's own
 * documented assumption; see that type for the rationale and the accepted
 * imprecision at a local-midnight or DST boundary.
 * #VERIFY: useReadingTimeAccumulator.test.ts "buckets by the injected clock's
 * local date". */
export function readerLocalDate(now: Date): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export interface ReadingTimeAccumulatorOptions {
  /** The reading child's own profile id. */
  profileId: string
  /** The flush port. When omitted entirely, the hook still accrues locally
   * (so a caller that has not wired the network port yet loses nothing) but
   * never attempts a flush. */
  api?: ReadingTimeApi
  /** Guardian per-profile "pause time capture" toggle (resolved gamification
   * settings, `GET /me/progress`). True suspends BOTH accrual and flush
   * entirely: no ticking happens at all, matching the recommendation
   * section 4 table's "a separate toggle for families who want none of it
   * recorded". */
  paused?: boolean
  /** True while read-aloud is actively speaking (useReadAloud's `speaking`).
   * Counts as interaction with no taps required. */
  isReadAloudPlaying?: boolean
  /** The reader shell container; pointerdown/keydown/scroll inside it count
   * as interaction. Omitted (e.g. a caller with nothing to attach to yet)
   * degrades to explicit `recordInteraction()` calls only. */
  containerRef?: RefObject<HTMLElement | null>
  /** Injectable clock, for deterministic tests. Defaults to `() => new Date()`. */
  now?: () => Date
  /** Injectable device id, forwarded to each flush. */
  deviceId?: string
}

export interface ReadingTimeAccumulator {
  /** Marks this instant as an interaction, resetting the idle window. Safe
   * to call at any time, including while paused (a no-op then). */
  recordInteraction: () => void
}

function defaultNow(): Date {
  return new Date()
}

/**
 * Accumulate active reading seconds into day buckets and flush them
 * opportunistically. See the module doc for the exact "active" definition.
 *
 * #CRITICAL: timing dependencies: the timer, the visibilitychange listener,
 * and the interaction listeners are all torn down on unmount (the effect
 * cleanup), and a final flush is attempted then too -- a component that
 * mounts and unmounts this hook repeatedly (route changes) must never leak
 * an interval or double-count a tick from an orphaned timer still firing
 * against a bucket a different mount now owns.
 * #VERIFY: useReadingTimeAccumulator.test.ts "clears its timer and listeners
 * on unmount" and "flushes once on unmount".
 */
export function useReadingTimeAccumulator({
  profileId,
  api,
  paused = false,
  isReadAloudPlaying = false,
  containerRef,
  now = defaultNow,
  deviceId,
}: ReadingTimeAccumulatorOptions): ReadingTimeAccumulator {
  const lastInteractionAtRef = useRef<number>(now().getTime())
  const lastFlushAtRef = useRef<number>(0)
  // Mirrors the latest prop values into refs so the interval callback (set up
  // once per mount, not re-created every render) always reads the current
  // values instead of a stale closure over the render that started it.
  // Written from an effect (not during render itself): mutating a ref's
  // `.current` while rendering is a react-hooks/refs violation, even though
  // these refs are otherwise only ever read from an async timer/event
  // callback, never during render.
  const pausedRef = useRef(paused)
  const readAloudRef = useRef(isReadAloudPlaying)
  const apiRef = useRef(api)
  useEffect(() => {
    pausedRef.current = paused
  }, [paused])
  useEffect(() => {
    readAloudRef.current = isReadAloudPlaying
  }, [isReadAloudPlaying])
  useEffect(() => {
    apiRef.current = api
  }, [api])

  const recordInteraction = useCallback(() => {
    lastInteractionAtRef.current = now().getTime()
  }, [now])

  // Passive interaction listeners scoped to the reader shell (see module
  // doc): covers choice taps, go-back, scroll, and any other control inside
  // the shell (text-size, theme) without this hook needing to instrument
  // each one individually.
  useEffect(() => {
    const el = containerRef?.current
    if (!el) return
    const handler = () => recordInteraction()
    el.addEventListener('pointerdown', handler, { passive: true })
    el.addEventListener('keydown', handler)
    el.addEventListener('scroll', handler, { passive: true })
    return () => {
      el.removeEventListener('pointerdown', handler)
      el.removeEventListener('keydown', handler)
      el.removeEventListener('scroll', handler)
    }
  }, [containerRef, recordInteraction])

  const attemptFlush = useCallback(() => {
    const currentApi = apiRef.current
    if (currentApi === undefined) return
    void flushAllReadingTime(currentApi, profileId, { deviceId }).catch((error: unknown) => {
      // Best-effort: a flush failure must never surface to the reader UI.
      // offline/readingTimeSync.ts itself already keeps unsynced seconds
      // safely pending for the next opportunity; this catch only guards
      // against an unexpected throw escaping that module's own handling.
      console.error('[reading-time] opportunistic flush failed', { profileId, error })
    })
  }, [profileId, deviceId])

  // The tick loop: while mounted and not paused, wake every TICK_INTERVAL_MS,
  // credit elapsed active time (if any) to today's bucket, and flush
  // opportunistically at most every FLUSH_INTERVAL_MS.
  useEffect(() => {
    if (paused) return
    const interval = setInterval(() => {
      if (pausedRef.current) return
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      const nowMs = now().getTime()
      const idle = nowMs - lastInteractionAtRef.current > IDLE_WINDOW_MS
      const active = readAloudRef.current || !idle
      if (active) {
        void accrueReadingTime(profileId, readerLocalDate(now()), TICK_INTERVAL_MS / 1000).catch(
          (error: unknown) => {
            console.error('[reading-time] accrual failed', { profileId, error })
          }
        )
      }
      if (nowMs - lastFlushAtRef.current >= FLUSH_INTERVAL_MS) {
        lastFlushAtRef.current = nowMs
        attemptFlush()
      }
    }, TICK_INTERVAL_MS)
    return () => {
      clearInterval(interval)
    }
  }, [paused, profileId, now, attemptFlush])

  // Pause immediately on visibilitychange to hidden (do not wait for the
  // next tick), and take the opportunity to flush what has accrued so far.
  useEffect(() => {
    if (typeof document === 'undefined') return
    const handler = () => {
      if (document.visibilityState === 'hidden') {
        attemptFlush()
      } else {
        // Coming back to the foreground counts as an interaction: a child
        // who switched apps and returned did not "idle out" the story.
        recordInteraction()
      }
    }
    document.addEventListener('visibilitychange', handler)
    return () => {
      document.removeEventListener('visibilitychange', handler)
    }
  }, [attemptFlush, recordInteraction])

  // Pause immediately on unmount (the interval's own cleanup above already
  // stops future ticks) and attempt one final opportunistic flush so a
  // child who leaves the reader mid-session does not strand accrued seconds
  // until their next visit.
  useEffect(() => {
    return () => {
      attemptFlush()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { recordInteraction }
}
