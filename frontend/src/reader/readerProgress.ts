/**
 * Route-relative reading position (W1.2, AL-029).
 *
 * The reader used to show `visit_set.length / story.nodes.length`: corpus
 * coverage against every node in the graph, not progress along the path a
 * child actually took. On a large book (AL-029's book-3 example: 746 nodes)
 * a typical short read reported 1%, then snapped straight to 100% at the
 * ending screen; the numeric label was already suppressed as untrustworthy,
 * but the bar's fill and its aria-label kept making the same broken claim.
 *
 * This module replaces that with a plain position count: no denominator, no
 * percent, no fill claiming a "distance to the end" the graph cannot honestly
 * supply for the path a child chose (a story is a graph, not a line; how many
 * pages/stops remain depends on which branch is taken from here, and nothing
 * in the Storybook blob's metadata (`StoryMetadata` in
 * `storybook/models.py`, mirrored by `Storybook.metadata` here) exposes a
 * per-node "distance to nearest ending" or a "shortest path from here"
 * figure -- `estimated_minutes` is a whole-story fastest-finish clock, not a
 * per-position one, so scaling a bar toward it would recreate the exact
 * "fill toward a target the current path may never reach" dishonesty this
 * replaces). See ADR-026's "Implementation notes" and AL-029's row in
 * authoring-lessons-log.md for the fuller reasoning; ReaderChrome renders
 * this as a plain text pill rather than a percent-fill bar for exactly this
 * reason.
 */

import type { ReadingState, Storybook } from '../player/types'

/**
 * Bands where the reader flows consecutive single-choice, non-ending nodes
 * into one rendered "stop" (ADR-026 decisions 1 and 4). 3-5 and 5-8 keep
 * today's one-node-per-page rendering. This is the single canonical list;
 * Reader.tsx's stop composition and this module's position counting both
 * import it so the two can never drift apart on which bands are flowed.
 *
 * #ASSUME: data-integrity: the band string comes from the reading profile's
 * `age_band` field (ADR-026 decision 6), threaded in from ReaderRoute via a
 * best-effort `useKidProfile` lookup that resolves to `undefined` while the
 * lookup is in flight, has failed, or the caller has no profile to offer
 * (e.g. a bare `<Reader>` test with no `ageBand` prop). `isFlowedBand`
 * therefore always treats an unknown band as non-flowed (today's page
 * behavior), never as a guess; a wrong guess in either direction would be
 * worse than the safe default of "keep the behavior every existing reader
 * page already has".
 * #VERIFY: readerProgress.test.ts "treats an unrecognized or missing band as
 * non-flowed"; Reader.test.tsx's whole existing suite passes no `ageBand`
 * prop at all and must keep exercising the page-per-node path unchanged.
 */
const FLOWED_BANDS = new Set(['8-11', '10-13', '13-16', '16+'])

export function isFlowedBand(ageBand: string | undefined | null): boolean {
  return ageBand != null && FLOWED_BANDS.has(ageBand)
}

/**
 * How far into this read the child has walked: one count per rendered page
 * at 3-5/5-8 (`path.length`, matching the reader's actual one-node-per-page
 * rendering there), one count per rendered STOP at 8-11+ (matching
 * `composeStop` in `player/stops.ts`, which is what the reader actually
 * renders as a single scrollable screen there).
 *
 * #ASSUME: data-integrity: a stop boundary is inferred from each node's raw
 * (unfiltered) choice count in `reading.path` -- a node with exactly one
 * choice continues the current stop, a node with zero or two-plus choices
 * (or an ending) starts a new one -- mirroring `composeStop`'s own branch
 * test. This slightly UNDER-counts in the two rare cases where a one-choice
 * node is itself a stop terminal per `stops.ts` (`dead_end`: the one
 * choice's condition is false; `loop`: taking it would revisit a node
 * already in the current stop): telling those apart needs the choice's
 * condition evaluated against the variable state at that exact point in the
 * path, which means replaying the whole read from the start (the same
 * O(depth) cost AL-030 already flags for `back()`). Paying that cost for a
 * coarse position label is not worth it; under-counting a rare loop_and_grow
 * boundary by one is a far smaller honesty problem than the percent bar this
 * function replaces. Never over-counts.
 * #VERIFY: readerProgress.test.ts "counts a flowed run as one stop, not one
 * per node" and "counts each page as itself at page bands".
 */
export function readerPositionCount(
  story: Storybook,
  reading: ReadingState,
  ageBand: string | undefined | null
): number {
  if (!isFlowedBand(ageBand)) {
    return Math.max(1, reading.path.length)
  }
  const nodesById = new Map(story.nodes.map((node) => [node.id, node]))
  let stops = 0
  for (let i = 0; i < reading.path.length; i += 1) {
    const previousNode = i > 0 ? nodesById.get(reading.path[i - 1]) : undefined
    if (i === 0 || previousNode === undefined || previousNode.choices.length !== 1) {
      stops += 1
    }
  }
  return Math.max(1, stops)
}

/** "Page N": the honest, denominator-free position label (W1.2/AL-029). */
export function readerPositionLabel(
  story: Storybook,
  reading: ReadingState,
  ageBand: string | undefined | null
): string {
  return `Page ${readerPositionCount(story, reading, ageBand)}`
}
