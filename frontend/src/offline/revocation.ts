/**
 * Offline-copy revocation (roadmap Phase 5, register G8/A5): when a book is
 * unassigned, archived, unpublished, or pulled for a moderation incident, the
 * child's device must stop being able to read it offline the next time it
 * connects. This completes the guardian kill switch and the incident
 * pull-everywhere path.
 *
 * `/v1/library` already returns the authoritative, per-profile set of
 * assigned+published books (LibraryPage.tsx: "The server already filters to
 * published, approved, family-scoped books"), so this is pure client-side
 * reconciliation against that response. No backend change is needed: a book
 * leaves the shelf response the moment it is unassigned, archived, or
 * unpublished, and the next successful fetch is exactly the "next
 * connection" the requirement asks for.
 *
 * One gap the shelf list cannot express: a book that is still assigned to a
 * profile but becomes unpublished (or is pulled) *mid-read*, before that
 * profile's next library fetch. The kid stays on the reader route with an
 * already-downloaded cache entry and no trigger to re-check the shelf until
 * they navigate back to the library (or the app reloads and re-renders it).
 * This is a real, if narrow, window; closing it would need either a
 * revocation push channel or the reader route re-validating against the
 * shelf mid-session, both backend/routing changes out of scope here. It is
 * documented, not silently accepted, rather than papered over with an
 * invented backend change.
 */

import type { ValuesPayload } from '../player/personalization'
import {
  cachePersonalizationValues,
  deleteCachedStorybookVersion,
  deletePersonalizationValues,
  deleteReadingState,
  deleteStorybooksById,
  dequeue,
  getAllProfileShelves,
  listCachedStorybookIds,
  listCachedStorybookKeys,
  listPersonalizationValues,
  listQueue,
  listReadingStateStorybookIds,
  putProfileShelf,
  storybookCacheKey,
} from './db'

// #CRITICAL: data-integrity: this function purges local cache state and must
// ONLY ever be invoked with the result of a successful, authoritative fetch
// of a profile's library list. It has no way to tell "this profile genuinely
// has zero books right now" apart from "the fetch failed and there is no
// list at all"; that distinction lives entirely at the call site.
// reconcileOfflineCache must never run from a catch/error branch, a timeout,
// or a stale/cached response, only after a resolved libraryApi.list() call.
// A caller that reconciles on a failed fetch would wipe every offline book on
// a transient network blip, which is worse than the staleness this feature
// is closing.
// #VERIFY: revocation.test.ts "does not purge anything when the fetch
// fails" (the caller never calls reconcileOfflineCache in that path); the
// LibraryPage.tsx call site only calls it inside fetchItems's success block,
// never inside its catch.

/**
 * Reconcile this device's offline cache against a profile's fresh,
 * authoritative shelf (the ids returned by the current `/v1/library` fetch).
 *
 * Two different safety scopes are in play:
 *
 * - `reading_states` and the `offline_queue` are keyed per profile
 *   (`profile_id:storybook_id` / a `profile_id` field), so any entry for
 *   THIS profile whose storybook is no longer on its fresh shelf is always
 *   safe to delete outright: no other profile can be affected.
 * - `storybooks` (the downloaded story content itself) is a device-wide
 *   cache keyed only by `id@version` (db.ts), because a sibling profile on
 *   the same device can legitimately have the same book assigned. Deleting
 *   it is only safe once NO profile this device knows about still lists the
 *   book, tracked via the `profile_shelf` snapshot this function maintains
 *   on every call.
 *
 * #ASSUME: concurrency: queued offline-sync writes (`offline_queue`) for a
 * revoked book are dropped outright here, never flushed to the server first.
 * Revocation means the server has already removed this profile's access
 * (unassigned, archived, unpublished, or pulled for an incident), so a
 * pending PUT for that story would almost certainly 403/404 against the
 * server's now-canonical state; replayQueue already drops a non-offline
 * failure the same way (offline/sync.ts), and there is no reader UI left for
 * this profile to act on the result even if the write somehow succeeded.
 * Flushing first would add a network round-trip, on a path that runs after
 * every library fetch and must stay simple and purely local, for a write
 * whose destination the profile can no longer reach anyway.
 * #VERIFY: revocation.test.ts "drops queued writes for a revoked book
 * without calling the sync API".
 */
