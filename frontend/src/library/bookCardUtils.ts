import type { LibraryItemView } from './libraryApi'

// #ASSUME: data integrity: progress may be pinned to an older story version,
// so nodes_visited can exceed the current node_count after a republish.
// #VERIFY: clamp at 100 and guard node_count <= 0; unit tests cover both.
/** Percent of nodes visited, clamped: a state pinned to an older version can
 * exceed the current version's node count after a republish. */
export function percentComplete(item: LibraryItemView): number {
  if (!item.progress || item.node_count <= 0) return 0
  return Math.min(100, Math.round((100 * item.progress.nodes_visited) / item.node_count))
}

/** K9 shelf presentation, "what's new" leg: how long a book keeps its "New"
 * badge on the shelf after publishing. */
export const NEW_BADGE_WINDOW_MS = 7 * 24 * 60 * 60 * 1000

// #ASSUME: data integrity: published_at is optional/nullable (an offline-
// cached item saved before this field existed, or a pre-migration backend
// row, both omit it) and, once parsed, may not be a valid date.
// #VERIFY: both cases degrade to "not new" rather than throwing or showing a
// false badge; unit tests cover the missing, malformed, and future-dated cases.
/** Whether `item` was published recently enough to show the "New" badge. */
export function isRecentlyPublished(item: LibraryItemView, now: Date = new Date()): boolean {
  if (!item.published_at) return false
  const publishedMs = Date.parse(item.published_at)
  if (Number.isNaN(publishedMs)) return false
  const ageMs = now.getTime() - publishedMs
  // #EDGE: timing dependencies: a clock skew or malformed future timestamp
  // could put publishedMs after `now`; treat that as not-new rather than a
  // negative age accidentally satisfying `<= window`.
  return ageMs >= 0 && ageMs <= NEW_BADGE_WINDOW_MS
}
