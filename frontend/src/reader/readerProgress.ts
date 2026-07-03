import type { ReadingState, Storybook } from '../player/types'

/**
 * Percent of the story's nodes the reader has visited, clamped to 0-100. Mirrors
 * the library's percentComplete but reads from the in-session reading state.
 */
export function readerProgressPercent(story: Storybook, reading: ReadingState): number {
  const total = story.nodes.length
  if (total <= 0) return 0
  return Math.min(100, Math.round((100 * reading.visit_set.length) / total))
}

/** "X of Y pages explored", matching the library's BookCard label wording. */
export function readerProgressLabel(story: Storybook, reading: ReadingState): string {
  return `${reading.visit_set.length} of ${story.nodes.length} pages explored`
}
