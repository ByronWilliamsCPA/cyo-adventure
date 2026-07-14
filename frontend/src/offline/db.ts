/**
 * IndexedDB cache for offline reading (idb wrapper).
 *
 * The server is canonical; this is a cache only. Four stores back the reader:
 * - `storybooks`: downloaded immutable story blobs, keyed by `id@version`.
 * - `reading_states`: the latest known reading state per profile+story.
 * - `offline_queue`: reading-state writes made while offline, replayed in order
 *   on reconnect (each carries an `event_id` so the server can dedupe replays).
 * - `device_grant`: a durable mirror of the device grant (ADR-014 Phase 3), a
 *   singleton row keyed by {@link DEVICE_GRANT_KEY}. `localStorage` is the
 *   primary store (auth/deviceGrant.ts); this mirror only exists so a
 *   localStorage clear (private-mode eviction, a user clearing site data)
 *   does not strand an otherwise-valid, still-unexpired grant, since
 *   IndexedDB survives a localStorage clear on most browsers.
 */

import { type DBSchema, type IDBPDatabase, openDB } from 'idb'

import type { DeviceGrant } from '../auth/deviceGrant'
import type { ReadingState, Storybook } from '../player/types'

export interface QueuedWrite {
  event_id: string
  profile_id: string
  storybook_id: string
  base_revision: number
  state: ReadingState
  device_id?: string
  queued_at: number
}

interface ReaderDB extends DBSchema {
  storybooks: { key: string; value: Storybook }
  reading_states: { key: string; value: ReadingState }
  offline_queue: { key: string; value: QueuedWrite }
  device_grant: { key: string; value: DeviceGrant }
}

const DB_NAME = 'cyo-reader'
const DB_VERSION = 2
/** Singleton key: one device grant per device. */
const DEVICE_GRANT_KEY = 'current'

function storyKey(id: string, version: number): string {
  return `${id}@${version}`
}

function stateKey(profileId: string, storybookId: string): string {
  return `${profileId}:${storybookId}`
}

let _db: Promise<IDBPDatabase<ReaderDB>> | null = null

/** Open (or reuse) the reader IndexedDB database. */
export function getDb(): Promise<IDBPDatabase<ReaderDB>> {
  _db ??= openDB<ReaderDB>(DB_NAME, DB_VERSION, {
    // #ASSUME: data-integrity: idb's upgrade callback receives the OLD
    // version (0 for a brand-new database), and each `if` runs the schema
    // change for every version the open needed to pass through, so a
    // brand-new database (oldVersion 0) creates all four stores in one pass,
    // and an existing v1 database (oldVersion 1) only gains `device_grant`.
    // #VERIFY: db.test.ts "creates the device_grant store on a fresh
    // database" and offline/db.test.ts's existing v1 stores stay reachable.
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        db.createObjectStore('storybooks')
        db.createObjectStore('reading_states')
        db.createObjectStore('offline_queue', { keyPath: 'event_id' })
      }
      if (oldVersion < 2) {
        db.createObjectStore('device_grant')
      }
    },
  })
  return _db
}

/** Cache a downloaded story blob for offline play. */
export async function cacheStorybook(story: Storybook): Promise<void> {
  const db = await getDb()
  await db.put('storybooks', story, storyKey(story.id, story.version))
}

/** Read a cached story blob, or undefined if it is not downloaded. */
export async function getCachedStorybook(
  id: string,
  version: number
): Promise<Storybook | undefined> {
  const db = await getDb()
  return db.get('storybooks', storyKey(id, version))
}

/** Persist the latest reading state locally. */
export async function putReadingState(
  profileId: string,
  storybookId: string,
  state: ReadingState
): Promise<void> {
  const db = await getDb()
  await db.put('reading_states', state, stateKey(profileId, storybookId))
}

/** Read the locally-cached reading state, if any. */
export async function getReadingState(
  profileId: string,
  storybookId: string
): Promise<ReadingState | undefined> {
  const db = await getDb()
  return db.get('reading_states', stateKey(profileId, storybookId))
}

/** Queue a reading-state write made while offline. */
export async function enqueueWrite(item: QueuedWrite): Promise<void> {
  const db = await getDb()
  await db.put('offline_queue', item)
}

/** List queued offline writes in insertion order (oldest first). */
export async function listQueue(): Promise<QueuedWrite[]> {
  const db = await getDb()
  const items = await db.getAll('offline_queue')
  return items.sort((a, b) => a.queued_at - b.queued_at)
}

/** Remove a queued write once the server has accepted it. */
export async function dequeue(eventId: string): Promise<void> {
  const db = await getDb()
  await db.delete('offline_queue', eventId)
}

/** Persist the durable device-grant mirror (ADR-014 Phase 3). */
export async function putDeviceGrantMirror(grant: DeviceGrant): Promise<void> {
  const db = await getDb()
  await db.put('device_grant', grant, DEVICE_GRANT_KEY)
}

/** Read the mirrored device grant, or undefined if none is stored. */
export async function getDeviceGrantMirror(): Promise<DeviceGrant | undefined> {
  const db = await getDb()
  return db.get('device_grant', DEVICE_GRANT_KEY)
}

/** Remove the mirrored device grant (mirrors a localStorage clear/revoke). */
export async function clearDeviceGrantMirror(): Promise<void> {
  const db = await getDb()
  await db.delete('device_grant', DEVICE_GRANT_KEY)
}

/** Reset the cached database handle (test isolation helper). */
export function _resetDbHandle(): void {
  _db = null
}
