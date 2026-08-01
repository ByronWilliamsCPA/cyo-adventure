/**
 * Active-reading-time accrual and idempotent flush (W3.3, gamification
 * recommendation 2026-08-01 section 2.4).
 *
 * Mirrors `offline/sync.ts`'s shape deliberately: `OfflineError` (reused, not
 * redefined) distinguishes "no network" from a real HTTP failure, and a
 * flush attempt is idempotent via a client-minted `flush_id`, exactly like a
 * queued reading-state write's `event_id`. The two differ in what "replay"
 * means: a reading-state write replays a FIXED body; a reading-time flush
 * replays a FIXED (flush_id, delta) pair frozen at the moment the attempt was
 * minted (`PendingReadingTimeFlush`, offline/db.ts), so newly-accrued seconds
 * during a retry window are never silently folded into an already-dispatched
 * delta -- they wait for the NEXT attempt, minted only once this one
 * resolves (success or a genuine drop).
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import {
  getReadingTimeBucket,
  listReadingTimeBuckets,
  putReadingTimeBucket,
  type ReadingTimeDayBucket,
} from './db'
import { OfflineError } from './sync'

export interface ReadingTimeFlushResult {
  activity_date: string
  active_seconds: number
  updated_at: string
  /**
   * Seconds of THIS flush's delta the server took responsibility for, by
   * recording them or by discarding them under the guardian pause policy.
   * Optional so a client running against a server that predates the field
   * keeps its old optimistic behaviour instead of retrying forever.
   */
  settled_seconds?: number
}

/** The network port this module depends on (a hand-typed adapter over axios;
 * `POST /v1/me/reading-time` has not yet been regenerated into
 * `src/client/` with this shape -- see `makeReadingTimeApi`'s own note). */
export interface ReadingTimeApi {
  flush(
    date: string,
    secondsDelta: number,
    flushId: string,
    deviceId?: string
  ): Promise<ReadingTimeFlushResult>
}

// #ASSUME: external resources: `POST /v1/me/reading-time`
// (src/cyo_adventure/api/reading_time.py) is in the regenerated client
// (`ReadingActivityDayView` in src/client/types.gen.ts); this hand-typed
// shape is retained like frontend/src/kid/storyStatusApi.ts for its
// narrowed types. Follow-up: assert parity in apiContractParity.ts.
// #VERIFY: reading_time.py's ReadingTimeFlushBody/ReadingActivityDayView are
// the source of truth this hand-typed shape must track.
export function makeReadingTimeApi(api: AxiosInstance): ReadingTimeApi {
  return {
    async flush(date, secondsDelta, flushId, deviceId) {
      try {
        const res = await api.post<ReadingTimeFlushResult>('/v1/me/reading-time', {
          date,
          seconds_delta: secondsDelta,
          flush_id: flushId,
          device_id: deviceId,
        })
        return res.data
      } catch (error) {
        // Same convention as api/readerApi.ts::makeSyncApi: no HTTP response
        // means a transport failure (offline/timeout), signalled distinctly
        // so only a true offline condition leaves the flush pending for
        // retry. An HTTP error response (auth/validation/server) propagates
        // as itself.
        if (isAxiosError(error) && !error.response) {
          throw new OfflineError()
        }
        throw error
      }
    },
  }
}

function defaultFlushId(): string {
  return crypto.randomUUID()
}

/**
 * Accrue local active-reading seconds into a profile's (reader-local date)
 * bucket. Pure local-storage bookkeeping; never talks to the network, so
 * offline reading accrues exactly like online reading (the recommendation's
 * explicit requirement).
 *
 * #CRITICAL: data-integrity: this ONLY ever grows `seconds`; it never
 * touches `syncedSeconds` or `pending`, so a flush failure can never lose
 * locally-accrued time, and a burst of accrual calls during an in-flight
 * flush attempt is safe (the next flush picks up the growth once the current
 * pending attempt resolves).
 * #VERIFY: offline/readingTimeSync.test.ts "accrual during a pending flush
 * is not lost".
 */
export async function accrueReadingTime(
  profileId: string,
  date: string,
  seconds: number
): Promise<void> {
  if (seconds <= 0) return
  const existing = await getReadingTimeBucket(profileId, date)
  const bucket: ReadingTimeDayBucket = existing ?? {
    profileId,
    date,
    seconds: 0,
    syncedSeconds: 0,
    pending: null,
  }
  await putReadingTimeBucket({ ...bucket, seconds: bucket.seconds + seconds })
}

