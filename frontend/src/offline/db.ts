/**
 * IndexedDB cache for offline reading (idb wrapper).
 *
 * The server is canonical; this is a cache only. Three stores back the reader:
 * - `storybooks`: downloaded immutable story blobs, keyed by `id@version`.
 * - `reading_states`: the latest known reading state per profile+story.
 * - `offline_queue`: reading-state writes made while offline, replayed in order
 *   on reconnect (each carries an `event_id` so the server can dedupe replays).
 */

import { type DBSchema, type IDBPDatabase, openDB } from 'idb'

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
}

const DB_NAME = 'cyo-reader'
const DB_VERSION = 1

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
    upgrade(db) {
      db.createObjectStore('storybooks')
      db.createObjectStore('reading_states')
      db.createObjectStore('offline_queue', { keyPath: 'event_id' })
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

/** Reset the cached database handle (test isolation helper). */
export function _resetDbHandle(): void {
  _db = null
}
