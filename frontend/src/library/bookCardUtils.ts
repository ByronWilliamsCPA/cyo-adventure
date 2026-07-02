import type { LibraryItemView } from './libraryApi'

/** Percent of nodes visited, clamped: a state pinned to an older version can
 * exceed the current version's node count after a republish. */
export function percentComplete(item: LibraryItemView): number {
  if (!item.progress || item.node_count <= 0) return 0
  return Math.min(100, Math.round((100 * item.progress.nodes_visited) / item.node_count))
}