export interface ReconcileOfflineCacheOptions {
  /**
   * Reports the shared-content purge of a book (G15 storage/download view)
   * once each entry's local delete has actually resolved, one call per
   * removed book id. Optional, fire-and-forget dependency injection,
   * mirroring cacheStorybook's own `reportEviction` option (offline/db.ts):
   * this module holds no axios/network import, so the real HTTP call is
   * built by the caller (LibraryPage.tsx) and handed in here as a plain
   * callback.
   */
  reportRemoval?: (removedStorybookId: string) => void
}

export async function reconcileOfflineCache(
  profileId: string,
  authoritativeIds: readonly string[],
  options: ReconcileOfflineCacheOptions = {}
): Promise<void> {
  const freshIds = [...authoritativeIds]
  const freshSet = new Set(freshIds)

  // Profile-scoped cleanup: always safe regardless of any sibling profile.
  const cachedStateIds = await listReadingStateStorybookIds(profileId)
  for (const storybookId of cachedStateIds) {
    if (!freshSet.has(storybookId)) {
      await deleteReadingState(profileId, storybookId)
    }
  }
  const queue = await listQueue()
  for (const item of queue) {
    if (item.profile_id === profileId && !freshSet.has(item.storybook_id)) {
      await dequeue(item.event_id)
    }
  }

  // Record this profile's fresh shelf, then union every known profile's
  // shelf on this device so a sibling's still-assigned book is never
  // stripped out from under them.
  await putProfileShelf(profileId, freshIds)
  const allShelves = await getAllProfileShelves()
  const stillNeeded = new Set<string>()
  for (const shelf of allShelves) {
    for (const id of shelf.storybook_ids) stillNeeded.add(id)
  }

  // Shared storybook content: delete only when no known profile needs it.
  const cachedStoryIds = await listCachedStorybookIds()
  for (const id of cachedStoryIds) {
    if (!stillNeeded.has(id)) {
      await deleteStorybooksById(id)
      // #ASSUME: data-integrity: reported only after the delete above has
      // resolved without throwing; a throw there propagates out of this
      // function before this line is ever reached, so a failed delete is
      // never reported as a removal. Reporting a removal that did not happen
      // would make the guardian's Downloads view wrong in the opposite
      // direction from the gap this closes.
      // #VERIFY: revocation.test.ts "reports each removed book after a
      // successful shared-content purge".
      if (options.reportRemoval) {
        // #EDGE: external-resources: guard a synchronous throw from a
        // caller-supplied reporter, the same defense db.ts's cacheStorybook
        // applies around its own reportEviction call: a throw here must not
        // abort the remaining loop iterations or the profile-scoped cleanup
        // that already ran above.
        // #VERIFY: revocation.test.ts "a synchronously-throwing reporter
        // does not break the purge loop".
        try {
          options.reportRemoval(id)
        } catch (error) {
          console.error('[offline] revocation report threw synchronously', {
            storybookId: id,
            error,
          })
        }
      }
    }
  }

  // Personalization values ride the same device-wide still-needed set (ADR-023
  // P6): the store is keyed by book, not profile, exactly like `storybooks`.
  // Once no known profile lists a book, its cached values payload (a child's
  // real first name at rest) has no remaining reader, and no other purge path
  // will ever reach it: the per-book reconcile in ReaderRoute only fires when
  // THAT book is opened again, which a revoked book never is. Deleting here is
  // what keeps a revocation from stranding an unreachable values entry forever.
  const valuesEntries = await listPersonalizationValues()
  for (const entry of valuesEntries) {
    if (!stillNeeded.has(entry.storybook_id)) {
      await deletePersonalizationValues(entry.storybook_id)
    }
  }
}

// There is deliberately no subject-scoped values purge here. Every one of the
// spec's purge triggers (Task C2c) already routes through a mechanism that
// exists: sign-out clears the whole store at once (db.ts
// clearPersonalizationValues, called from AuthContext's
// purgeAuthenticatedDataAtRest); a consent or ring change surfaces as an empty
// payload on the next open of each book, which the per-book
// reconcilePersonalizationValues below turns into a delete; and revocation of
// the book itself is covered by reconcileOfflineCache's values deletion above.
// A subject-keyed purgePersonalizationValues existed briefly but had zero
// production call sites and was removed rather than left as an untriggered
// privacy affordance.

