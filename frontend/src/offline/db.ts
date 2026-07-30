/**
 * IndexedDB cache for offline reading (idb wrapper).
 *
 * The server is canonical; this is a cache only. Seven stores back the reader:
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
 * - `profile_shelf`: the last authoritative library list seen for each
 *   profile on this device (offline-copy revocation, see offline/revocation.ts
 *   and roadmap Phase 5 G8/A5). `storybooks` is keyed by `id@version` only,
 *   not by profile, because a book can be legitimately assigned to more than
 *   one sibling profile on the same device; this store is what lets
 *   revocation tell "nobody on this device may read this book anymore" apart
 *   from "this profile lost it, but a sibling still has it".
 * - `library_lists`: the last-good library list per profile (UX-K1 offline
 *   shelf).
 * - `personalization_values`: the resolved ADR-023 values payload for one book,
 *   keyed by `storybook_id`. Keyed by book rather than by subject profile because
 *   the reader only ever holds a book id: the subject profile id lives inside the
 *   payload and is unknowable offline. A subject-scoped purge therefore scans this
 *   store's bounded key set (see offline/revocation.ts). Never merged into
 *   `storybooks`, which is deliberately device-wide and profile-independent.
 */

import { type DBSchema, type IDBPDatabase, openDB } from 'idb'

import type { DeviceGrant } from '../auth/deviceGrant'
import type { LibraryItemView } from '../library/libraryApi'
import type { ValuesPayload } from '../player/personalization'
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

/** A profile's last known authoritative shelf (offline-copy revocation). */
export interface ProfileShelfSnapshot {
  profile_id: string
  storybook_ids: string[]
}

/** One cached values payload, paired with the book it was resolved for. */
export interface PersonalizationValuesEntry {
  storybook_id: string
  payload: ValuesPayload
}

interface ReaderDB extends DBSchema {
  storybooks: { key: string; value: Storybook }
  reading_states: { key: string; value: ReadingState }
  offline_queue: { key: string; value: QueuedWrite }
  device_grant: { key: string; value: DeviceGrant }
  // The last-good library list per profile, so an offline kid still sees a
  // bookshelf (UX-K1) rather than a dead-end "Try again" that can never
  // succeed. Keyed by profileId.
  library_lists: { key: string; value: LibraryItemView[] }
  profile_shelf: { key: string; value: ProfileShelfSnapshot }
  personalization_values: { key: string; value: ValuesPayload }
}

const DB_NAME = 'cyo-reader'
const DB_VERSION = 4
/** Singleton key: one device grant per device. */
const DEVICE_GRANT_KEY = 'current'

function storyKey(id: string, version: number): string {
  return `${id}@${version}`
}

function stateKey(profileId: string, storybookId: string): string {
  return `${profileId}:${storybookId}`
}

let _db: Promise<IDBPDatabase<ReaderDB>> | null = null

/**
 * Ask the browser to exempt this origin from best-effort storage eviction, so
 * downloaded stories survive iOS Safari's storage-pressure purges. Idempotent
 * and safe to call on every open: it no-ops when already granted or unsupported.
 */
export async function requestPersistentStorage(): Promise<boolean> {
  const storage = typeof navigator === 'undefined' ? undefined : navigator.storage
  if (!storage?.persist) return false
  if (await storage.persisted?.()) return true
  return storage.persist()
}

/** Open (or reuse) the reader IndexedDB database. */
export function getDb(): Promise<IDBPDatabase<ReaderDB>> {
  if (_db !== null) return _db
  // Best-effort: ask for durable storage the first time we touch IndexedDB.
  // Fire-and-forget; a rejection or unsupported browser must not block opening.
  void requestPersistentStorage()
  const opening = openDB<ReaderDB>(DB_NAME, DB_VERSION, {
    // #ASSUME: data-integrity: idb's upgrade callback receives the OLD
    // version (0 for a brand-new database), and each `if` runs the schema
    // change for every version the open needed to pass through, so a
    // brand-new database (oldVersion 0) creates all stores in one pass, an
    // existing v1 database (oldVersion 1) gains `device_grant`, `library_lists`,
    // and `profile_shelf`, an existing v2 database (oldVersion 2) gains
    // `library_lists` and `profile_shelf`, and an existing v3 database
    // (oldVersion 3) gains `personalization_values`.
    // #VERIFY: db.test.ts "creates the device_grant store on a fresh
    // database", the v1-to-v3 and v2-to-v3 migration tests, "creates the
    // store when upgrading a v3 database to v4", "keeps the pre-existing
    // stores reachable across the v4 upgrade", and offline/db.test.ts's
    // existing stores stay reachable across every migration path.
    upgrade(db, oldVersion) {
      if (oldVersion < 1) {
        db.createObjectStore('storybooks')
        db.createObjectStore('reading_states')
        db.createObjectStore('offline_queue', { keyPath: 'event_id' })
      }
      if (oldVersion < 2) {
        db.createObjectStore('device_grant')
      }
      if (oldVersion < 3) {
        db.createObjectStore('library_lists')
        db.createObjectStore('profile_shelf')
      }
      if (oldVersion < 4) {
        db.createObjectStore('personalization_values')
      }
    },
    // #CRITICAL: timing (ARCH-M5): without these callbacks a DB_VERSION bump
    // could hang every new tab. `blocking` fires on THIS (older) connection when
    // a newer-version open is waiting; close it and drop the cached handle so
    // the upgrade proceeds and our next op reopens at the new version, instead
    // of the new tab waiting forever on a connection an old tab never released.
    // #VERIFY: db.test.ts "closes and reopens when a newer version is blocking".
    blocking() {
      void _db?.then((db) => db.close()).catch(() => undefined)
      _db = null
    },
    // This tab wants to upgrade but an older connection elsewhere has not closed
    // yet; surfaced so an "app won't load" incident is diagnosable.
    blocked() {
      console.warn('cyo-reader: IndexedDB upgrade blocked by an older tab')
    },
    // The connection closed unexpectedly (e.g. the browser evicted it); drop the
    // cached handle so the next op reopens cleanly.
    terminated() {
      _db = null
    },
  })
  _db = opening
  // #CRITICAL: external-resources: never memoize a REJECTED open. Caching the
  // rejection would turn one transient failure (a blocked upgrade, a quota
  // error, a private-mode restriction) into a session-long outage of offline
  // reading, the write queue, AND every personalization purge, until a full
  // reload. Clear the memo on rejection so the next getDb() retries; the
  // identity guard keeps this handler from clobbering a newer open that
  // blocking()/terminated() may have allowed to start in the meantime.
  // #VERIFY: db.test.ts "retries the open after a rejected first attempt
  // instead of memoizing the failure".
  void opening.catch(() => {
    if (_db === opening) _db = null
  })
  return opening
}

