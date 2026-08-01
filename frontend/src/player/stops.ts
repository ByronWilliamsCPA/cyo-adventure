/**
 * Rendered-stop composition (ADR-026: rendered-stop flow of linear passages).
 *
 * At bands 8-11 and up the reader flows consecutive single-choice, non-ending
 * nodes into one scrollable "stop" instead of stopping at every node, so
 * every stop a reader makes ends at a real choice (or an ending). This
 * mirrors `src/cyo_adventure/player/stops.py` exactly: it introduces no new
 * traversal semantics, it only decides where one stop ends and the next
 * begins. Every node-to-node transition inside a stop is delegated to
 * `choose()` from `./engine`, so a flowed run applies `on_enter` effects,
 * appends to `path`, and adds to `visit_set` exactly as if the reader had
 * tapped that single choice (ADR-026 decision 2).
 *
 * The shared conformance corpus at `schema/conformance/stop_traces.json` (run
 * by both `stops.test.ts` here and `tests/unit/test_stop_conformance.py`)
 * proves this stays in lock-step with the Python side.
 *
 * AL-030: composing a stop walks every node in the run, so a caller (the
 * reader) MUST NOT call `composeStop` again on every render of an
 * already-flowed stop. Compose once per stop and hold on to the returned
 * `Stop` (or at least its terminal `ReadingState`) for as long as the reader
 * is looking at that stop; only compose again once the reader actually taps
 * a choice into a new stop. This module deliberately does not build a cache
 * layer itself (per the ADR-026 W1.1 scope): memoization is the caller's
 * responsibility, this module only makes it cheap to do.
 */

import { back, choose } from './engine'
import { evaluate } from './evaluator'
import type { ReadingState, Storybook, StoryNode } from './types'

/** Why a stop's composition stopped at its terminal node (ADR-026 decision 1).
 *
 * - `branch`: the terminal node offers 2+ choices (the ordinary case: a real
 *   decision point).
 * - `ending`: the terminal node is an ending.
 * - `dead_end`: the terminal node has exactly one choice and its condition
 *   evaluated false, so there is nothing to flow into.
 * - `loop`: the single true-condition choice would revisit a node already in
 *   this same composed stop; composition stops rather than looping forever.
 */
export type StopTerminalReason = 'branch' | 'ending' | 'dead_end' | 'loop'

/** A rendered stop: one or more flowed node bodies ending in a real choice.
 *
 * Go-back-by-stop (ADR-026 decision 3): rewinding a stop means undoing the
 * tap that started it, landing on the *previous* stop's terminal node (a real
 * choice point), never mid-flow. `nodeIds.length` is exactly the number of
 * single-step `back()` calls (`./engine`) needed to reach that node from
 * `state`; see `backOneStop` below, which does that by calling the existing
 * `back()` repeatedly rather than reimplementing replay.
 */
export interface Stop {
  originNode: string
  nodeIds: string[]
  state: ReadingState
  terminalReason: StopTerminalReason
}

function nodeIndex(story: Storybook): Map<string, StoryNode> {
  return new Map(story.nodes.map((node) => [node.id, node]))
}

/**
 * Compose the rendered stop starting at `state.current_node`.
 *
 * Callers must pass a state whose `current_node` is a genuine stop origin:
 * either a fresh read (`start()`/`startContinuation()`) or a state produced
 * by an explicit tap on a visible choice (`choose()`). `composeStop` does not
 * re-derive stop boundaries from history; it only walks forward.
 *
 * @param story - The parsed, schema-valid Storybook being played. Used to
 *   look up each node's full (unfiltered) choice list; `engine.ts` keeps its
 *   node index module-private, so this module keeps its own, mirroring that
 *   file's own `nodeIndex` helper.
 * @param state - The state to start composing from. Not mutated; the
 *   returned `Stop.state` is a fresh state built by `choose()`, or `state`
 *   itself when the stop is length 1 (already at a branch, an ending, or a
 *   dead end).
 * @returns The composed stop, terminating at a branch, an ending, or a
 *   dead-end/loop guard.
 */