export interface FlushOptions {
  deviceId?: string
  /** Injectable id factory for deterministic tests; defaults to crypto.randomUUID. */
  newId?: () => string
}

/**
 * Attempt to flush one bucket's unsynced seconds. Safe to call repeatedly
 * and opportunistically (on a timer, on `online`, on unmount): a bucket with
 * nothing unsynced is a no-op; an already-pending attempt is retried with
 * the EXACT SAME (flush_id, delta) the server may already be mid-processing;
 * a fresh delta is only minted once no attempt is pending.
 *
 * #CRITICAL: concurrency: `pending` is written to IndexedDB BEFORE the
 * network call, so a page reload or crash mid-flight leaves a resumable
 * pending attempt behind rather than an orphaned in-flight request nothing
 * will ever retry the seconds for.
 * #VERIFY: offline/readingTimeSync.test.ts "a pending attempt survives
 * across separate flush calls with the same flush_id and delta";
 * "a non-offline failure drops pending and the next flush recomputes from
 * the unadvanced synced baseline".
 */
export async function flushReadingTimeBucket(
  api: ReadingTimeApi,
  bucket: ReadingTimeDayBucket,
  opts: FlushOptions = {}
): Promise<void> {
  const mint = opts.newId ?? defaultFlushId
  let working = bucket
  let attempt = bucket.pending
  if (attempt === null) {
    if (bucket.seconds <= bucket.syncedSeconds) return
    attempt = {
      flushId: mint(),
      deltaSeconds: bucket.seconds - bucket.syncedSeconds,
      snapshotSeconds: bucket.seconds,
    }
    working = { ...bucket, pending: attempt }
    await putReadingTimeBucket(working)
  }
  let result: ReadingTimeFlushResult
  try {
    result = await api.flush(working.date, attempt.deltaSeconds, attempt.flushId, opts.deviceId)
  } catch (error) {
    if (error instanceof OfflineError) {
      // Still offline: leave `pending` exactly as stored for the next
      // opportunistic attempt to retry verbatim.
      return
    }
    // Non-offline failure (auth/validation/server): this specific attempt
    // cannot succeed by retrying it verbatim. Drop `pending` (NOT
    // `syncedSeconds`, which stays at its last-acknowledged value) so the
    // next flush call recomputes a fresh delta spanning this failed range
    // plus anything accrued since, under a new flush_id, instead of wedging
    // forever on one bad request (mirrors offline/sync.ts::replayQueue's
    // non-offline branch).
    console.error('[reading-time] flush failed', {
      profileId: working.profileId,
      date: working.date,
      error,
    })
    await putReadingTimeBucket({ ...working, pending: null })
    return
  }
  // #CRITICAL: data-integrity: advance the baseline by what the SERVER settled,
  // never by the local snapshot. `POST /v1/me/reading-time` clamps a delta to a
  // plausibility ceiling (api/reading_time.py::_clamp_seconds_delta), so
  // assuming the full delta landed marked clamped-away seconds as synced and
  // deleted them: `accrueReadingTime` only ever grows `seconds`, so nothing
  // else would ever re-send them. Anything unsettled stays above the baseline
  // and rides along in the next flush's delta, which succeeds once the
  // server-side ceiling has grown.
  // #VERIFY: offline/readingTimeSync.test.ts "a clamped flush leaves the
  // unsettled remainder to be retried".
  const settled = Math.max(
    0,
    Math.min(attempt.deltaSeconds, result.settled_seconds ?? attempt.deltaSeconds)
  )
  await putReadingTimeBucket({
    ...working,
    syncedSeconds: working.syncedSeconds + settled,
    pending: null,
  })
}

/**
 * Flush every bucket for a profile that has unsynced seconds (a pending
 * attempt or `seconds > syncedSeconds`). Best-effort per bucket: one
 * bucket's failure never stops the others (a stuck day should not strand
 * every other day's data).
 */
export async function flushAllReadingTime(
  api: ReadingTimeApi,
  profileId: string,
  opts: FlushOptions = {}
): Promise<void> {
  const buckets = await listReadingTimeBuckets(profileId)
  for (const bucket of buckets) {
    if (bucket.pending === null && bucket.seconds <= bucket.syncedSeconds) continue
    await flushReadingTimeBucket(api, bucket, opts)
  }
}
