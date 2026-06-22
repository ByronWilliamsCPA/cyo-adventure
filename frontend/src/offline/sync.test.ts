import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import type { ReadingState } from '../player/types'
import { _resetDbHandle, getReadingState, listQueue } from './db'
import { type PutResponse, type SyncApi, replayQueue, resolveConflict, saveProgress } from './sync'

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
      throw new Error('offline')
    })
    const result = await saveProgress(api, 'p1', 's1', makeState('n_mid', 0), {
      newId: ids,
    })
    expect(result.kind).toBe('queued')
    const queue = await listQueue()
    expect(queue).toHaveLength(1)
    expect(queue[0].event_id).toBe('evt-1')
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
      throw new Error('offline')
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
      throw new Error('offline')
    })
    await saveProgress(offline, 'p1', 's1', makeState('a', 0), { newId: ids })
    await saveProgress(offline, 'p1', 's1', makeState('b', 1), { newId: ids })

    const stillOffline = fakeApi(() => {
      throw new Error('offline')
    })
    const outcome = await replayQueue(stillOffline)
    expect(outcome.replayed).toBe(0)
    expect(await listQueue()).toHaveLength(2)
  })
})
