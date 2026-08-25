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
 * - `reading_time_days` (W3.3): a per-(profile, reader-local date) active-reading-
 *   seconds bucket, keyed by `${profileId}:${date}`. `seconds` is the running
 *   local total (grows the instant the reader accumulates active time, online or
 *   off); `syncedSeconds` is how much of that total the server has acknowledged.
 *   A `pending` attempt (flushId + the exact delta/snapshot it represents) is
 *   frozen once minted so a retry-while-offline resends the SAME flush_id and
 *   delta rather than silently growing it (see offline/readingTimeSync.ts for
 *   why that distinction matters for the server's idempotency contract).
 * - `badge_seen` (W3.2): badge ids this device has already shown an unlock toast
 *   for, per profile (keyed by `${profileId}:${badgeId}`). Client-side "seen"
 *   state per the gamification recommendation section 5 ("badge seen-state lives
 *   client-side in IndexedDB, avoiding a table"): a badge a profile has earned
 *   but this device has not yet toasted stays toast-eligible; once toasted here
 *   it never re-toasts on this device, even across a badge re-fetch.
 */

import { type DBSchema, type IDBPDatabase, openDB } from 'idb'

import type { DeviceGrant } from '../auth/deviceGrant'
import type { LibraryItemView } from '../library/libraryApi'
import type { ValuesPayload } from '../player/personalization'
import type { ReadingState, Storybook } from '../player/types'
import {
  type BudgetGateResult,
  checkDownloadBudget,
  estimateByteSize,
  forgetStoryRecency,
  recordDownloadEviction,
  recordDownloadRefusal,
  recordStoryOpened,
} from './downloadBudget'

export interface QueuedWrite {
  event_id: string
  profile_id: string
  storybook_id: string
  base_revision: number
  state: ReadingState
  device_id?: string
  queued_at: number
  // #CRITICAL: data-integrity: monotonic tie-break for queued_at, which is a
  // Date.now() millisecond stamp. Two writes for one row can be enqueued inside
  // the same millisecond (saveProgress appends without a network round trip once
  // the row already has a queued write), and Array.prototype.sort is stable, so
  // without this the tie keeps db.getAll's key order, which is random-UUID
  // event_id order rather than insertion order. Replayed out of order the older
  // node is written last and the child's server position rewinds.
  // #VERIFY: sync.test.ts "replays same-millisecond writes in insertion order".
  // Optional so records written before this field existed still load; they
  // predate the multi-writer path and sort by queued_at alone.
  seq?: number
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

/**
 * A pending, not-yet-acknowledged reading-time flush attempt (W3.3).
 *
 * `flushId`/`deltaSeconds`/`snapshotSeconds` are frozen together the moment a
 * flush attempt is minted (see offline/readingTimeSync.ts), so a retry while
 * offline resends the EXACT same payload the server already knows how to
 * dedupe on `flush_id`, rather than silently growing the delta underneath an
 * id the server has already partially processed.
 */
export interface PendingReadingTimeFlush {
  flushId: string
  deltaSeconds: number
  /** `bucket.seconds` at the moment this attempt was minted; on success the
   * bucket's `syncedSeconds` is set to exactly this value (never `+=`), so a
   * successful ack can never double-count seconds accrued mid-flight. */
  snapshotSeconds: number
}

/** A profile's active-reading-seconds bucket for one reader-local day (W3.3). */
export interface ReadingTimeDayBucket {
  profileId: string
  /** Reader-local calendar date, `YYYY-MM-DD`.
   * #ASSUME: data integrity: this is the DEVICE's local calendar date, not
   * UTC, matching the accumulator hook's own day-boundary choice (see
   * reader/useReadingTimeAccumulator.ts). A read spanning local midnight
   * splits across two buckets exactly as a real day would; a day that
   * straddles a DST transition or a timezone change mid-read is accepted
   * imprecision for a literacy signal, not a billing ledger.
   * #VERIFY: offline/readingTimeSync.test.ts. */
  date: string
  /** Running local total; grows the instant active time accrues, online or
   * off. Never decreases. */
  seconds: number
  /** How much of `seconds` the server has acknowledged. */
  syncedSeconds: number
  /** The in-flight or queued-for-retry flush attempt, if any; `null` when
   * every accrued second has been acknowledged. */
  pending: PendingReadingTimeFlush | null
}

/** One badge this device has already shown an unlock toast for (W3.2). */
export interface BadgeSeenEntry {
  profileId: string
  badgeId: string
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
  reading_time_days: { key: string; value: ReadingTimeDayBucket }
  badge_seen: { key: string; value: BadgeSeenEntry }
}

const DB_NAME = 'cyo-reader'
const DB_VERSION = 5
/** Singleton key: one device grant per device. */
const DEVICE_GRANT_KEY = 'current'

/**
 * The `storybooks` store key for one exact payload.
 *
 * Exported because offline/revocation.ts's content-staleness check keys its
 * own bookkeeping by the same identity; a second, hand-rolled copy of this
 * template there would silently stop matching the day the format changed.
 */
export function storybookCacheKey(id: string, version: number): string {
  return `${id}@${version}`
}

function storyKey(id: string, version: number): string {
  return storybookCacheKey(id, version)
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
    // #CRITICAL: data-integrity: idb's upgrade callback receives the OLD
    // version (0 for a brand-new database), and each `if` runs the schema
    // change for every version the open needed to pass through, so a
    // brand-new database (oldVersion 0) creates all stores in one pass, an
    // existing v1 database (oldVersion 1) gains `device_grant`, `library_lists`,
    // and `profile_shelf`, an existing v2 database (oldVersion 2) gains
    // `library_lists` and `profile_shelf`, an existing v3 database
    // (oldVersion 3) gains `personalization_values`, and an existing v4
    // database (oldVersion 4) gains `reading_time_days` and `badge_seen`
    // (W3.3/W3.2). Every branch MUST stay additive (create, never drop, a
    // store) and every earlier branch MUST stay exactly as it ran for a real
    // upgraded user's database: reordering or collapsing an old `if` would
    // silently change what an existing v1-v4 database receives on its next
    // open, which idb has no way to detect or warn about.
    // #VERIFY: db.test.ts "creates the device_grant store on a fresh
    // database", the v1-to-v3 and v2-to-v3 migration tests, "creates the
    // store when upgrading a v3 database to v4", "keeps the pre-existing
    // stores reachable across the v4 upgrade", offline/db.test.ts's
    // existing stores stay reachable across every migration path, and the
    // new v4-to-v5 migration test asserting `reading_time_days`/`badge_seen`
    // appear without disturbing any earlier store.
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
      if (oldVersion < 5) {
        db.createObjectStore('reading_time_days')
        db.createObjectStore('badge_seen')
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

/**
 * Cache a downloaded story blob for offline play.
 *
 * W4.3 (D20): gated by the offline download budget (`downloadBudget.ts`)
 * before the write. A refusal is silent from THIS function's own contract
 * (it still resolves, never rejects, for a budget refusal specifically) so
 * the existing caller (`ReaderPage.tsx::load()`) keeps working unedited: it
 * already treats a caching failure as best-effort ("the story is already in
 * hand from the network, so a failure to cache it locally must not block
 * reading it now"), and a budget refusal is exactly that same shape -- the
 * story is still readable this session, it just will not be available
 * offline. `recordDownloadRefusal` leaves a flag `LibraryPage.tsx` surfaces
 * as a kid-facing banner the next time this profile's shelf loads, since
 * `ReaderPage.tsx` is out of scope for this change and cannot be edited to
 * show it directly.
 *
 * #ASSUME timing/external-resources: the budget CHECK fails open (proceeds
 * to cache) on any unexpected error, so a diagnostic feature never costs
 * offline reading. Three outcomes around it are deliberately NOT fail-open,
 * because each is an enforcement step rather than a diagnostic: a refusal
 * past the hard cap, a required eviction that did not happen, and the cache
 * write itself failing. Every one of the three records a refusal so the
 * kid-facing banner fires, and every one logs.
 * #VERIFY: db.test.ts budget cases.
 */
export interface CacheStorybookOptions {
  /**
   * Reports a space-pressure eviction (G15 storage/download view) once the
   * evicted book's local delete has actually resolved without throwing.
   * Optional, fire-and-forget dependency injection, mirroring
   * reconcileOfflineCache's own `reportRemoval` option (offline/revocation.ts):
   * this module holds no axios/network import, so the real HTTP call is built
   * by the caller (ReaderRoute.tsx's `reportRemoval`, threaded through
   * ReaderPage's own `reportRemoval` prop) and handed in here as a plain
   * callback.
   *
   * #ASSUME: data-integrity: invoked only from the SAME branch that already
   * decides `recordDownloadEviction` fires, i.e. strictly after the evicted
   * book's delete resolved. Reporting a removal that did not happen would
   * make the guardian's Downloads view wrong in the opposite direction from
   * the gap this closes: it would show a book as gone from a device that
   * still has it.
   * #VERIFY: db.test.ts "reports a space-pressure eviction exactly once with
   * the evicted story id" and "does not report when the eviction delete fails".
   */
  reportEviction?: (evictedStorybookId: string) => void
}

export async function cacheStorybook(
  story: Storybook,
  options: CacheStorybookOptions = {}
): Promise<void> {
  const db = await getDb()
  let decision: BudgetGateResult
  try {
    const newBytes = estimateByteSize(story)
    const cachedIds = await listCachedStorybookIds()
    decision = await checkDownloadBudget(story.id, newBytes, cachedIds)
  } catch (error) {
    // The DIAGNOSTIC failing open is deliberate (see the doc block above);
    // failing open silently is not. Previously this catch also covered the
    // eviction below, so a failed delete was indistinguishable from a failed
    // estimate and both proceeded to write.
    console.error('[offline] download budget check failed', { storyId: story.id, error })
    decision = { allowed: true }
  }
  if (!decision.allowed) {
    recordDownloadRefusal()
    return
  }
  if (decision.evictStoryId !== undefined) {
    try {
      await deleteStorybooksById(decision.evictStoryId)
      recordDownloadEviction()
      // #EDGE: external-resources: options.reportEviction is caller-supplied
      // and this module has no network import to trust its contract from the
      // outside (ReaderRoute.tsx's own wrapper already guards a synchronous
      // throw at its call site, matching reportDownload's pattern), so this
      // guards it again here, inside the SAME try this eviction ran in: a
      // reporter that throws must not fall into the catch below and be
      // mistaken for the eviction itself failing (which would wrongly call
      // recordDownloadRefusal on a successful eviction).
      // #VERIFY: db.test.ts "a synchronously-throwing reporter does not
      // break a REQUIRED eviction".
      if (options.reportEviction) {
        try {
          options.reportEviction(decision.evictStoryId)
        } catch (error) {
          console.error('[offline] eviction report threw synchronously', {
            evictStoryId: decision.evictStoryId,
            error,
          })
        }
      }
    } catch (error) {
      console.error('[offline] eviction failed', {
        storyId: story.id,
        evictStoryId: decision.evictStoryId,
        required: decision.evictionRequired === true,
        error,
      })
      if (decision.evictionRequired === true) {
        // Past the hard cap with no room freed: writing anyway is what the
        // budget exists to prevent.
        recordDownloadRefusal()
        return
      }
    }
  }
  try {
    await db.put('storybooks', story, storyKey(story.id, story.version))
  } catch (error) {
    // #CRITICAL: external-resources: the genuine `QuotaExceededError` path.
    // The budget check is an estimate against a fixed cap and can pass while
    // the device itself is out of space; this write is where that shows up.
    // It previously escaped past the try entirely, into ReaderPage's
    // best-effort `catch {}`, producing neither the book offline nor the
    // "bookshelf is full" banner nor a log line. Records the refusal so the
    // kid-facing surface says something, then rethrows so the caller's own
    // handling is unchanged.
    // #VERIFY: db.test.ts "records a refusal and rethrows when the cache
    // write itself fails".
    console.error('[offline] storybook cache write failed', { storyId: story.id, error })
    recordDownloadRefusal()
    throw error
  }
  recordStoryOpened(story.id)
}

/**
 * Read a cached story blob, or undefined if it is not downloaded.
 *
 * W4.3: every successful read also refreshes that story's recency (not just
 * every download), so the offline budget's eviction order reflects actual
 * last-OPENED, not just last-downloaded (see `downloadBudget.ts`).
 */
export async function getCachedStorybook(
  id: string,
  version: number
): Promise<Storybook | undefined> {
  const db = await getDb()
  const story = await db.get('storybooks', storyKey(id, version))
  if (story) recordStoryOpened(id)
  return story
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

// Session-monotonic counter stamped onto every queued write, so writes made in
// the same millisecond keep their insertion order. Resets on reload, which is
// harmless: queued_at dominates the sort across sessions (a reload takes far
// longer than a millisecond), and seq only ever breaks a within-session tie.
let queueSeq = 0

/** Queue a reading-state write. Stamps the insertion-order tie-break. */
export async function enqueueWrite(item: QueuedWrite): Promise<void> {
  const db = await getDb()
  queueSeq += 1
  await db.put('offline_queue', { ...item, seq: item.seq ?? queueSeq })
}

/** List queued writes in insertion order (oldest first). */
export async function listQueue(): Promise<QueuedWrite[]> {
  const db = await getDb()
  const items = await db.getAll('offline_queue')
  return items.sort((a, b) => a.queued_at - b.queued_at || (a.seq ?? 0) - (b.seq ?? 0))
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

/**
 * Remove every cached version of a storybook (offline-copy revocation, and
 * W4.3's own budget-driven eviction). Also drops the story's offline-budget
 * recency entry (`downloadBudget.ts`) so a later re-download starts clean
 * rather than inheriting a stale eviction-time timestamp.
 */
export async function deleteStorybooksById(id: string): Promise<void> {
  const db = await getDb()
  const keys = await db.getAllKeys('storybooks')
  const prefix = `${id}@`
  for (const key of keys) {
    if (key.startsWith(prefix)) {
      await db.delete('storybooks', key)
    }
  }
  forgetStoryRecency(id)
}

/**
 * Remove exactly one cached `(id, version)` entry, leaving any other cached
 * version of the same book alone.
 *
 * The narrow counterpart to {@link deleteStorybooksById}, for the content-
 * staleness eviction in offline/revocation.ts. Two differences matter and
 * neither is cosmetic:
 *
 * - Scope: staleness is a property of one exact payload, so a device holding
 *   two versions of a book must not lose the one that is still current.
 * - Recency: this deliberately does NOT call `forgetStoryRecency`.
 *   `deleteStorybooksById` forgets it because that book is genuinely leaving
 *   the device (revoked, or evicted for space). A stale blob is about to be
 *   re-downloaded by the very reader who has been opening it, so discarding
 *   its recency would make an actively-read book the first candidate the
 *   budget evicts (`downloadBudget.ts::pickEvictionCandidate` sorts an
 *   unknown recency as oldest-possible).
 */
export async function deleteCachedStorybookVersion(id: string, version: number): Promise<void> {
  const db = await getDb()
  await db.delete('storybooks', storyKey(id, version))
}

/**
 * Every `id@version` key currently cached on this device.
 *
 * The version-preserving counterpart to {@link listCachedStorybookIds}, for
 * the content-staleness check, which has to tell "this exact payload is
 * cached" from "some version of this book is cached".
 */
export async function listCachedStorybookKeys(): Promise<string[]> {
  const db = await getDb()
  return [...(await db.getAllKeys('storybooks'))]
}

/** Distinct storybook ids currently cached on this device, across every version. */
export async function listCachedStorybookIds(): Promise<string[]> {
  const keys = await listCachedStorybookKeys()
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

function readingTimeKey(profileId: string, date: string): string {
  return `${profileId}:${date}`
}

/** Read one profile's reading-time bucket for a reader-local date, or undefined. */
export async function getReadingTimeBucket(
  profileId: string,
  date: string
): Promise<ReadingTimeDayBucket | undefined> {
  const db = await getDb()
  return db.get('reading_time_days', readingTimeKey(profileId, date))
}

/** Persist a reading-time bucket (overwrites the previous value wholesale). */
export async function putReadingTimeBucket(bucket: ReadingTimeDayBucket): Promise<void> {
  const db = await getDb()
  await db.put('reading_time_days', bucket, readingTimeKey(bucket.profileId, bucket.date))
}

/** Every reading-time bucket stored for a profile, in no particular order. */
export async function listReadingTimeBuckets(profileId: string): Promise<ReadingTimeDayBucket[]> {
  const db = await getDb()
  const keys = await db.getAllKeys('reading_time_days')
  const prefix = `${profileId}:`
  const buckets: ReadingTimeDayBucket[] = []
  for (const key of keys) {
    if (!key.startsWith(prefix)) continue
    const bucket = await db.get('reading_time_days', key)
    if (bucket !== undefined) buckets.push(bucket)
  }
  return buckets
}

function badgeSeenKey(profileId: string, badgeId: string): string {
  return `${profileId}:${badgeId}`
}

/** Whether this device has already shown an unlock toast for this badge (W3.2). */
export async function isBadgeSeen(profileId: string, badgeId: string): Promise<boolean> {
  const db = await getDb()
  const row = await db.get('badge_seen', badgeSeenKey(profileId, badgeId))
  return row !== undefined
}

/** Record that this device has now shown the unlock toast for this badge. */
export async function markBadgeSeen(profileId: string, badgeId: string): Promise<void> {
  const db = await getDb()
  await db.put('badge_seen', { profileId, badgeId }, badgeSeenKey(profileId, badgeId))
}

/** Reset the cached database handle (test isolation helper). */
export function _resetDbHandle(): void {
  _db = null
}
