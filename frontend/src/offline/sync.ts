/**
 * Reading-state sync: revision-based saves, offline queue, idempotent replay.
 *
 * The server is canonical (tech-spec "Multi-device sync rules"). A save carries
 * the base `state_revision` and an `event_id`. On success the local cache is
 * updated; on 409 the caller reconciles (see offline-conflict-ux.md); when the
 * network is unavailable the write is queued and replayed in order on reconnect,
 * with the `event_id` making replays idempotent server-side.
 */

import {
  type QueuedWrite,
  dequeue,
  enqueueWrite,
  getReadingState,
  listQueue,
  putReadingState,
} from './db'
import type { ReadingStateView } from '../client/types.gen'
import type { ReadingState } from '../player/types'

export interface SaveBody extends ReadingState {
  device_id?: string
  event_id?: string
}

export type PutResponse =
  { status: 200; row: ReadingState } | { status: 409; currentRow: ReadingState }

/**
 * Raised by a SyncApi implementation when the save could not reach the server
 * (no HTTP response: offline, DNS failure, timeout). Only this error means
 * "offline"; an HTTP error response (401/403/422/5xx) is a real failure and must
 * propagate rather than be queued as if the device were offline.
 */
export class OfflineError extends Error {
  constructor(message = 'network unavailable') {
    super(message)
    this.name = 'OfflineError'
  }
}

/**
 * Raised when a local IndexedDB write inside saveProgress fails somewhere
 * that leaves this step stored nowhere at all: the initial cache write
 * (before the server is even tried) or the offline-queue enqueue (the server
 * was unreachable and the fallback write also failed). Distinct from
 * OfflineError/HTTP failures so the caller can surface it immediately
 * instead of treating it as a routine retry-later network blip.
 *
 * Deliberately NOT raised when only the post-save local cache refresh fails
 * (the server already has this step; see saveProgress): that failure means
 * the local mirror is stale, not that the step is lost, and must not stop
 * the caller from adopting the server's new revision.
 */
export class LocalWriteError extends Error {
  // Manually assigned, not via the ES2022 Error(message, {cause}) constructor
  // signature: this project's build target is ES2020.
  readonly cause?: unknown

  constructor(message = 'local write failed', cause?: unknown) {
    super(message)
    this.name = 'LocalWriteError'
    this.cause = cause
  }
}

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
 * Build the strict reading-state PUT body from a state that may have been
 * sourced from a cached server View.
 *
 * The PUT request model (ReadingStateBody, `extra="forbid"`) accepts only the
 * engine-owned fields plus `device_id`/`event_id`. After a cross-device resume
 * the client caches the server's ReadingStateView verbatim; that View also
 * carries `child_profile_id`, `storybook_id`, `updated_by_device_id`, and
 * `last_synced_at`. Spreading such a state into the body echoes those fields
 * back and the server rejects the save with HTTP 422 `extra_forbidden`, so the
 * save silently fails. Whitelisting the allowed fields (rather than deleting the
 * known-bad ones) keeps the request valid even if the View gains new
 * server-managed fields later.
 */
// #CRITICAL: data-integrity: the reading-state PUT model is extra="forbid". A
// state read back from the local cache after a cross-device resume is a server
// View with fields the body forbids; echoing them 422s and loses the save.
// #VERIFY: this field set must match ReadingStateBody in
// src/cyo_adventure/api/schemas.py; update it if that model changes. sync.test.ts
// "PUT body hygiene" asserts no View-only key survives.
export function toPutPayload(state: SaveBody): SaveBody {
  const payload: SaveBody = {
    version: state.version,
    current_node: state.current_node,
    var_state: state.var_state,
    path: state.path,
    visit_set: state.visit_set,
    save_slots: state.save_slots,
    state_revision: state.state_revision,
  }
  if (state.device_id !== undefined) {
    payload.device_id = state.device_id
  }
  if (state.event_id !== undefined) {
    payload.event_id = state.event_id
  }
  return payload
}