/** Cache the last-good library list for a profile (UX-K1 offline shelf). */
export async function cacheLibraryList(profileId: string, items: LibraryItemView[]): Promise<void> {
  const db = await getDb()
  await db.put('library_lists', items, profileId)
}

/** Read the cached library list for a profile, or undefined if none. */
export async function getCachedLibraryList(
  profileId: string
): Promise<LibraryItemView[] | undefined> {
  const db = await getDb()
  return db.get('library_lists', profileId)
}

/** Cache the resolved values payload for one book (ADR-023 P6). */
export async function cachePersonalizationValues(
  storybookId: string,
  payload: ValuesPayload
): Promise<void> {
  const db = await getDb()
  await db.put('personalization_values', payload, storybookId)
}

/** Read the cached values payload for one book, or undefined if none. */
export async function getCachedPersonalizationValues(
  storybookId: string
): Promise<ValuesPayload | undefined> {
  const db = await getDb()
  return db.get('personalization_values', storybookId)
}

/** Drop one book's cached values payload. */
export async function deletePersonalizationValues(storybookId: string): Promise<void> {
  const db = await getDb()
  await db.delete('personalization_values', storybookId)
}

/**
 * List every cached values payload with its book id.
 *
 * The bounded read a subject-scoped purge needs: the store's key is the book, so
 * "forget everything about this child" has to look inside each payload. Bounded
 * by the number of books downloaded on one device, the same assumption
 * `listCachedStorybookIds` already makes.
 */
export async function listPersonalizationValues(): Promise<PersonalizationValuesEntry[]> {
  const db = await getDb()
  const keys = await db.getAllKeys('personalization_values')
  const entries: PersonalizationValuesEntry[] = []
  for (const key of keys) {
    const payload = await db.get('personalization_values', key)
    if (payload !== undefined) entries.push({ storybook_id: key, payload })
  }
  return entries
}

/**
 * Clear every cached values payload.
 *
 * Called on guardian sign-out / device handover, beside `clearReadingStates`, so
 * a returned device retains no child's personalization values at rest.
 */
export async function clearPersonalizationValues(): Promise<void> {
  const db = await getDb()
  await db.clear('personalization_values')
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

/**
 * Clear every cached reading state.
 *
 * Called on guardian sign-out / device handover so a returned device does not
 * retain any child's reading progress at rest (SEC-F5).
 */
export async function clearReadingStates(): Promise<void> {
  const db = await getDb()
  await db.clear('reading_states')
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

/** Remove a single profile's locally-cached reading state (offline-copy revocation). */
export async function deleteReadingState(profileId: string, storybookId: string): Promise<void> {
  const db = await getDb()
  await db.delete('reading_states', stateKey(profileId, storybookId))
}

/** Storybook ids this profile has a locally-cached reading state for. */
export async function listReadingStateStorybookIds(profileId: string): Promise<string[]> {
  const db = await getDb()
  const keys = await db.getAllKeys('reading_states')
  const prefix = `${profileId}:`
  return keys.filter((key) => key.startsWith(prefix)).map((key) => key.slice(prefix.length))
}

/** Remove every cached version of a storybook (offline-copy revocation). */
export async function deleteStorybooksById(id: string): Promise<void> {
  const db = await getDb()
  const keys = await db.getAllKeys('storybooks')
  const prefix = `${id}@`
  for (const key of keys) {
    if (key.startsWith(prefix)) {
      await db.delete('storybooks', key)
    }
  }
}

/** Distinct storybook ids currently cached on this device, across every version. */
export async function listCachedStorybookIds(): Promise<string[]> {
  const db = await getDb()
  const keys = await db.getAllKeys('storybooks')
  return [...new Set(keys.map((key) => key.slice(0, key.lastIndexOf('@'))))]
}

/**
 * Persist a profile's latest authoritative shelf (offline-copy revocation;
 * see offline/revocation.ts). Overwrites the previous snapshot: the caller
 * always passes the full, fresh list from a successful library fetch, never
 * a partial update.
 */
export async function putProfileShelf(profileId: string, storybookIds: string[]): Promise<void> {
  const db = await getDb()
  await db.put('profile_shelf', { profile_id: profileId, storybook_ids: storybookIds }, profileId)
}

/** Every profile shelf snapshot known on this device. */
export async function getAllProfileShelves(): Promise<ProfileShelfSnapshot[]> {
  const db = await getDb()
  return db.getAll('profile_shelf')
}

/** Reset the cached database handle (test isolation helper). */
export function _resetDbHandle(): void {
  _db = null
}
