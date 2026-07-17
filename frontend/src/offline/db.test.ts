import 'fake-indexeddb/auto'

import { openDB } from 'idb'
import { beforeEach, describe, expect, it } from 'vitest'

import type { DeviceGrant } from '../auth/deviceGrant'
import type { ReadingState, Storybook } from '../player/types'
import type { LibraryItemView } from '../library/libraryApi'
import {
  _resetDbHandle,
  cacheLibraryList,
  cacheStorybook,
  clearDeviceGrantMirror,
  dequeue,
  enqueueWrite,
  getCachedLibraryList,
  getCachedStorybook,
  getDeviceGrantMirror,
  getReadingState,
  listQueue,
  putDeviceGrantMirror,
  putReadingState,
  type QueuedWrite,
} from './db'

// db.ts keeps DB_NAME private; mirror it here so the v1-migration test can open
// the same database at the previous version. A drift fails this test loudly.
const DB_NAME = 'cyo-reader'

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

  it('round-trips the device-grant mirror on a fresh (v2) database', async () => {
    const grant: DeviceGrant = {
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    }
    await putDeviceGrantMirror(grant)
    expect(await getDeviceGrantMirror()).toEqual(grant)
    await clearDeviceGrantMirror()
    expect(await getDeviceGrantMirror()).toBeUndefined()
  })

  it('migrates a v1 database additively (adds device_grant and library_lists)', async () => {
    // Reproduce the pre-ADR-014-Phase-3 on-disk state: a real v1 database with
    // exactly the three original stores. This is what an existing reader's
    // browser holds before the upgrade.
    const v1 = await openDB(DB_NAME, 1, {
      upgrade(db) {
        db.createObjectStore('storybooks')
        db.createObjectStore('reading_states')
        db.createObjectStore('offline_queue', { keyPath: 'event_id' })
      },
    })
    v1.close()

    // getDb() opens at the current DB_VERSION, so idb's upgrade fires with
    // oldVersion === 1: the `oldVersion < 1` block is skipped, and both
    // device_grant (< 2) and library_lists (< 3) are created. This is the
    // migration branch the fresh-database tests never exercise.
    const grant: DeviceGrant = {
      token: 'tok-2',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-2',
    }
    await putDeviceGrantMirror(grant)
    expect(await getDeviceGrantMirror()).toEqual(grant)

    // The migration must be additive: a pre-existing v1 store still works and
    // loses no data.
    await cacheStorybook(story)
    expect((await getCachedStorybook('s_demo', 1))?.id).toBe('s_demo')
  })
})

const libItem: LibraryItemView = {
  id: 's_demo',
  title: 'The Demo',
  version: 1,
  age_band: '5-8',
  tier: 1,
  reading_level_target: 2,
  node_count: 4,
  rating: null,
  progress: null,
  series_id: null,
  book_index: null,
  cover_url: null,
}

describe('library list cache (UX-K1)', () => {
  beforeEach(() => {
    _resetDbHandle()
  })

  it('round-trips a cached library list per profile', async () => {
    await cacheLibraryList('p1', [libItem])
    const got = await getCachedLibraryList('p1')
    expect(got).toHaveLength(1)
    expect(got?.[0].id).toBe('s_demo')
  })

  it('returns undefined for a profile with no cached list', async () => {
    expect(await getCachedLibraryList('nobody')).toBeUndefined()
  })

  it('isolates cached lists between profiles', async () => {
    await cacheLibraryList('p1', [libItem])
    expect(await getCachedLibraryList('p2')).toBeUndefined()
  })
})
