/**
 * How a book is entered: what the reader knows about the shelf copy the child
 * tapped (cover, current rating), how to save a rating, and whether this open
 * deserves a title page.
 *
 * Supplied by ReaderRoute through `ReaderEntryContext` rather than as Reader
 * props so ReaderPage, which sits between the two and is otherwise untouched by
 * this, does not have to forward three more values. A Reader rendered with no
 * provider (unit tests, any future embedded reader) gets the default: no title
 * page, no shelf data, no rating; i.e. exactly the pre-title-page reader.
 */

import { createContext, useContext } from 'react'

import { flowedPrefix } from '../player/stops'
import type { ReadingState, Storybook } from '../player/types'

/** The shelf's view of one book, as the library last saw it. */
export interface ShelfEntry {
  /**
   * Presigned cover URL, or null for a book with no cover.
   * #ASSUME: external-resources: presigned URLs expire and need the network;
   * every consumer must fall back to the letter tile on a load error.
   * #VERIFY: BookCover.test.tsx "falls back to the letter tile when the
   * cover fails to load".
   */
  coverUrl: string | null
  /** The child's current 1-5 rating, or null when unrated. */
  rating: number | null
}

export interface ReaderEntry {
  /** Whether a fresh open shows the title page (the routed reader only). */
  titlePage: boolean
  /** Shelf data for this book, or null when unknown. */
  entry: ShelfEntry | null
  /**
   * Saves a rating and resolves to the saved value (the same POST /v1/ratings
   * the library card uses). Omitted means no rating UI.
   */
  rate?: (storybookId: string, value: number) => Promise<number>
}

export const NO_READER_ENTRY: ReaderEntry = { titlePage: false, entry: null }

export const ReaderEntryContext = createContext<ReaderEntry>(NO_READER_ENTRY)

export function useReaderEntry(): ReaderEntry {
  return useContext(ReaderEntryContext)
}

/**
 * The `shelf` key BookCard puts on its router location state, or null when
 * absent or malformed (a deep link, a reload, ContinueSeries' own navigation).
 * #ASSUME: data-integrity: location.state is untyped and survives reloads in
 * the browser's history entry, so every field is type-checked here.
 * #VERIFY: readerEntry.test.ts "rejects a malformed shelf state".
 */
export function parseShelfState(state: unknown): ShelfEntry | null {
  if (typeof state !== 'object' || state === null) return null
  const shelf = (state as { shelf?: unknown }).shelf
  if (typeof shelf !== 'object' || shelf === null) return null
  const { coverUrl, rating } = shelf as { coverUrl?: unknown; rating?: unknown }
  // #ASSUME: security: location.state is writable by any script on this
  // origin through the History API, so it is untrusted. Only an absolute
  // http(s) URL is accepted as an image source; anything else (a data: or
  // javascript: URL, a relative path) degrades to the letter tile.
  // #VERIFY: readerEntry.test.ts "rejects a non-http cover URL".
  const cover = typeof coverUrl === 'string' && /^https?:\/\//i.test(coverUrl) ? coverUrl : null
  const stars =
    typeof rating === 'number' && Number.isInteger(rating) && rating >= 1 && rating <= 5
      ? rating
      : null
  return { coverUrl: cover, rating: stars }
}

/**
 * Whether `initial` is the very start of a read, so the reader may show the
 * title page before it: no saved state at all, or a saved state that has not
 * yet left its opening stop. A child returning mid-book (any real tap made)
 * lands straight on their page with no extra tap.
 *
 * At flowed bands (ADR-026) the persisted state of an untouched book can sit
 * at the TERMINAL of the opening stop, because useFlowedStop walks the
 * machine through that stop's single-choice hops on mount and the result is
 * saved. Those hops were never tapped, so a path made only of the opening
 * stop's flowed prefix still counts as the opening.
 */
export function isOpeningRead(
  story: Storybook,
  initial: ReadingState | undefined,
  flowed: boolean
): boolean {
  if (initial === undefined) return true
  if (initial.path.length <= 1) return true
  if (!flowed) return false
  return initial.path.length === flowedPrefix(story, initial).length + 1
}