export function composeStop(story: Storybook, state: ReadingState): Stop {
  const nodes = nodeIndex(story)
  const nodeIds = [state.current_node]
  const seen = new Set(nodeIds)
  let current = state
  for (;;) {
    const node = nodes.get(current.current_node)
    // Mirror engine.ts::enterNode: a dangling node id is an error, not a
    // silent stop, so a corrupt story fails loudly here too.
    if (!node) {
      throw new Error(`node '${current.current_node}' does not exist in the story`)
    }
    if (node.is_ending) {
      return { originNode: nodeIds[0], nodeIds, state: current, terminalReason: 'ending' }
    }
    const choices = node.choices
    if (choices.length !== 1) {
      // 2+ choices is the ordinary branch stop. 0 choices on a non-ending
      // node cannot happen (the schema requires >=1 choice on a non-ending
      // node), but if it ever did, treating it as a dead end is the safe
      // fallback: there is nothing to render but this node.
      return {
        originNode: nodeIds[0],
        nodeIds,
        state: current,
        terminalReason: choices.length === 0 ? 'dead_end' : 'branch',
      }
    }
    const [choice] = choices
    if (choice.condition != null && !evaluate(choice.condition, current.var_state)) {
      // The dead-end guard (ADR-026 decision 5): a single choice whose
      // condition is false has nothing to flow into, so the stop ends here
      // showing this node's (empty) visible choice list.
      return { originNode: nodeIds[0], nodeIds, state: current, terminalReason: 'dead_end' }
    }
    // #CRITICAL: timing: without this check, a single-choice cycle inside one
    // composed stop (node A's only choice targets B, B's only choice targets
    // A, with conditions that never resolve false) would recurse forever:
    // composeStop would never return, hanging the read. A node already
    // visited within *this* stop is where the loop closes, so the stop ends
    // there instead of retaking the same edge.
    // #VERIFY: schema/conformance/stop_traces.json "loop_back_ends_stop";
    // stops.test.ts and tests/unit/test_stop_conformance.py both run it.
    if (seen.has(choice.target)) {
      return { originNode: nodeIds[0], nodeIds, state: current, terminalReason: 'loop' }
    }
    current = choose(story, current, choice.id)
    nodeIds.push(current.current_node)
    seen.add(current.current_node)
  }
}

// ---------------------------------------------------------------------------
// Go back one stop (ADR-026 decision 3, ADR-024). Frontend-only, exactly like
// `back()`/`canGoBack()` in engine.ts, which this delegates to rather than
// reimplementing replay: calling `back()` once per node in the current stop
// always lands on the previous stop's terminal node.
//
// Why: a stop's `nodeIds` is a contiguous run of `state.path`, and the node
// immediately before `nodeIds[0]` (the origin) in `path` is, by construction,
// the previous stop's terminal node (the real choice point whose tap
// produced this stop's origin). Calling `back()` `nodeIds.length` times walks
// `state.path` backwards exactly that far. When this is the first stop
// (origin === story.start_node), there is no such node, and the last `back()`
// call correctly returns null (path.length <= 1), so this fails closed
// without any special-casing.
// ---------------------------------------------------------------------------

/** Rewind from a stop's terminal state to the previous stop's terminal node,
 * via `nodeIds.length` calls to `back()`; `null` when there is no previous
 * stop (this was the first stop) or the recorded path cannot be replayed
 * (same fail-closed contract as `back()`). The input is not mutated. */
export function backOneStop(story: Storybook, stop: Stop): ReadingState | null {
  let current: ReadingState | null = stop.state
  for (let i = 0; i < stop.nodeIds.length; i += 1) {
    if (current === null) return null
    current = back(story, current)
  }
  return current
}

/** Whether `backOneStop` would succeed for this stop. */
export function canGoBackOneStop(story: Storybook, stop: Stop): boolean {
  return backOneStop(story, stop) !== null
}
