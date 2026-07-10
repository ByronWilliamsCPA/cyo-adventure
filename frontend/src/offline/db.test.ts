import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import type { ReadingState, Storybook } from '../player/types'
import {
  _resetDbHandle,
  cacheStorybook,
  dequeue,
  enqueueWrite,
  getCachedStorybook,
  getReadingState,
  listQueue,
  putReadingState,
  type QueuedWrite,
} from './db'

const story: Storybook = {
  schema_version: '1.0',
  id: 's_demo',
  version: 1,
  title: 'Demo',
  metadata: {},
  variables: [],
  start_node: 'n_start',
  nodes: [
    {
      id: 'n_start',
      body: 'Start',
      is_ending: false,
      choices: [{ id: 'c', label: 'go', target: 'n_end' }],
    },
    {
      id: 'n_end',
      body: 'End',
      is_ending: true,
      ending: { id: 'e', kind: 'success', valence: 'positive', title: 'End' },
      choices: [],
    },
  ],
}

const state: ReadingState = {
  current_node: 'n_start',
  var_state: {},
  path: ['n_start'],
  visit_set: ['n_start'],
  version: 1,
  state_revision: 1,
  save_slots: {},
}

beforeEach(() => {
  // Fresh in-memory IndexedDB per test.
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})

describe('offline IndexedDB cache', () => {
  it('caches and reads back a story blob by id and version', async () => {
    await cacheStorybook(story)
    const cached = await getCachedStorybook('s_demo', 1)
    expect(cached?.id).toBe('s_demo')
    expect(await getCachedStorybook('s_demo', 2)).toBeUndefined()
  })

  it('persists and reads reading state per profile and story', async () => {
    await putReadingState('p1', 's_demo', state)
    const got = await getReadingState('p1', 's_demo')
    expect(got?.current_node).toBe('n_start')
    expect(await getReadingState('p2', 's_demo')).toBeUndefined()
  })

  it('queues, lists in order, and dequeues offline writes', async () => {
    const make = (id: string, at: number): QueuedWrite => ({
      event_id: id,
      profile_id: 'p1',
      storybook_id: 's_demo',
      base_revision: 0,
      state,
      queued_at: at,
    })
    await enqueueWrite(make('e2', 200))
    await enqueueWrite(make('e1', 100))
    const queue = await listQueue()
    expect(queue.map((q) => q.event_id)).toEqual(['e1', 'e2'])
    await dequeue('e1')
    const after = await listQueue()
    expect(after.map((q) => q.event_id)).toEqual(['e2'])
  })
})
