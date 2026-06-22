/**
 * Reading-state sync: revision-based saves, offline queue, idempotent replay.
 *
 * The server is canonical (tech-spec "Multi-device sync rules"). A save carries
 * the base `state_revision` and an `event_id`. On success the local cache is
 * updated; on 409 the caller reconciles (see offline-conflict-ux.md); when the
 * network is unavailable the write is queued and replayed in order on reconnect,
 * with the `event_id` making replays idempotent server-side.
 */

import { type QueuedWrite, dequeue, enqueueWrite, listQueue, putReadingState } from './db'
import type { ReadingState } from '../player/types'

export interface SaveBody extends ReadingState {
  device_id?: string
  event_id?: string
}

export type PutResponse =
  | { status: 200; row: ReadingState }
  | { status: 409; currentRow: ReadingState }

/** The network port the sync layer depends on (the generated client adapts to this). */
export interface SyncApi {
  putReadingState(profileId: string, storybookId: string, body: SaveBody): Promise<PutResponse>
}

export type SaveResult =
  | { kind: 'saved'; row: ReadingState }
  | { kind: 'conflict'; currentRow: ReadingState }
  | { kind: 'queued'; eventId: string }

export type Resolution = 'continue_from_this_device' | 'use_newer_progress'

export interface SaveOptions {
  deviceId?: string
  eventId?: string
  /** Injectable id factory for deterministic tests; defaults to crypto.randomUUID. */
  newId?: () => string
}

function makeId(opts: SaveOptions): string {
  return opts.eventId ?? (opts.newId ?? (() => crypto.randomUUID()))()
}

/**
 * Save reading progress. Updates the local cache, then attempts the server save:
 * returns `saved` on success, `conflict` on a 409, or `queued` if the network is
 * unavailable (the write is enqueued for later replay).
 */
export async function saveProgress(
  api: SyncApi,
  profileId: string,
  storybookId: string,
  state: ReadingState,
  opts: SaveOptions = {}
): Promise<SaveResult> {
  const eventId = makeId(opts)
  await putReadingState(profileId, storybookId, state)
  const body: SaveBody = {
    ...state,
    device_id: opts.deviceId,
    event_id: eventId,
  }
  try {
    const res = await api.putReadingState(profileId, storybookId, body)
    if (res.status === 409) {
      return { kind: 'conflict', currentRow: res.currentRow }
    }
    await putReadingState(profileId, storybookId, res.row)
    return { kind: 'saved', row: res.row }
  } catch {
    const queued: QueuedWrite = {
      event_id: eventId,
      profile_id: profileId,
      storybook_id: storybookId,
      base_revision: state.state_revision,
      state,
      device_id: opts.deviceId,
      queued_at: Date.now(),
    }
    await enqueueWrite(queued)
    return { kind: 'queued', eventId }
  }
}

/**
 * Resolve a 409 conflict per the reader's choice (offline-conflict-ux.md):
 * "continue_from_this_device" re-saves the local state at the server's current
 * revision so it wins; "use_newer_progress" adopts the server row.
 */
export async function resolveConflict(
  api: SyncApi,
  profileId: string,
  storybookId: string,
  localState: ReadingState,
  serverRow: ReadingState,
  resolution: Resolution,
  opts: SaveOptions = {}
): Promise<SaveResult> {
  if (resolution === 'use_newer_progress') {
    await putReadingState(profileId, storybookId, serverRow)
    return { kind: 'saved', row: serverRow }
  }
  const rebased: ReadingState = {
    ...localState,
    state_revision: serverRow.state_revision,
  }
  return saveProgress(api, profileId, storybookId, rebased, opts)
}

export interface ReplayOutcome {
  replayed: number
  conflicts: QueuedWrite[]
}

/**
 * Replay queued offline writes in order. Stops at the first network error
 * (still offline). A 409 during replay is collected for the caller to reconcile
 * and removed from the queue so it does not block later writes.
 */
export async function replayQueue(api: SyncApi): Promise<ReplayOutcome> {
  const outcome: ReplayOutcome = { replayed: 0, conflicts: [] }
  for (const item of await listQueue()) {
    let res: PutResponse
    try {
      res = await api.putReadingState(item.profile_id, item.storybook_id, {
        ...item.state,
        device_id: item.device_id,
        event_id: item.event_id,
      })
    } catch {
      break // still offline; leave the rest queued
    }
    if (res.status === 409) {
      outcome.conflicts.push(item)
    } else {
      await putReadingState(item.profile_id, item.storybook_id, res.row)
      outcome.replayed += 1
    }
    await dequeue(item.event_id)
  }
  return outcome
}
