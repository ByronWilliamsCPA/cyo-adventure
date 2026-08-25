import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import type { Storybook } from '../player/types'
import { _resetDbHandle, cacheStorybook, getCachedStorybook } from './db'
import { _resetContentHashes, evictStaleOfflineBooks, type StaleCheckItem } from './revocation'

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

function item(id: string, version: number, contentHash?: string): StaleCheckItem {
  return contentHash === undefined ? { id, version } : { id, version, content_hash: contentHash }
}

const HASH_A = 'sha256:aaaa'
const HASH_B = 'sha256:bbbb'

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  localStorage.clear()
  _resetContentHashes()
})

describe('evictStaleOfflineBooks', () => {
  it('keeps a cached book whose content identity still matches', async () => {
    await cacheStorybook(makeStory('s1'))
    // First pass records the advertised identity (and verifies the pre-existing
    // entry once); the second pass is the one under test.
    await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    await cacheStorybook(makeStory('s1'))

    const outcome = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])

    expect(outcome).toEqual({ changed: 0, unverified: 0, fresh: 1 })
    expect(await getCachedStorybook('s1', 1)).toBeDefined()
  })

  it('evicts a cached book whose content changed under an unchanged version', async () => {
    await cacheStorybook(makeStory('s1'))
    await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    await cacheStorybook(makeStory('s1'))

    // The production defect: same id, same version, different bytes.
    const outcome = await evictStaleOfflineBooks([item('s1', 1, HASH_B)])

    expect(outcome).toEqual({ changed: 1, unverified: 0, fresh: 0 })
    expect(await getCachedStorybook('s1', 1)).toBeUndefined()
  })

  it('evicts a cached book this device has no recorded identity for', async () => {
    // The entire population the production retrofit affected: cached before
    // any content hash existed, so absence must read as "unknown", not "matches".
    await cacheStorybook(makeStory('s1'))

    const outcome = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])

    expect(outcome).toEqual({ changed: 0, unverified: 1, fresh: 0 })
    expect(await getCachedStorybook('s1', 1)).toBeUndefined()
  })

  it('verifies an unrecorded book exactly once rather than on every shelf load', async () => {
    // The loop guard. Without recording the advertised identity at eviction
    // time, the re-downloaded entry would read as unverified again on the next
    // shelf load and re-download forever.
    await cacheStorybook(makeStory('s1'))
    await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    // ReaderPage's existing cache-miss path is what re-downloads.
    await cacheStorybook(makeStory('s1'))

    const second = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    const third = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])

    expect(second).toEqual({ changed: 0, unverified: 0, fresh: 1 })
    expect(third).toEqual({ changed: 0, unverified: 0, fresh: 1 })
    expect(await getCachedStorybook('s1', 1)).toBeDefined()
  })

  it('does not charge a first download a throwaway re-download', async () => {
    // A book listed on the shelf but not yet cached still gets its advertised
    // identity recorded, so the download that follows is already accounted for.
    await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    await cacheStorybook(makeStory('s1'))

    const outcome = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])

    expect(outcome).toEqual({ changed: 0, unverified: 0, fresh: 1 })
    expect(await getCachedStorybook('s1', 1)).toBeDefined()
  })

  it('leaves a cached book alone when the server advertised no content hash', async () => {
    // A pre-field backend or a hand-built item is silence, not evidence of
    // change; evicting on it would wipe the offline library on a bad payload.
    await cacheStorybook(makeStory('s1'))

    const outcome = await evictStaleOfflineBooks([item('s1', 1)])

    expect(outcome).toEqual({ changed: 0, unverified: 0, fresh: 0 })
    expect(await getCachedStorybook('s1', 1)).toBeDefined()
  })

  it('evicts only the drifted version, leaving another cached version of the same book', async () => {
    await cacheStorybook(makeStory('s1', 1))
    await cacheStorybook(makeStory('s1', 2))
    await evictStaleOfflineBooks([item('s1', 1, HASH_A), item('s1', 2, HASH_A)])
    await cacheStorybook(makeStory('s1', 1))
    await cacheStorybook(makeStory('s1', 2))

    await evictStaleOfflineBooks([item('s1', 1, HASH_A), item('s1', 2, HASH_B)])

    expect(await getCachedStorybook('s1', 1)).toBeDefined()
    expect(await getCachedStorybook('s1', 2)).toBeUndefined()
  })

  it('leaves a sibling profile recorded identity intact across another profile shelf load', async () => {
    // `storybooks` is device-wide; a shelf fetch for one profile must not
    // discard what an earlier fetch verified for a book only a sibling lists,
    // or that book would be re-downloaded on every alternating shelf load.
    await cacheStorybook(makeStory('s_sibling'))
    await evictStaleOfflineBooks([item('s_sibling', 1, HASH_A)])
    await cacheStorybook(makeStory('s_sibling'))
    await cacheStorybook(makeStory('s_mine'))

    // A shelf load for the other profile, which does not list s_sibling.
    await evictStaleOfflineBooks([item('s_mine', 1, HASH_A)])
    await cacheStorybook(makeStory('s_mine'))
    const outcome = await evictStaleOfflineBooks([item('s_sibling', 1, HASH_A)])

    expect(outcome).toEqual({ changed: 0, unverified: 0, fresh: 1 })
    expect(await getCachedStorybook('s_sibling', 1)).toBeDefined()
  })

  it('re-verifies once when the recorded identities are lost but the cache survives', async () => {
    // localStorage can be cleared independently of IndexedDB. The degrade must
    // be one extra verification pass, never a wrong "still fresh" answer.
    await cacheStorybook(makeStory('s1'))
    await evictStaleOfflineBooks([item('s1', 1, HASH_A)])
    await cacheStorybook(makeStory('s1'))
    _resetContentHashes()

    const outcome = await evictStaleOfflineBooks([item('s1', 1, HASH_A)])

    expect(outcome).toEqual({ changed: 0, unverified: 1, fresh: 0 })
    expect(await getCachedStorybook('s1', 1)).toBeUndefined()
  })

  it('forgets identities for payloads that are neither cached nor on the shelf', async () => {
    // Keeps the map bounded by what the device holds rather than by everything
    // it has ever listed.
    await evictStaleOfflineBooks([item('s_gone', 1, HASH_A)])
    await evictStaleOfflineBooks([item('s_other', 1, HASH_A)])

    const raw = localStorage.getItem('offline_story_content_hash')
    expect(raw).not.toBeNull()
    const map: unknown = JSON.parse(raw ?? '{}')
    expect(map).toEqual({ 's_other@1': HASH_A })
  })
})
