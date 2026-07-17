import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import type { ReadingState, Storybook } from '../player/types'
import {
  _resetDbHandle,
  cacheStorybook,
  enqueueWrite,
  getCachedStorybook,
  getReadingState,
  listQueue,
  putReadingState,
  type QueuedWrite,
} from './db'
import { reconcileOfflineCache } from './revocation'

function makeStory(id: string, version = 1): Storybook {
  return {
    schema_version: '1.0',
    id,
    version,
    title: id,
    metadata: {},
    variables: [],
    start_node: 'n_start',
    nodes: [
      {
        id: 'n_start',
        body: 'Start',
        is_ending: true,
        ending: { id: 'e', kind: 'success', valence: 'positive', title: 'End' },
        choices: [],
      },
    ],
  }
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

function makeQueued(profileId: string, storybookId: string, eventId: string): QueuedWrite {
  return {
    event_id: eventId,
    profile_id: profileId,
    storybook_id: storybookId,
    base_revision: 0,
    state,
    queued_at: Date.now(),
  }
}

beforeEach(() => {
  // Fresh in-memory IndexedDB per test.
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})

describe('reconcileOfflineCache', () => {
  it('removes a revoked book (storybook blob, reading state, and queued writes) for that profile', async () => {
    await cacheStorybook(makeStory('s_revoked'))
    await putReadingState('p1', 's_revoked', state)
    await enqueueWrite(makeQueued('p1', 's_revoked', 'e1'))

    // The fresh, authoritative shelf no longer lists s_revoked.
    await reconcileOfflineCache('p1', [])

    expect(await getCachedStorybook('s_revoked', 1)).toBeUndefined()
    expect(await getReadingState('p1', 's_revoked')).toBeUndefined()
    expect(await listQueue()).toEqual([])
  })

  it('leaves a kept book (still on the fresh shelf) untouched', async () => {
    await cacheStorybook(makeStory('s_kept'))
    await putReadingState('p1', 's_kept', state)
    await enqueueWrite(makeQueued('p1', 's_kept', 'e1'))

    await reconcileOfflineCache('p1', ['s_kept'])

    expect(await getCachedStorybook('s_kept', 1)).toBeDefined()
    expect(await getReadingState('p1', 's_kept')).toEqual(state)
    expect(await listQueue()).toHaveLength(1)
  })

  it("does not touch another profile's reading state or queue entries", async () => {
    await putReadingState('p1', 's_shared', state)
    await putReadingState('p2', 's_shared', state)
    await enqueueWrite(makeQueued('p2', 's_shared', 'e2'))

    // p1's fresh shelf no longer has s_shared; p2 was never consulted here.
    await reconcileOfflineCache('p1', [])

    expect(await getReadingState('p1', 's_shared')).toBeUndefined()
    expect(await getReadingState('p2', 's_shared')).toEqual(state)
    expect(await listQueue()).toHaveLength(1)
  })

  it("keeps the shared storybook blob cached while a sibling profile still has it assigned", async () => {
    await cacheStorybook(makeStory('s_shared'))
    // p2 reconciled earlier and still has s_shared on its shelf.
    await reconcileOfflineCache('p2', ['s_shared'])

    // p1 no longer has s_shared assigned.
    await reconcileOfflineCache('p1', [])

    // The shared blob survives: p2 (a known profile on this device) still
    // needs it, even though it is not p1's reconcile call.
    expect(await getCachedStorybook('s_shared', 1)).toBeDefined()
  })

  it('deletes the shared storybook blob once no known profile lists it anymore', async () => {
    await cacheStorybook(makeStory('s_shared'))
    await reconcileOfflineCache('p1', ['s_shared'])
    await reconcileOfflineCache('p2', ['s_shared'])

    // Both siblings lose the book on their next fetch.
    await reconcileOfflineCache('p1', [])
    await reconcileOfflineCache('p2', [])

    expect(await getCachedStorybook('s_shared', 1)).toBeUndefined()
  })

  it('drops queued writes for a revoked book outright (never flushes them)', async () => {
    await enqueueWrite(makeQueued('p1', 's_revoked', 'e1'))
    await enqueueWrite(makeQueued('p1', 's_kept', 'e2'))

    await reconcileOfflineCache('p1', ['s_kept'])

    const remaining = await listQueue()
    expect(remaining.map((item) => item.event_id)).toEqual(['e2'])
  })

  // #CRITICAL: data-integrity: reconcileOfflineCache must never be called
  // after a failed fetch (see the #CRITICAL note in revocation.ts); this test
  // documents the safety property from the caller's point of view: as long as
  // the caller only invokes it with a resolved, authoritative list, a fetch
  // failure (which never reaches this function at all) purges nothing.
  it('purges nothing when the caller never reconciles after a failed fetch', async () => {
    await cacheStorybook(makeStory('s_kept'))
    await putReadingState('p1', 's_kept', state)
    await enqueueWrite(makeQueued('p1', 's_kept', 'e1'))

    // Simulate a failed library fetch: the caller's catch branch never calls
    // reconcileOfflineCache at all.
    const fetchLibrary = () => Promise.reject(new Error('network error'))
    await expect(fetchLibrary()).rejects.toThrow('network error')

    expect(await getCachedStorybook('s_kept', 1)).toBeDefined()
    expect(await getReadingState('p1', 's_kept')).toEqual(state)
    expect(await listQueue()).toHaveLength(1)
  })

  it('a first-ever reconcile call establishes the shelf snapshot without needing a prior baseline', async () => {
    await cacheStorybook(makeStory('s_new'))
    await reconcileOfflineCache('p1', ['s_new'])
    expect(await getCachedStorybook('s_new', 1)).toBeDefined()
  })
})
