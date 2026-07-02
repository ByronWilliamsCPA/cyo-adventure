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
