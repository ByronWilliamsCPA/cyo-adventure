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

import {
  deleteReadingState,
  deleteStorybooksById,
  dequeue,
  getAllProfileShelves,
  listCachedStorybookIds,
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
