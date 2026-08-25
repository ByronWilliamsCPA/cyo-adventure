import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReadingState } from '../player/types'
import * as db from './db'
import { type QueuedWrite, _resetDbHandle, enqueueWrite, getReadingState, listQueue } from './db'
import {
  LocalWriteError,
  OfflineError,
  QUEUE_APPENDED_EVENT,
  type PutResponse,
  type SaveBody,
  type SyncApi,
  replayQueue,
  resolveConflict,
  saveProgress,
  toPutPayload,
} from './sync'

function makeState(node: string, revision: number): ReadingState {
  return {
    current_node: node,
    var_state: {},
    path: ['n_start', node],
    visit_set: ['n_start', node],
    version: 1,
    state_revision: revision,
    save_slots: {},
  }
}

function rowAt(node: string, revision: number): ReadingState {
  return makeState(node, revision)
}

/**
 * The server-managed / View-only fields the strict PUT model (ReadingStateBody,
 * extra="forbid") rejects. They appear on ReadingStateView but not the body, so
 * a save that echoes them back 422s. Seven fields, not four: `character_id`,
 * `character_name`, and `seed_var_state` (ADR-028 Task 6) joined the original
 * four when the server started snapshotting a profile's active persistent
 * character onto the reading-state row; all three are just as server-derived
 * as the pre-existing four, and just as forbidden on the client-writable body.
 */
const FORBIDDEN_VIEW_KEYS = [
  'child_profile_id',
  'storybook_id',
  'updated_by_device_id',
  'last_synced_at',
  'character_id',
  'character_name',
  'seed_var_state',
] as const

/**
 * A reading state as it exists AFTER a cross-device resume caches the server's
 * ReadingStateView verbatim: the engine fields plus the seven View-only fields
 * the strict PUT model forbids. The cast models the real (structurally unsound)
 * runtime situation where a View is handed to code typed for ReadingState.
 */
function viewShapedState(node: string, revision: number): ReadingState {
  return {
    ...makeState(node, revision),
    child_profile_id: '11111111-1111-1111-1111-111111111111',
    storybook_id: 's1',
    updated_by_device_id: 'device-a',
    last_synced_at: '2026-07-21T00:00:00Z',
    character_id: '22222222-2222-2222-2222-222222222222',
    character_name: 'Astra',
    seed_var_state: { has_sword: true },
  } as unknown as ReadingState
}

/** A fake API that records the full body sent to each PUT (not just event_id). */
function capturingApi(
  handler: (body: SaveBody) => PutResponse | never
): SyncApi & { bodies: SaveBody[] } {
  const bodies: SaveBody[] = []
  return {
    bodies,
    putReadingState(_p, _s, body) {
      bodies.push(body)
      return Promise.resolve().then(() => handler(body))
    },
  }
}

/** A fake API whose putReadingState behaviour is supplied per test. */
function fakeApi(
  handler: (body: { event_id?: string }) => PutResponse | never
): SyncApi & { calls: { event_id?: string }[] } {
  const calls: { event_id?: string }[] = []
  return {
    calls,
    putReadingState(_p, _s, body) {
      calls.push({ event_id: body.event_id })
      return Promise.resolve().then(() => handler(body))
    },
  }
}

let idCounter = 0
const ids = () => `evt-${++idCounter}`

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  idCounter = 0
})
afterEach(() => vi.restoreAllMocks())

