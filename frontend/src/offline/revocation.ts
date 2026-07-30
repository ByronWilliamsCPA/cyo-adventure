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
  deletePersonalizationValues,
  deleteReadingState,
  deleteStorybooksById,
  dequeue,
  getAllProfileShelves,
  listCachedStorybookIds,
  listPersonalizationValues,
  listQueue,
  listReadingStateStorybookIds,
  putProfileShelf,
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
export async function reconcileOfflineCache(
  profileId: string,
  authoritativeIds: readonly string[]
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
    }
  }
}

/**
 * Forget every cached values payload naming one subject profile (ADR-023 P6).
 *
 * Deliberately NOT part of `reconcileOfflineCache`. That function's #CRITICAL
 * contract is that it runs only after a successful authoritative library fetch,
 * because it cannot distinguish "zero books" from "the fetch failed". A values
 * purge has looser preconditions (a sign-out, a guardian toggling a ring off, a
 * consent revocation), and folding it in would either weaken that contract or
 * make the purge unreachable from the paths that need it.
 *
 * #ASSUME: security: purging is best-effort and PROSPECTIVE. A device that is
 * offline when a guardian revokes keeps its payload until it next opens the app
 * and completes a fetch, exactly like the mid-read book-revocation gap this
 * module already documents at the top of the file. Guardian-facing copy must
 * therefore say "new readings" and must never imply retroactive erasure.
 * #VERIFY: revocation.test.ts covers the online purge; the offline residue
 * window is documented, not closed, and the R20 acceptance in
 * docs/planning/privacy-model.md is where it is formally accepted.
 */
export async function purgePersonalizationValues(subjectProfileId: string): Promise<void> {
  const entries = await listPersonalizationValues()
  for (const entry of entries) {
    if (entry.payload.subject_profile_id === subjectProfileId) {
      await deletePersonalizationValues(entry.storybook_id)
    }
  }
}

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
  // #CRITICAL: security: null means "no authoritative answer", and this function
  // treats it as revocation (delete) rather than as "keep what we have". That is
  // the opposite of reconcileOfflineCache's fail-safe direction, and deliberately
  // so: keeping a stale personalization payload risks rendering a child's name
  // after consent was withdrawn, while deleting it costs only a fall back to the
  // generic story on the next render. The asymmetry is the point.
  // #VERIFY: revocation.test.ts "deletes rather than caches when the fetch
  // produced null".
  if (fresh === null || Object.keys(fresh.values).length === 0) {
    await deletePersonalizationValues(storybookId)
    return
  }
  await cachePersonalizationValues(storybookId, fresh)
}
