import 'fake-indexeddb/auto'

import { openDB } from 'idb'
import { beforeEach, describe, expect, it } from 'vitest'

import type { DeviceGrant } from '../auth/deviceGrant'
import type { ValuesPayload } from '../player/personalization'
import type { ReadingState, Storybook } from '../player/types'
import type { LibraryItemView } from '../library/libraryApi'
import {
  _resetDbHandle,
  cacheLibraryList,
  cachePersonalizationValues,
  cacheStorybook,
  clearDeviceGrantMirror,
  clearPersonalizationValues,
  deletePersonalizationValues,
  deleteReadingState,
  deleteStorybooksById,
  dequeue,
  enqueueWrite,
  getAllProfileShelves,
  getCachedLibraryList,
  getCachedPersonalizationValues,
  getCachedStorybook,
  getDeviceGrantMirror,
  getReadingState,
  listCachedStorybookIds,
  listPersonalizationValues,
  listQueue,
  listReadingStateStorybookIds,
  putDeviceGrantMirror,
  putProfileShelf,
  putReadingState,
  type PersonalizationValuesEntry,
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

const valuesPayload: ValuesPayload = {
  subject_profile_id: 'p_subject',
  ring: 1,
  policy_version: 'ring1-no-consent-required',
  resolved_at: '2026-07-29T00:00:00Z',
  values: { protagonist_first_name: 'Maya' },
  sentinel_pattern: "\\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\\}",
  slot_bindings: { HERO: 'protagonist_first_name' },
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

  it('migrates a v2 database to v3 by adding only the profile_shelf store', async () => {
    // Reproduce a real pre-revocation v2 database: device_grant exists, but
    // profile_shelf does not.
    const v2 = await openDB(DB_NAME, 2, {
      upgrade(db) {
        db.createObjectStore('storybooks')
        db.createObjectStore('reading_states')
        db.createObjectStore('offline_queue', { keyPath: 'event_id' })
        db.createObjectStore('device_grant')
      },
    })
    v2.close()

    // getDb() opens at DB_VERSION (3), so idb's upgrade fires with
    // oldVersion === 2: both `oldVersion < 1` and `oldVersion < 2` blocks are
    // skipped and only `profile_shelf` is created.
    await putProfileShelf('p1', ['s1', 's2'])
    expect(await getAllProfileShelves()).toEqual([
      { profile_id: 'p1', storybook_ids: ['s1', 's2'] },
    ])

    // Pre-existing v1/v2 stores still work and lost no data.
    await cacheStorybook(story)
    expect((await getCachedStorybook('s_demo', 1))?.id).toBe('s_demo')
  })

  describe('offline-copy revocation primitives', () => {
    it('deletes a single profile reading state without touching another profile', async () => {
      await putReadingState('p1', 's_demo', state)
      await putReadingState('p2', 's_demo', state)
      await deleteReadingState('p1', 's_demo')
      expect(await getReadingState('p1', 's_demo')).toBeUndefined()
      expect(await getReadingState('p2', 's_demo')).toEqual(state)
    })

    it('lists only the storybook ids a given profile has reading state for', async () => {
      await putReadingState('p1', 's_demo', state)
      await putReadingState('p1', 's_other', state)
      await putReadingState('p2', 's_demo', state)
      expect((await listReadingStateStorybookIds('p1')).sort()).toEqual(['s_demo', 's_other'])
      expect(await listReadingStateStorybookIds('p2')).toEqual(['s_demo'])
    })

    it('deletes every cached version of a storybook by id', async () => {
      await cacheStorybook(story)
      await cacheStorybook({ ...story, version: 2 })
      await cacheStorybook({ ...story, id: 's_other' })
      await deleteStorybooksById('s_demo')
      expect(await getCachedStorybook('s_demo', 1)).toBeUndefined()
      expect(await getCachedStorybook('s_demo', 2)).toBeUndefined()
      expect(await getCachedStorybook('s_other', 1)).toBeDefined()
    })

    it('lists distinct cached storybook ids across versions', async () => {
      await cacheStorybook(story)
      await cacheStorybook({ ...story, version: 2 })
      await cacheStorybook({ ...story, id: 's_other' })
      expect((await listCachedStorybookIds()).sort()).toEqual(['s_demo', 's_other'])
    })

    it('round-trips a profile shelf snapshot and overwrites on the next put', async () => {
      await putProfileShelf('p1', ['s1', 's2'])
      expect(await getAllProfileShelves()).toEqual([
        { profile_id: 'p1', storybook_ids: ['s1', 's2'] },
      ])
      await putProfileShelf('p1', ['s1'])
      expect(await getAllProfileShelves()).toEqual([{ profile_id: 'p1', storybook_ids: ['s1'] }])
    })
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

describe('personalization values store', () => {
  beforeEach(() => {
    _resetDbHandle()
  })

  it('round-trips a payload keyed by storybook id', async () => {
    await cachePersonalizationValues('s_demo', valuesPayload)
    expect(await getCachedPersonalizationValues('s_demo')).toEqual(valuesPayload)
  })

  it('returns undefined for a book with no cached payload', async () => {
    expect(await getCachedPersonalizationValues('s_never_cached')).toBeUndefined()
  })

  it('deletes one book payload without touching another', async () => {
    await cachePersonalizationValues('s_a', valuesPayload)
    await cachePersonalizationValues('s_b', valuesPayload)
    await deletePersonalizationValues('s_a')
    expect(await getCachedPersonalizationValues('s_a')).toBeUndefined()
    expect(await getCachedPersonalizationValues('s_b')).toEqual(valuesPayload)
  })

  it('lists every cached entry with its key, for subject-scoped purges', async () => {
    await cachePersonalizationValues('s_a', valuesPayload)
    await cachePersonalizationValues('s_b', {
      ...valuesPayload,
      subject_profile_id: 'p_other',
    })
    const entries: PersonalizationValuesEntry[] = await listPersonalizationValues()
    expect(entries.map((e) => e.storybook_id).sort()).toEqual(['s_a', 's_b'])
  })

  it('clears every payload at once', async () => {
    await cachePersonalizationValues('s_a', valuesPayload)
    await clearPersonalizationValues()
    expect(await listPersonalizationValues()).toEqual([])
  })

  it('creates the store when upgrading a v3 database to v4', async () => {
    // Mirrors the existing v1-to-v3 and v2-to-v3 migration tests: open the
    // previous version explicitly, close it, then let db.ts upgrade.
    _resetDbHandle()
    const legacy = await openDB(DB_NAME, 3, {
      upgrade(db) {
        db.createObjectStore('storybooks')
        db.createObjectStore('reading_states')
        db.createObjectStore('offline_queue', { keyPath: 'event_id' })
        db.createObjectStore('device_grant')
        db.createObjectStore('library_lists')
        db.createObjectStore('profile_shelf')
      },
    })
    legacy.close()
    _resetDbHandle()

    await cachePersonalizationValues('s_after_upgrade', valuesPayload)
    expect(await getCachedPersonalizationValues('s_after_upgrade')).toEqual(valuesPayload)
  })

  it('keeps the pre-existing stores reachable across the v4 upgrade', async () => {
    await cacheStorybook(story)
    await putReadingState('p_1', story.id, state)
    await cachePersonalizationValues(story.id, valuesPayload)
    expect(await getCachedStorybook(story.id, story.version)).toEqual(story)
    expect(await getReadingState('p_1', story.id)).toEqual(state)
  })
})