describe('saveProgress', () => {
  it('returns saved and caches the server row on 200', async () => {
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), {
      newId: ids,
    })
    expect(result).toEqual({ kind: 'saved', row: rowAt('n_mid', 1) })
    expect((await getReadingState('p1', 's1'))?.state_revision).toBe(1)
  })

  it('returns conflict and does not throw on 409', async () => {
    const api = fakeApi(() => ({ status: 409, currentRow: rowAt('n_other', 5) }))
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), {
      newId: ids,
    })
    expect(result.kind).toBe('conflict')
    if (result.kind === 'conflict') {
      expect(result.currentRow.state_revision).toBe(5)
    }
  })

  it('queues the write when the network is unavailable', async () => {
    const api = fakeApi(() => {
      throw new OfflineError()
    })
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), {
      newId: ids,
    })
    expect(result.kind).toBe('queued')
    const queue = await listQueue()
    expect(queue).toHaveLength(1)
    expect(queue[0].event_id).toBe('evt-1')
  })

  it('propagates a non-offline HTTP error instead of queueing it', async () => {
    const api = fakeApi(() => {
      throw new Error('500 server error')
    })
    await expect(
      saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
    ).rejects.toThrow('500 server error')
    expect(await listQueue()).toHaveLength(0)
  })

  it('throws LocalWriteError when the initial local cache write fails', async () => {
    vi.spyOn(db, 'putReadingState').mockRejectedValueOnce(new Error('quota exceeded'))
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))
    await expect(
      saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
    ).rejects.toBeInstanceOf(LocalWriteError)
    // The server was never called: the step never left the device.
    expect(api.calls).toHaveLength(0)
  })

  it('still returns saved when only the post-save cache refresh fails', async () => {
    // The server already accepted this step; a failure to mirror it locally
    // afterward is not a loss and must not make the caller skip adopting the
    // new revision (that would desync it from the server on the next save).
    const original = db.putReadingState
    let calls = 0
    vi.spyOn(db, 'putReadingState').mockImplementation(async (...args) => {
      calls += 1
      if (calls === 2) throw new Error('quota exceeded')
      return original(...args)
    })
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
    expect(result).toEqual({ kind: 'saved', row: rowAt('n_mid', 1) })
  })

  it('throws LocalWriteError when enqueueing an offline write fails', async () => {
    vi.spyOn(db, 'enqueueWrite').mockRejectedValueOnce(new Error('quota exceeded'))
    const api = fakeApi(() => {
      throw new OfflineError()
    })
    await expect(
      saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
    ).rejects.toBeInstanceOf(LocalWriteError)
    expect(await listQueue()).toHaveLength(0)
  })

  /**
   * Regression for the offline-resume seed loss: the plain machine
   * ReadingState saveProgress is actually called with (see `makeState`)
   * never carries `character_name`/`seed_var_state`, unlike every other test
   * in this file that seeds the cache directly via `viewShapedState` and
   * never exercises the real save path. Before this fix, saveProgress's
   * optimistic pre-network write replaced the cached View wholesale with the
   * plain state, and the offline branch below never got a chance to
   * overwrite it again with the server's real View: a resume in that window
   * would read `character_name`/`seed_var_state` off the degraded row and
   * silently open unseeded (see reader/characterSeed.ts::deriveCharacterSeed).
   */
  it('carries the previously cached character seed forward into an offline save', async () => {
    // Seed the cache the way a real resume would: the server's own
    // ReadingStateView, character fields included.
    await db.putReadingState('p1', 's1', viewShapedState('n_start', 0))
    const api = fakeApi(() => {
      throw new OfflineError()
    })
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
    expect(result.kind).toBe('queued')

    const cached = (await getReadingState('p1', 's1')) as unknown as {
      character_name?: string
      seed_var_state?: Record<string, unknown>
      current_node: string
    }
    // The offline save still landed (the machine's own progress is not
    // lost)...
    expect(cached.current_node).toBe('n_mid')
    // ...and the character binding carried forward from the previous cache
    // row instead of being silently dropped.
    expect(cached.character_name).toBe('Astra')
    expect(cached.seed_var_state).toEqual({ has_sword: true })
  })

  it('does not invent a character seed when the previous cache row had none', async () => {
    // No previous cache row at all, and `makeState` itself never carries the
    // two fields: nothing here should manufacture one from thin air.
    const api = fakeApi(() => {
      throw new OfflineError()
    })
    await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })

    const cached = (await getReadingState('p1', 's1')) as unknown as {
      character_name?: string
      seed_var_state?: unknown
    }
    expect(cached.character_name).toBeUndefined()
    expect(cached.seed_var_state).toBeUndefined()
  })
})