/**
 * Carries the previously-cached character-binding fields forward onto the
 * optimistic local write that saveProgress makes before it even tries the
 * network.
 *
 * `state` here is always the plain machine ReadingState: the reader engine
 * has no server-View surface for `character_name`/`seed_var_state` (see
 * characterSeed.ts), so it never carries them. The only place those two
 * fields can exist locally is a previously-cached row written after a
 * successful PUT or a cross-device resume, which is a real ReadingStateView
 * at runtime even though it is typed ReadingState (same widening
 * characterSeed.ts::deriveCharacterSeed uses for the same two fields).
 *
 * Without this, saveProgress's pre-network write replaces that cached View
 * wholesale with the plain state. If the network call then fails offline
 * (OfflineError, the write is queued instead) nothing overwrites the row
 * with the server's real View again until the queued write eventually
 * replays, so a resume in that window reads `character_name`/
 * `seed_var_state` off the degraded row and deriveCharacterSeed (which has
 * no other source of truth) silently opens the read unseeded.
 *
 * Deliberately does not invent a seed: a previous row with neither field (a
 * read that was never character-bound) leaves `state` untouched.
 */
// #CRITICAL: data-integrity: an offline save must not downgrade a seeded
// read to unseeded. `previous`'s two character fields are carried forward
// onto the optimistic write untouched; nothing here derives or guesses a
// seed the previous row did not already have.
// #VERIFY: sync.test.ts "carries the previously cached character seed
// forward into an offline save" (reverting this function collapses that
// test: the cached row would lose character_name/seed_var_state the moment
// the offline branch runs).
function withCarriedCharacterSeed(
  previous: ReadingState | undefined,
  state: ReadingState
): ReadingState {
  if (previous === undefined) return state
  const view = previous as ReadingState &
    Partial<Pick<ReadingStateView, 'character_name' | 'seed_var_state'>>
  if (view.character_name === undefined && view.seed_var_state === undefined) return state
  // `state` wins per field when it already carries one of its own (today's
  // only real call sites never do; this is defensive, not load-bearing): the
  // cache is a fallback for a value the caller genuinely does not have, not
  // an override of one it does.
  const carried = state as ReadingState &
    Partial<Pick<ReadingStateView, 'character_name' | 'seed_var_state'>>
  const result: ReadingState &
    Partial<Pick<ReadingStateView, 'character_name' | 'seed_var_state'>> = { ...carried }
  if (carried.character_name === undefined && view.character_name !== undefined) {
    result.character_name = view.character_name
  }
  if (carried.seed_var_state === undefined && view.seed_var_state !== undefined) {
    result.seed_var_state = view.seed_var_state
  }
  return result
}

/**
 * Save reading progress. Updates the local cache, then attempts the server save:
 * returns `saved` on success, `conflict` on a 409, or `queued` if the network is
 * unavailable (the write is enqueued for later replay).
 */
// #CRITICAL: concurrency: saveProgress writes to IndexedDB then the server.
// The server is canonical (tech-spec "Multi-device sync rules"). A 409 means
// another device advanced the revision; the caller must reconcile, not retry.
// #VERIFY: only OfflineError is queued; HTTP 4xx/5xx must propagate to the
// caller so a real failure (auth, validation, server error) is not misclassified
// as offline and queued indefinitely. A failed local write (LocalWriteError)
// always propagates too, even during the offline branch: it means this step is
// not cached anywhere, so the caller must treat it as lost, not as queued.

// #ASSUME: concurrency: event_id uniqueness relies on crypto.randomUUID().
// Two concurrent saveProgress calls in the same millisecond will receive
// different event_ids; the server uses event_id for idempotent replay dedup.
// #VERIFY: replayQueue sends event_id on every replay write to the server.