/**
 * Reconcile one book's cached values payload against a fresh, authoritative one.
 *
 * The single client-side mechanism behind six of the spec's seven purge triggers
 * (a ring flag switched off, ring-2 consent revoked, the connection revoked, the
 * subject deactivated, the subject's processing restricted, the consent policy
 * version rotated). Every one of them makes the server return a payload that
 * differs from the cached one, usually the empty payload, because the values
 * route re-evaluates the whole predicate on each call. The client does not need
 * to know WHICH of them happened, and deliberately is not told: distinguishing
 * them is exactly what the route's uniform empty payload refuses to leak.
 *
 * @param storybookId - The book whose cache entry this is.
 * @param fresh - The payload the authoritative fetch returned, or null when the
 *   fetch failed or was not attempted.
 */
export async function reconcilePersonalizationValues(
  storybookId: string,
  fresh: ValuesPayload | null
): Promise<void> {
  // #CRITICAL: security: the null branch deletes, but know who actually uses
  // it. It exists for a caller that treats null as an authoritative "no
  // payload" and wants the fail-safe delete. The only production caller today
  // (ReaderRoute.tsx's fetcher) deliberately never passes null: the api
  // adapter (api/personalizationApi.ts) collapses EVERY failure (401, 403,
  // 500, transport) to null, so treating null as revocation there would purge
  // the cache on any server blip. The operative consequence: on a server
  // error a cached payload persists until a successful fetch answers, and
  // only that answer (an empty or changed payload) revokes it.
  // #VERIFY: revocation.test.ts "deletes rather than caches when the fetch
  // produced null" covers this branch; ReaderRoute.tsx's fetcher returns the
  // cache untouched on a null fetch instead of calling this with null.
  if (fresh === null || Object.keys(fresh.values).length === 0) {
    await deletePersonalizationValues(storybookId)
    return
  }
  await cachePersonalizationValues(storybookId, fresh)
}

/**
 * Where this device records, per `id@version`, the content identity the
 * server most recently advertised for that payload.
 *
 * `localStorage`, deliberately, not a new IndexedDB store: this is derived
 * bookkeeping that is cheap to rebuild from scratch, and keeping it out of
 * `db.ts` means the whole feature needs no `DB_VERSION` bump, no upgrade
 * branch, and no downgrade story for a client running an older bundle. It is
 * the same call `downloadBudget.ts` already makes for recency and the refusal
 * flag ("this module carries no schema/version surface at all"). If the map
 * is lost (private mode, a user clearing site data, a browser that throws on
 * access), every cached entry simply reads as unverified again and is
 * re-verified once; the failure mode is one extra re-download, never a wrong
 * answer.
 */
const CONTENT_HASH_KEY = 'offline_story_content_hash'

type ContentHashMap = Record<string, string>