describe('toPutPayload', () => {
  it('strips View-only fields and keeps the engine + device/event fields', () => {
    const payload = toPutPayload({
      ...viewShapedState('n_mid', 3),
      device_id: 'device-a',
      event_id: 'evt-9',
    })
    for (const key of FORBIDDEN_VIEW_KEYS) {
      expect(payload).not.toHaveProperty(key)
    }
    expect(payload).toEqual({
      version: 1,
      current_node: 'n_mid',
      var_state: {},
      path: ['n_start', 'n_mid'],
      visit_set: ['n_start', 'n_mid'],
      save_slots: {},
      state_revision: 3,
      device_id: 'device-a',
      event_id: 'evt-9',
    })
  })

  it('omits device_id and event_id when they are absent', () => {
    const payload = toPutPayload(makeState('a', 0))
    expect(payload).not.toHaveProperty('device_id')
    expect(payload).not.toHaveProperty('event_id')
    expect(payload.current_node).toBe('a')
  })

  it('never re-adds character_id or seed_var_state (ADR-028 Task 6/9): they are server-owned', () => {
    // Named explicitly, not just covered by the FORBIDDEN_VIEW_KEYS loop
    // above: these two are the client-supplied-binding hole Task 6 closed
    // (a client could otherwise bind an arbitrary character to someone
    // else's reading state, or fabricate its own seed). The next person
    // extending SaveBody with a character-related field must see this fail,
    // not add it by reflex.
    const payload = toPutPayload(viewShapedState('n_mid', 3))
    const keys = Object.keys(payload)
    expect(keys).not.toContain('character_id')
    expect(keys).not.toContain('seed_var_state')
  })
})

describe('PUT body hygiene (strict extra="forbid" contract)', () => {
  it('saveProgress never echoes View-only fields the PUT model forbids', async () => {
    // Reproduces the 422 extra_forbidden bug: the SECOND save after a
    // cross-device resume, where `state` was sourced from a cached server View.
    const api = capturingApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))
    await saveProgress(api, 'p1', 's1', viewShapedState('n_mid', 0), { newId: ids })

    const body = api.bodies[0]
    for (const key of FORBIDDEN_VIEW_KEYS) {
      expect(body).not.toHaveProperty(key)
    }
    // The engine-owned fields the PUT model requires must all survive.
    expect(body).toMatchObject({
      version: 1,
      current_node: 'n_mid',
      var_state: {},
      path: ['n_start', 'n_mid'],
      visit_set: ['n_start', 'n_mid'],
      save_slots: {},
      state_revision: 0,
      event_id: 'evt-1',
    })
  })

  it('replayQueue never echoes View-only fields the PUT model forbids', async () => {
    const offline = capturingApi(() => {
      throw new OfflineError()
    })
    await saveProgress(offline, 'p1', 's1', viewShapedState('a', 0), {
      newId: ids,
      deviceId: 'device-a',
    })

    const online = capturingApi(() => ({ status: 200, row: rowAt('synced', 1) }))
    await replayQueue(online)

    const body = online.bodies[0]
    for (const key of FORBIDDEN_VIEW_KEYS) {
      expect(body).not.toHaveProperty(key)
    }
    expect(body).toMatchObject({ current_node: 'a', state_revision: 0, device_id: 'device-a' })
  })
})

describe('resolveConflict', () => {
  it('adopts the server row for use_newer_progress', async () => {
    const api = fakeApi(() => ({ status: 200, row: rowAt('x', 9) }))
    const result = await resolveConflict(
      api,
      'p1',
      's1',
      makeState('local', 0),
      rowAt('server', 7),
      'use_newer_progress'
    )
    expect(result).toEqual({ kind: 'saved', row: rowAt('server', 7) })
    expect((await getReadingState('p1', 's1'))?.current_node).toBe('server')
  })

  it('throws LocalWriteError when adopting the server row fails (use_newer_progress)', async () => {
    // Regression: the use_newer_progress local write must surface as
    // LocalWriteError, the same contract saveProgress upholds. Without the
    // wrapper a raw storage error escaped, ReaderPage's LocalWriteError branch
    // missed it, the failure was misclassified as a transient remote hiccup, the
    // server row was never adopted, and the reader re-409'd on the next choice.
    const api = fakeApi(() => ({ status: 200, row: rowAt('x', 9) }))
    vi.spyOn(db, 'putReadingState').mockRejectedValueOnce(new Error('quota exceeded'))
    await expect(
      resolveConflict(
        api,
        'p1',
        's1',
        makeState('local', 0),
        rowAt('server', 7),
        'use_newer_progress'
      )
    ).rejects.toBeInstanceOf(LocalWriteError)
  })

  it('rebases local state onto the server revision for continue_from_this_device', async () => {
    const seen: number[] = []
    const api: SyncApi = {
      putReadingState(_p, _s, body) {
        seen.push(body.state_revision)
        return Promise.resolve({ status: 200, row: rowAt('local', body.state_revision + 1) })
      },
    }
    const result = await resolveConflict(
      api,
      'p1',
      's1',
      makeState('local', 0),
      rowAt('server', 7),
      'continue_from_this_device',
      { newId: ids }
    )
    // Local save is rebased to the server's current revision (7) before resending.
    expect(seen).toEqual([7])
    expect(result.kind).toBe('saved')
  })
})

