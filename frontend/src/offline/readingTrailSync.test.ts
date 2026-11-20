import 'fake-indexeddb/auto'

import type { AxiosInstance } from 'axios'
import { AxiosError, AxiosHeaders } from 'axios'
import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReadingTrailBatchBody } from '../client/types.gen'
import { _resetDbHandle, enqueueWrite, listQueue, listTrailBatches } from './db'
import * as db from './db'
import { makeReadingTrailApi, sendTrailBatch } from './readingTrailSync'
import { OfflineError, QUEUE_APPENDED_EVENT, type ReadingTrailApi, replayQueue } from './sync'

const BODY: ReadingTrailBatchBody = {
  read_id: '00000000-0000-4000-8000-000000000001',
  version: 1,
  steps: [{ seq: 0, kind: 'start', node_id: 'n_open', choice_id: null, elapsed_s: 0 }],
}

function trailApi(impl: ReadingTrailApi['postBatch']): ReadingTrailApi {
  return { postBatch: vi.fn(impl) }
}

function httpError(status: number): AxiosError {
  return new AxiosError('fail', 'ERR', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: {},
  })
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('makeReadingTrailApi', () => {
  it('posts to the trail route and passes keepalive through the fetch adapter', async () => {
    const post = vi.fn().mockResolvedValue({ data: { recorded: true, stored_steps: 1 } })
    const api = makeReadingTrailApi({ post } as unknown as AxiosInstance)
    await api.postBatch('p1', 's1', BODY, { keepalive: true })
    expect(post).toHaveBeenCalledWith('/v1/reading-trail/p1/s1', BODY, {
      adapter: 'fetch',
      fetchOptions: { keepalive: true },
    })
    await api.postBatch('p1', 's1', BODY)
    expect(post).toHaveBeenLastCalledWith('/v1/reading-trail/p1/s1', BODY, undefined)
  })

  it('maps transport failures, 5xx and 429 to OfflineError and lets 4xx through', async () => {
    const transport = new AxiosError('network')
    for (const [error, offline] of [
      [transport, true],
      [httpError(503), true],
      [httpError(429), true],
      [httpError(422), false],
    ] as const) {
      const api = makeReadingTrailApi({
        post: vi.fn().mockRejectedValue(error),
      } as unknown as AxiosInstance)
      const caught = await api.postBatch('p1', 's1', BODY).catch((e: unknown) => e)
      expect(caught instanceof OfflineError).toBe(offline)
    }
  })
})

describe('sendTrailBatch', () => {
  it('reports recorded and disabled straight from the server answer', async () => {
    const on = trailApi(() => Promise.resolve({ recorded: true, stored_steps: 1 }))
    const off = trailApi(() => Promise.resolve({ recorded: false, stored_steps: 0 }))
    expect(await sendTrailBatch(on, 'p1', 's1', BODY)).toBe('recorded')
    expect(await sendTrailBatch(off, 'p1', 's1', BODY)).toBe('disabled')
    expect(await listTrailBatches()).toEqual([])
  })

  it('queues an offline batch in the shared offline queue and kicks the drain', async () => {
    const kicked = vi.fn()
    window.addEventListener(QUEUE_APPENDED_EVENT, kicked)
    const api = trailApi(() => Promise.reject(new OfflineError()))
    expect(await sendTrailBatch(api, 'p1', 's1', BODY, { newId: () => 'ev-1', now: () => 7 })).toBe(
      'queued'
    )
    window.removeEventListener(QUEUE_APPENDED_EVENT, kicked)
    expect(kicked).toHaveBeenCalledTimes(1)
    expect(await listTrailBatches()).toEqual([
      {
        event_id: 'ev-1',
        kind: 'reading_trail',
        profile_id: 'p1',
        storybook_id: 's1',
        body: BODY,
        queued_at: 7,
      },
    ])
    // Reading-state consumers never see a trail batch.
    expect(await listQueue()).toEqual([])
  })

  it('drops a permanently rejected batch without queueing it', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const api = trailApi(() => Promise.reject(httpError(422)))
    expect(await sendTrailBatch(api, 'p1', 's1', BODY)).toBe('dropped')
    expect(await listTrailBatches()).toEqual([])
  })

  it('never rejects, even when the queue write fails', async () => {
    vi.spyOn(db, 'enqueueTrailBatch').mockRejectedValue(new TypeError('IndexedDB is unavailable'))
    const api = trailApi(() => Promise.reject(new OfflineError()))
    await expect(sendTrailBatch(api, 'p1', 's1', BODY)).resolves.toBe('dropped')
  })
})

describe('replayQueue and queued trail batches', () => {
  async function queueTwo(): Promise<void> {
    const offline = trailApi(() => Promise.reject(new OfflineError()))
    let n = 0
    const newId = () => `ev-${String(++n)}`
    await sendTrailBatch(offline, 'p1', 's1', BODY, { newId, now: () => 1 })
    await sendTrailBatch(offline, 'p1', 's1', BODY, { newId, now: () => 2 })
  }

  it('drains queued trail batches and keeps them on an offline failure', async () => {
    await queueTwo()
    const stillOffline = trailApi(() => Promise.reject(new OfflineError()))
    await replayQueue({ putReadingState: vi.fn(), readingTrail: stillOffline })
    expect(await listTrailBatches()).toHaveLength(2)

    const postBatch = vi.fn(() => Promise.resolve({ recorded: true, stored_steps: 1 }))
    await replayQueue({ putReadingState: vi.fn(), readingTrail: { postBatch } })
    expect(postBatch).toHaveBeenCalledTimes(2)
    expect(postBatch).toHaveBeenCalledWith('p1', 's1', BODY)
    expect(await listTrailBatches()).toEqual([])
  })

  it('drops a batch the server rejects so it cannot wedge the queue', async () => {
    await queueTwo()
    const rejecting = trailApi(() => Promise.reject(httpError(422)))
    await replayQueue({ putReadingState: vi.fn(), readingTrail: rejecting })
    expect(await listTrailBatches()).toEqual([])
  })

  it('replayQueue reports nothing for trail batches', async () => {
    await queueTwo()
    await enqueueWrite({
      event_id: 'rs-1',
      profile_id: 'p1',
      storybook_id: 's1',
      base_revision: 0,
      state: {
        current_node: 'n_open',
        var_state: {},
        path: ['n_open'],
        visit_set: ['n_open'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
      queued_at: 3,
    })
    const putReadingState = vi.fn().mockResolvedValue({
      status: 200,
      row: {
        current_node: 'n_open',
        var_state: {},
        path: ['n_open'],
        visit_set: ['n_open'],
        version: 1,
        state_revision: 1,
        save_slots: {},
      },
    })
    const online = trailApi(() => Promise.resolve({ recorded: true, stored_steps: 1 }))
    const outcome = await replayQueue({ putReadingState, readingTrail: online })
    // Only the reading-state write counts; trail batches are silent.
    expect(outcome).toEqual({ replayed: 1, conflicts: [], failed: [] })
    expect(putReadingState).toHaveBeenCalledTimes(1)
    expect(await listQueue()).toEqual([])
    expect(await listTrailBatches()).toEqual([])
  })

  it('leaves trail batches queued when no trail port is wired', async () => {
    await queueTwo()
    await replayQueue({ putReadingState: vi.fn() })
    expect(await listTrailBatches()).toHaveLength(2)
  })
})