export async function saveProgress(
  api: SyncApi,
  profileId: string,
  storybookId: string,
  state: ReadingState,
  opts: SaveOptions = {}
): Promise<SaveResult> {
  const eventId = makeId(opts)
  let previous: ReadingState | undefined
  try {
    previous = await getReadingState(profileId, storybookId)
  } catch (cause) {
    // Best-effort only: a failed read of the previous cache row must not
    // block the write below. Losing the carried-forward seed fields (if any
    // existed) is preferable to treating this as LocalWriteError, which
    // would tell the caller this step was never cached anywhere at all.
    console.error('[reader] failed to read the previous cached reading state', { cause })
  }
  try {
    await putReadingState(profileId, storybookId, withCarriedCharacterSeed(previous, state))
  } catch (cause) {
    throw new LocalWriteError('failed to write reading state to the local cache', cause)
  }
  const body = toPutPayload({
    ...state,
    device_id: opts.deviceId,
    event_id: eventId,
  })
  const enqueueBehindTheQueue = async (): Promise<SaveResult> => {
    const queued: QueuedWrite = {
      event_id: eventId,
      profile_id: profileId,
      storybook_id: storybookId,
      base_revision: state.state_revision,
      state,
      device_id: opts.deviceId,
      queued_at: Date.now(),
    }
    try {
      await enqueueWrite(queued)
    } catch (cause) {
      throw new LocalWriteError('failed to enqueue the offline write', cause)
    }
    return { kind: 'queued', eventId }
  }
  // #CRITICAL: concurrency: never overtake writes already queued for this row.
  // The queue exists to keep one row's writes totally ordered. A live write
  // that goes straight to the network while older writes for the same row are
  // still queued races replayQueue on reconnect: neither writer can refresh
  // `state_revision` while offline, so both carry the same base, exactly one is
  // accepted and the other 409s. Whichever loses is discarded, and if the LIVE
  // write is the loser the reader adopts the replayed older row and rewinds the
  // child to a node they already left. Append instead and let replayQueue send
  // the chain in order; it rebases each write onto the previous one's revision.
  // #VERIFY: offline-reconnect-real.spec.ts "clean reconnect: every queued
  // offline choice replays and lands on the real backend", which reconnects
  // while a choice is still being saved, which is exactly this window.
  const overtakesQueue = (await listQueue()).some(
    (item) => item.profile_id === profileId && item.storybook_id === storybookId
  )
  if (overtakesQueue) {
    return enqueueBehindTheQueue()
  }
  try {
    const res = await api.putReadingState(profileId, storybookId, body)
    if (res.status === 409) {
      return { kind: 'conflict', currentRow: res.currentRow }
    }
    try {
      await putReadingState(profileId, storybookId, res.row)
    } catch (cause) {
      // The server already accepted this step: res.row is now authoritative
      // and this save is not lost, only its local mirror is stale. Log and
      // keep going rather than throw LocalWriteError, which would make the
      // caller skip adopting res.row's revision and desync it from the
      // server on the very next save.
      console.error('[reader] failed to refresh the local cache after saving', { cause })
    }
    return { kind: 'saved', row: res.row }
  } catch (error) {
    if (error instanceof LocalWriteError) {
      throw error
    }
    // Only queue when the device is genuinely offline. An HTTP error response
    // (auth, validation, server error) is a real failure and must propagate, not
    // be misclassified as offline and poison the queue.
    if (!(error instanceof OfflineError)) {
      throw error
    }
    return enqueueBehindTheQueue()
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
    // Mirror saveProgress's local-write contract: a failed IndexedDB write must
    // surface as LocalWriteError so the caller treats it as lost, not as a
    // remote-save hiccup. Without the wrapper a raw storage error escapes, the
    // reader misclassifies it as a transient remote failure, never adopts the
    // server row, and re-409s on the next choice in a loop.
    try {
      await putReadingState(profileId, storybookId, serverRow)
    } catch (cause) {
      throw new LocalWriteError('failed to adopt the server row into the local cache', cause)
    }
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
  /** Genuine cross-device conflicts (server moved underneath the queue). */
  conflicts: QueuedWrite[]
  /** Writes dropped because the server rejected them with a non-offline error. */
  failed: QueuedWrite[]
}

function queueKey(item: QueuedWrite): string {
  return `${item.profile_id} ${item.storybook_id}`
}

/**
 * Replay queued offline writes in order. Stops only on a genuine offline error
 * (still no network), leaving the rest queued. Writes for the same story made
 * while offline share a base revision; each is rebased onto the latest revision
 * applied earlier in this replay so the reader's sequential progress lands as a
 * chain instead of every write after the first losing a 409 and being dropped.
 * That chaining applies only up to a genuine cross-device 409: once a story hits
 * one, it is latched and every remaining queued write for that story (including
 * the one that 409'd) is surfaced in outcome.conflicts for reconciliation
 * instead of being auto-rebased onto the server's revision, which would silently
 * overwrite the still-unreconciled row. A non-offline error (e.g. 422/5xx) drops
 * that write so it cannot wedge every later write.
 */
// #CRITICAL: concurrency: replayQueue replays writes in insertion order.
// Writes for the same story share a base_revision; latestRevision rebases each
// subsequent write onto the revision applied by the previous one so the chain
// lands sequentially rather than every write after the first producing a 409.
// The FIRST 409 for a story latches it in `conflicted`: every later queued
// write for that story is held (pushed to outcome.conflicts, dequeued, never
// sent) rather than auto-rebased onto the server's revision. Auto-rebasing
// past a genuine cross-device conflict would silently overwrite the
// unreconciled row before a human (or B2's reconciliation UI) ever sees it.
// #VERIFY: a genuine cross-device 409 (server advanced by another device mid-
// replay) is collected in outcome.conflicts, not silently dropped, and no
// write queued after it for the same story reaches the server until the
// conflict is reconciled.

export async function replayQueue(api: SyncApi): Promise<ReplayOutcome> {
  const outcome: ReplayOutcome = { replayed: 0, conflicts: [], failed: [] }
  // Latest server revision applied per story during this replay, so subsequent
  // same-base writes rebase onto it rather than 409 against a stale base.
  const latestRevision = new Map<string, number>()
  // Stories that have already hit a genuine cross-device 409 in this replay.
  // Every remaining write for such a story is held, not sent.
  const conflicted = new Set<string>()
  // #CRITICAL: concurrency: drain in passes, not over one snapshot. saveProgress
  // appends to this queue while a replay is running (see its overtakesQueue
  // branch), so a choice made during the drain would otherwise sit unsent until
  // the next 'online' event, which on a device that never drops again is never.
  // Each pass either dequeues at least one write or returns, so this cannot spin.
  // #VERIFY: offline-reconnect-real.spec.ts "clean reconnect: every queued
  // offline choice replays and lands on the real backend" reconnects mid-save,
  // so the last choice is appended after this drain has already begun.
  for (;;) {
    const pass = await listQueue()
    if (pass.length === 0) return outcome
    let dequeuedAny = false
    let stillOffline = false
    for (const item of pass) {
      const key = queueKey(item)
      if (conflicted.has(key)) {
        // A prior write for this story hit a genuine cross-device conflict. Do
        // not auto-rebase the tail onto the server revision (that would
        // overwrite the still-unreconciled row); surface every held write to
        // reconciliation instead.
        outcome.conflicts.push(item)
        await dequeue(item.event_id)
        dequeuedAny = true
        continue
      }
      const knownRevision = latestRevision.get(key)
      const state =
        knownRevision === undefined ? item.state : { ...item.state, state_revision: knownRevision }
      let res: PutResponse
      try {
        res = await api.putReadingState(
          item.profile_id,
          item.storybook_id,
          toPutPayload({ ...state, device_id: item.device_id, event_id: item.event_id })
        )
      } catch (error) {
        if (error instanceof OfflineError) {
          // Still offline; leave this and the rest queued for the next 'online'.
          stillOffline = true
          break
        }
        // Non-offline failure (auth/validation/server): this write cannot replay.
        // Drop it so it does not block every later write, and surface it.
        outcome.failed.push(item)
        await dequeue(item.event_id)
        dequeuedAny = true
        continue
      }
      if (res.status === 409) {
        outcome.conflicts.push(item)
        conflicted.add(key) // latch: hold every later write for this story too
      } else {
        await putReadingState(item.profile_id, item.storybook_id, res.row)
        outcome.replayed += 1
        latestRevision.set(key, res.row.state_revision)
      }
      await dequeue(item.event_id)
      dequeuedAny = true
    }
    if (stillOffline || !dequeuedAny) return outcome
  }
}