describe('replayQueue', () => {
  it('drains queued writes on success and dedupes by event_id', async () => {
    const offline = fakeApi(() => {
      throw new OfflineError()
    })
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 1), { newId: ids })
    expect(await listQueue()).toHaveLength(2)

    const online = fakeApi((body) => ({
      status: 200,
      row: rowAt('synced', body.event_id === 'evt-1' ? 1 : 2),
    }))
    const outcome = await replayQueue(online)
    expect(outcome.replayed).toBe(2)
    expect(await listQueue()).toHaveLength(0)
    // event_id is forwarded so the server can ignore replays.
    expect(online.calls.map((c) => c.event_id)).toEqual(['evt-1', 'evt-2'])
  })

  it('stops replay at the first network error, leaving the rest queued', async () => {
    const offline = fakeApi(() => {
      throw new OfflineError()
    })
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 1), { newId: ids })

    const stillOffline = fakeApi(() => {
      throw new OfflineError()
    })
    const outcome = await replayQueue(stillOffline)
    expect(outcome.replayed).toBe(0)
    expect(await listQueue()).toHaveLength(2)
  })

  it('replays sequential same-base offline writes as a chain (latest wins)', async () => {
    const offline = fakeApi(() => {
      throw new OfflineError()
    })
    // The revision does not advance while offline, so both writes share base 0.
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 0), { newId: ids })

    let serverRevision = 0
    const sent: number[] = []
    const online: SyncApi = {
      putReadingState(_p, _s, body) {
        sent.push(body.state_revision)
        if (body.state_revision !== serverRevision) {
          return Promise.resolve({
            status: 409,
            currentRow: makeState('server', serverRevision),
          })
        }
        serverRevision += 1
        return Promise.resolve({ status: 200, row: makeState(body.current_node, serverRevision) })
      },
    }
    const outcome = await replayQueue(online)
    // Without rebasing, the second write would 409 and drop; rebasing applies it.
    expect(outcome.replayed).toBe(2)
    expect(outcome.conflicts).toHaveLength(0)
    expect(sent).toEqual([0, 1])
    expect(await listQueue()).toHaveLength(0)
  })

  it('holds every queued write for a story after its first cross-device conflict', async () => {
    // three queued writes for the same profile/story, increasing progress
    const offline = fakeApi(() => {
      throw new OfflineError()
    })
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 1), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('c', 2), { newId: ids })
    expect(await listQueue()).toHaveLength(3)

    const online = fakeApi(() => ({ status: 409, currentRow: rowAt('server', 7) }))
    const outcome = await replayQueue(online)
    expect(outcome.replayed).toBe(0)
    expect(outcome.conflicts).toHaveLength(3) // w1 (the 409) AND w2, w3 (held, not auto-rebased)
    expect(online.calls).toHaveLength(1) // w2/w3 never sent
    expect(await listQueue()).toHaveLength(0) // all surfaced to reconciliation, none silently kept
  })

  it('drops a write that fails with a non-offline error without wedging the queue', async () => {
    const offline = fakeApi(() => {
      throw new OfflineError()
    })
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 0), { newId: ids })

    const online: SyncApi = {
      putReadingState(_p, _s, body) {
        if (body.event_id === 'evt-1') {
          return Promise.reject(new Error('422 invalid'))
        }
        return Promise.resolve({ status: 200, row: makeState('b', 1) })
      },
    }
    const outcome = await replayQueue(online)
    expect(outcome.failed.map((w) => w.event_id)).toEqual(['evt-1'])
    expect(outcome.replayed).toBe(1)
    expect(await listQueue()).toHaveLength(0)
  })
})

/** A queued write with everything but the fields a test cares about filled in. */
function queuedWrite(overrides: Partial<QueuedWrite> & { event_id: string }): QueuedWrite {
  return {
    profile_id: 'p1',
    storybook_id: 's1',
    base_revision: 0,
    state: makeState('n_mid', 0),
    queued_at: Date.now(),
    ...overrides,
  }
}