function readContentHashes(): ContentHashMap {
  try {
    const raw = localStorage.getItem(CONTENT_HASH_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    return parsed as ContentHashMap
  } catch {
    // #EDGE: browser-compat: storage unavailable or a corrupt blob. Treated as
    // "nothing verified yet", which costs one re-verification pass and never
    // asserts a match this device cannot actually vouch for.
    return {}
  }
}

function writeContentHashes(map: ContentHashMap): void {
  try {
    localStorage.setItem(CONTENT_HASH_KEY, JSON.stringify(map))
  } catch {
    // #EDGE: browser-compat: storage unavailable. The eviction that already
    // happened still stands; only the memo of it is lost, so the next shelf
    // load re-verifies. Degrades toward extra work, never toward staleness.
  }
}

/** One shelf entry, as much of a `LibraryItemView` as the staleness check reads. */
export interface StaleCheckItem {
  id: string
  version: number
  /** The server's content identity for this exact payload (`LibraryItem.content_hash`). */
  content_hash?: string
}

/** What one staleness pass did, for logging and for tests. */
export interface StaleEvictionOutcome {
  /** Entries evicted because their stored identity differed from the server's. */
  changed: number
  /** Entries evicted because this device had never recorded an identity for them. */
  unverified: number
  /** Cached entries whose stored identity already matched; left untouched. */
  fresh: number
}

/**
 * Evict cached blobs whose CONTENT changed while their `version` did not.
 *
 * `storybook_version` is documented as immutable and the offline cache was
 * built on that promise: `storybooks` is keyed by `id@version` alone, and a
 * cache hit is never re-fetched. `scripts/retrofit_personalization.py` broke
 * the promise for 15 already-published production rows, rewriting `blob` in
 * place without bumping `version`, so every device that downloaded one of
 * those books beforehand keeps the pre-retrofit prose permanently: same id,
 * same version, cache hit, no personalization, forever, with nothing to
 * detect it. `LibraryItem.content_hash` (server side:
 * `api/library.py::storybook_content_hash`) is the missing signal, and this
 * is the client half.
 *
 * Three cases, and the third is the whole affected population:
 *
 * - stored identity === advertised identity: fresh. Nothing happens, which is
 *   what keeps this from re-downloading the shelf on every load.
 * - stored identity !== advertised identity: the payload changed underneath a
 *   frozen version. Evict just that `id@version`.
 * - no stored identity at all: UNKNOWN, not "matches". Every device that
 *   cached anything before this shipped is in this state, including every
 *   device holding one of the 15 retrofitted books. Verify it exactly once by
 *   evicting, then record the advertised identity so the re-download settles
 *   the question permanently. Recording is what makes it once rather than
 *   forever: without it the entry would read as unverified on every shelf
 *   load and re-download on every one of them.
 *
 * The advertised identity is recorded for every shelf item, cached or not, so
 * a book downloaded AFTER this pass is already accounted for and does not pay
 * a throwaway re-download the first time it appears here.
 *
 * Eviction only: nothing here downloads or rewrites a blob. The re-download is
 * `ReaderPage.tsx::load()`'s existing cache-miss path, unchanged and already
 * tested, so this adds no second download path to keep in sync.
 *
 * Scope note, and the reason this is NOT folded into `reconcileOfflineCache`:
 * that function's purge is gated on "no profile on this device still lists
 * this book". Staleness has no such gate and must not inherit one. A blob
 * whose bytes changed is stale for every profile on the device at once,
 * including profiles whose shelf is not the one being fetched, because
 * `storybooks` is a single device-wide store.
 *
 * #CRITICAL: data-integrity: like `reconcileOfflineCache` above, this deletes
 * local cache state and must ONLY run against a successful, authoritative
 * `/v1/library` response. It must never be called from a catch branch, a
 * timeout, or a cached/stale shelf: an item that reaches it with a missing or
 * empty `content_hash` is skipped entirely rather than evicted, so a partial
 * or older response can never be read as "everything changed" and wipe the
 * device's offline library on a bad payload.
 * #VERIFY: staleContent.test.ts "leaves a cached book alone when the server
 * advertised no content hash"; the LibraryPage.tsx call site sits in
 * fetchItems's success block beside reconcileOfflineCache, never in its catch.
 *
 * @param items - The freshly fetched, authoritative shelf for one profile.
 * @returns What the pass did, for the caller to log.
 */
export async function evictStaleOfflineBooks(
  items: readonly StaleCheckItem[]
): Promise<StaleEvictionOutcome> {
  const outcome: StaleEvictionOutcome = { changed: 0, unverified: 0, fresh: 0 }
  const known = readContentHashes()
  const cachedKeys = new Set(await listCachedStorybookKeys())
  const next: ContentHashMap = {}

  for (const item of items) {
    const advertised = item.content_hash
    // Absent or empty means the server told us nothing about this payload (a
    // pre-field backend, a hand-built item). Not evidence of change, so it is
    // not recorded and not acted on; the previous record, if any, is carried
    // forward below so an earlier verification is not thrown away.
    if (!advertised) continue
    const key = storybookCacheKey(item.id, item.version)
    next[key] = advertised
    if (!cachedKeys.has(key)) continue
    if (known[key] === advertised) {
      outcome.fresh += 1
      continue
    }
    await deleteCachedStorybookVersion(item.id, item.version)
    if (known[key] === undefined) outcome.unverified += 1
    else outcome.changed += 1
  }

  // Carry forward records for payloads this pass did not speak to but that are
  // still cached on the device: a sibling profile's book, or one this shelf
  // reported without a hash. Anything neither on this shelf nor still cached is
  // dropped, which is what keeps the map bounded by what the device actually
  // holds rather than by everything it has ever seen.
  for (const [key, hash] of Object.entries(known)) {
    if (next[key] === undefined && cachedKeys.has(key)) next[key] = hash
  }
  writeContentHashes(next)
  return outcome
}

/** Forget every recorded content identity (test isolation helper). */
export function _resetContentHashes(): void {
  try {
    localStorage.removeItem(CONTENT_HASH_KEY)
  } catch {
    // Nothing to clean up when storage is unavailable.
  }
}
