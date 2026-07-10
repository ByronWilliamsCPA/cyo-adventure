/**
 * Series-chaining helpers (WS-G): parse the embedded series block from a
 * story's loose metadata and define the reader-side continuation contract.
 * Kinds mirror the backend validator's _SATISFYING_KINDS (validator/series.py).
 */

import type { Storybook, VarState } from './types'

export interface SeriesMeta {
  seriesId: string
  bookIndex: number
  entryNode: string | null
  isFinal: boolean
  carriesState: boolean
}

/** Ending kinds that may offer "Continue the series" (spec section 1). */
export const SATISFYING_ENDING_KINDS: ReadonlySet<string> = new Set(['success', 'completion'])

/** Parse the embedded series block from story metadata, or null when absent/malformed. */
export function seriesMeta(story: Storybook): SeriesMeta | null {
  const block = (story.metadata as { series?: unknown }).series
  if (typeof block !== 'object' || block === null) return null
  const b = block as Record<string, unknown>
  if (typeof b.series_id !== 'string' || typeof b.book_index !== 'number') return null
  return {
    seriesId: b.series_id,
    bookIndex: b.book_index,
    entryNode: typeof b.series_entry_node === 'string' ? b.series_entry_node : null,
    isFinal: b.is_final === true,
    carriesState: b.carries_state === true,
  }
}

/** What a continuation navigation carries to the next book's reader. */
export interface ContinuationSeed {
  entryNode: string | null
  varState?: VarState
}

/**
 * Parse a router location.state into a ContinuationSeed, defensively: state
 * is attacker-shapeable via history manipulation, so every field is checked.
 * Carried var values are re-filtered by startContinuation (type and bounds),
 * so a forged varState can never seed an invalid value.
 */
export function parseContinuation(state: unknown): ContinuationSeed | undefined {
  if (typeof state !== 'object' || state === null) return undefined
  const c = (state as { continuation?: unknown }).continuation
  if (typeof c !== 'object' || c === null) return undefined
  const cc = c as Record<string, unknown>
  return {
    entryNode: typeof cc.entryNode === 'string' ? cc.entryNode : null,
    varState:
      typeof cc.varState === 'object' && cc.varState !== null
        ? (cc.varState as VarState)
        : undefined,
  }
}