describe('saveProgress does not overtake the queue', () => {
  it('appends a live write behind an existing queued write for the same row', async () => {
    await enqueueWrite(queuedWrite({ event_id: 'older' }))
    // This API would happily accept the write. The point is that it is never
    // asked: a reachable network is not permission to jump the row's queue.
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))

    const result = await saveProgress(api, 'p1', 's1', makeState('n_new', 0), { newId: ids })

    expect(result.kind).toBe('queued')
    expect(api.calls).toHaveLength(0)
    expect((await listQueue()).map((w) => w.event_id)).toEqual(['older', 'evt-1'])
  })

  it('sends a live write when the queue holds another row only', async () => {
    // Discriminates the per-row predicate from a bare "is the queue empty".
    // A backlog for a DIFFERENT book must not stall this one.
    await enqueueWrite(queuedWrite({ event_id: 'other-book', storybook_id: 's2' }))
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))

    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })

    expect(result.kind).toBe('saved')
    expect(api.calls).toHaveLength(1)
    expect((await listQueue()).map((w) => w.event_id)).toEqual(['other-book'])
  })

  it('appends rather than sending when the queue cannot be read', async () => {
    // Fail closed: an unreadable queue might hold writes for this row, and
    // overtaking one causes the rewind the check exists to prevent.
    vi.spyOn(db, 'listQueue').mockRejectedValueOnce(new Error('IDB unavailable'))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const api = fakeApi(() => ({ status: 200, row: rowAt('n_mid', 1) }))

    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })

    expect(result.kind).toBe('queued')
    expect(api.calls).toHaveLength(0)
  })

  it('schedules a drain when a write is appended while online', async () => {
    // An append while online is NOT covered by the 'online' event (it already
    // fired, or never will), so without this the write sits until the next
    // disconnect. Every response-less transport failure raises OfflineError,
    // and none of them flips navigator.onLine.
    const drains: Event[] = []
    const listener = (e: Event) => drains.push(e)
    window.addEventListener(QUEUE_APPENDED_EVENT, listener)
    try {
      const api = fakeApi(() => {
        throw new OfflineError()
      })
      await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
      expect(drains).toHaveLength(1)
    } finally {
      window.removeEventListener(QUEUE_APPENDED_EVENT, listener)
    }
  })

  it('does not schedule a drain for a write queued while offline', async () => {
    // The discriminating half of the pair above: while genuinely offline the
    // 'online' event already covers the drain, and a kick per choice would
    // burn a doomed round trip on every page of a long offline read.
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const drains: Event[] = []
    const listener = (e: Event) => drains.push(e)
    window.addEventListener(QUEUE_APPENDED_EVENT, listener)
    try {
      const api = fakeApi(() => {
        throw new OfflineError()
      })
      await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), { newId: ids })
      expect(await listQueue()).toHaveLength(1)
      expect(drains).toHaveLength(0)
    } finally {
      window.removeEventListener(QUEUE_APPENDED_EVENT, listener)
    }
  })
})

describe('queue ordering', () => {
  it('replays same-millisecond writes in insertion order', async () => {
    // queued_at is a millisecond stamp and appends need no round trip, so a
    // tie is normal. The event_ids here descend deliberately: real ids are
    // random UUIDs, and with getAll returning key order a tie would otherwise
    // resolve to id order. Ascending ids would agree with insertion order by
    // accident and the test could not tell the tie-break from its absence.
    const at = Date.now()
    for (const id of ['evt-c', 'evt-b', 'evt-a']) {
      await enqueueWrite(queuedWrite({ event_id: id, queued_at: at }))
    }

    expect((await listQueue()).map((w) => w.event_id)).toEqual(['evt-c', 'evt-b', 'evt-a'])
  })

  it('orders by queued_at first, so an older session replays before this one', async () => {
    // seq resets on reload; it must only ever break ties, never outrank the stamp.
    await enqueueWrite(queuedWrite({ event_id: 'this-session', queued_at: 2_000 }))
    await enqueueWrite(queuedWrite({ event_id: 'last-session', queued_at: 1_000, seq: 999 }))

    expect((await listQueue()).map((w) => w.event_id)).toEqual(['last-session', 'this-session'])
  })
})

