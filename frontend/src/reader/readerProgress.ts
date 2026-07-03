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

/** "X of Y pages explored", matching the library's BookCard label wording. Clamps
 * the visited count like readerProgressPercent so a resumed/replayed state with
 * a stale visit_set can't render "20 of 10 pages explored". */
export function readerProgressLabel(story: Storybook, reading: ReadingState): string {
  const total = story.nodes.length
  const visited = Math.min(reading.visit_set.length, total)
  return `${visited} of ${total} pages explored`
}
