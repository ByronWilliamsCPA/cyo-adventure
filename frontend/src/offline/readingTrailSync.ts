/**
 * Reading-trail transport: send a batch now, or queue it for the existing
 * offline replay (privacy-model.md "Reading trail").
 *
 * Mirrors offline/sync.ts::saveProgress's shape: try the network first, and on
 * an offline failure append to the shared `offline_queue` store and kick the
 * drain via QUEUE_APPENDED_EVENT; `replayQueue` (via useReplayOnReconnect)
 * sends it later. Unlike a reading-state save, nothing here is ever surfaced
 * to the reader: every function resolves, never rejects, and logs only a
 * status summary, never trail content.
 *
 * #CRITICAL: data-integrity: recording is best-effort and must never block,
 * slow, or interrupt reading. Callers fire and forget; this module swallows
 * every failure, including IndexedDB faults, and reports an outcome instead.
 * #VERIFY: readingTrailSync.test.ts "never rejects, even when the queue write
 * fails".
 */

import { type AxiosInstance, isAxiosError } from 'axios'

import type { ReadingTrailBatchBody, ReadingTrailIngestView } from '../client/types.gen'
import { enqueueTrailBatch } from './db'
import { OfflineError, QUEUE_APPENDED_EVENT, type ReadingTrailApi } from './sync'

/** What happened to one batch. `disabled`: the server records nothing in this
 * environment (Settings.reading_trail_enabled is off), so stop sending. */
export type TrailSendOutcome = 'recorded' | 'disabled' | 'queued' | 'dropped'

/**
 * Build the network port over the shared axios instance (which picks the
 * child-session bearer, like every other reader request).
 *
 * Throws OfflineError for a transport failure, a 5xx, or a 429, all of which
 * may succeed later; any other HTTP error propagates as itself and the caller
 * drops the batch.
 */
export function makeReadingTrailApi(api: AxiosInstance): ReadingTrailApi {
  return {
    async postBatch(profileId, storybookId, body, options) {
      try {
        const res = await api.post<ReadingTrailIngestView>(
          `/v1/reading-trail/${profileId}/${storybookId}`,
          body,
          // keepalive is fetch-only; see offline/readingTimeSync.ts for why the
          // unload path switches adapters rather than using sendBeacon (which
          // cannot carry the Authorization header).
          options?.keepalive === true
            ? { adapter: 'fetch' as const, fetchOptions: { keepalive: true } }
            : undefined
        )
        return res.data
      } catch (error) {
        const status = isAxiosError(error) ? error.response?.status : undefined
        if (isAxiosError(error) && status === undefined) throw new OfflineError()
        if (status !== undefined && (status >= 500 || status === 429)) throw new OfflineError()
        throw error
      }
    },
  }
}

export interface SendTrailOptions {
  keepalive?: boolean
  /** Injectable id factory for deterministic tests. */
  newId?: () => string
  /** Injectable clock for deterministic tests. */
  now?: () => number
}

/**
 * Send one batch, queueing it on an offline failure. Never rejects.
 *
 * @returns The outcome; `disabled` tells the recorder to stop for this session.
 */
export async function sendTrailBatch(
  api: ReadingTrailApi,
  profileId: string,
  storybookId: string,
  body: ReadingTrailBatchBody,
  options: SendTrailOptions = {}
): Promise<TrailSendOutcome> {
  try {
    const result = await api.postBatch(profileId, storybookId, body, {
      keepalive: options.keepalive,
    })
    return result.recorded ? 'recorded' : 'disabled'
  } catch (error) {
    if (!(error instanceof OfflineError)) {
      // A permanent rejection (validation, auth, a cap). Retrying the same
      // batch cannot succeed, and the child must never hear about it.
      console.warn('[reading-trail] batch rejected', { status: describeStatus(error) })
      return 'dropped'
    }
  }
  try {
    await enqueueTrailBatch({
      event_id: (options.newId ?? (() => crypto.randomUUID()))(),
      kind: 'reading_trail',
      profile_id: profileId,
      storybook_id: storybookId,
      body,
      queued_at: (options.now ?? Date.now)(),
    })
  } catch {
    return 'dropped'
  }
  if (typeof window !== 'undefined' && navigator.onLine) {
    window.dispatchEvent(new Event(QUEUE_APPENDED_EVENT))
  }
  return 'queued'
}

function describeStatus(error: unknown): string {
  if (isAxiosError(error) && error.response !== undefined) {
    return `http ${String(error.response.status)}`
  }
  return error instanceof Error ? error.name : 'unknown'
}