describe('replayQueue drains in passes', () => {
  it('sends a write appended while the drain was already running', async () => {
    await enqueueWrite(queuedWrite({ event_id: 'first', queued_at: 1_000 }))
    let appended = false
    const api = capturingApi((body) => {
      if (!appended) {
        appended = true
        // The child taps a choice mid-drain. saveProgress appends it (the queue
        // is non-empty for this row), so only a second pass can send it.
        void enqueueWrite(queuedWrite({ event_id: 'mid-drain', queued_at: 1_001 }))
      }
      return { status: 200, row: rowAt('n_mid', body.event_id === 'first' ? 1 : 2) }
    })

    const outcome = await replayQueue(api)

    expect(outcome.replayed).toBe(2)
    expect(api.bodies.map((b) => b.event_id)).toEqual(['first', 'mid-drain'])
    expect(await listQueue()).toHaveLength(0)
  })

  it('still sends a choice made after a drain latched the story', async () => {
    // The conflict latch exists to hold the STALE tail of an offline chain.
    // A choice stamped after the drain began is fresh reading on a device that
    // is online now; holding it would dequeue it without ever sending it, and
    // nothing surfaces outcome.conflicts to the child.
    vi.spyOn(Date, 'now').mockReturnValue(2_000)
    await enqueueWrite(queuedWrite({ event_id: 'stale-1', queued_at: 1_000 }))
    await enqueueWrite(queuedWrite({ event_id: 'stale-2', queued_at: 1_001 }))
    await enqueueWrite(queuedWrite({ event_id: 'fresh', queued_at: 3_000 }))
    const api = capturingApi((body) =>
      body.event_id === 'stale-1'
        ? { status: 409, currentRow: rowAt('n_elsewhere', 9) }
        : { status: 200, row: rowAt('n_mid', 10) }
    )

    const outcome = await replayQueue(api)

    // stale-1 conflicted and latched; stale-2 was held behind it unsent.
    expect(outcome.conflicts.map((c) => c.event_id)).toEqual(['stale-1', 'stale-2'])
    // The fresh choice was sent anyway, and is not reported as a conflict.
    expect(api.bodies.map((b) => b.event_id)).toEqual(['stale-1', 'fresh'])
    expect(outcome.replayed).toBe(1)
    expect(await listQueue()).toHaveLength(0)
  })

  it('holds a write stamped in the drain-start millisecond as part of the stale chain', async () => {
    // The exemption's boundary is strict, and deliberately so: queued_at and
    // drainStartedAt are both millisecond stamps, so a tie is ambiguous about
    // which came first. Holding is the fail-safe reading, because a held write
    // is surfaced as a conflict while a wrongly-sent stale write silently
    // rewinds the child's server position.
    vi.spyOn(Date, 'now').mockReturnValue(2_000)
    await enqueueWrite(queuedWrite({ event_id: 'stale', queued_at: 1_000 }))
    await enqueueWrite(queuedWrite({ event_id: 'boundary', queued_at: 2_000 }))
    const api = capturingApi((body) =>
      body.event_id === 'stale'
        ? { status: 409, currentRow: rowAt('n_elsewhere', 9) }
        : { status: 200, row: rowAt('n_mid', 10) }
    )

    const outcome = await replayQueue(api)

    expect(api.bodies.map((b) => b.event_id)).toEqual(['stale'])
    expect(outcome.conflicts.map((c) => c.event_id)).toEqual(['stale', 'boundary'])
  })

  it('keeps draining when mirroring an accepted row locally fails', async () => {
    // The server already took the write, so it is not lost, only its local
    // mirror is stale. Throwing would abort the drain and discard every
    // conflict and failure collected so far.
    await enqueueWrite(queuedWrite({ event_id: 'first', queued_at: 1_000 }))
    await enqueueWrite(queuedWrite({ event_id: 'second', queued_at: 1_001 }))
    vi.spyOn(db, 'putReadingState').mockRejectedValueOnce(new Error('quota exceeded'))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const api = capturingApi((body) => ({
      status: 200,
      row: rowAt('n_mid', body.event_id === 'first' ? 1 : 2),
    }))

    const outcome = await replayQueue(api)

    expect(outcome.replayed).toBe(2)
    expect(await listQueue()).toHaveLength(0)
  })
})
