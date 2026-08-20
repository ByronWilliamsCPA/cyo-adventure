/**
 * Rendered-stop composition (ADR-026: rendered-stop flow of linear passages).
 *
 * At bands 8-11 and up the reader flows consecutive single-choice, non-ending
 * nodes into one scrollable "stop" instead of stopping at every node, so
 * every stop a reader makes ends at a real choice (or an ending). It
 * introduces no new traversal semantics, it only decides where one stop ends
 * and the next begins. Every node-to-node transition inside a stop is
 * delegated to `choose()` from `./engine`, so a flowed run applies `on_enter`
 * effects, appends to `path`, and adds to `visit_set` exactly as if the reader
 * had tapped that single choice (ADR-026 decision 2).
 *
 * `composeStop` mirrors `src/cyo_adventure/player/stops.py::compose_stop`, and
 * the shared conformance corpus at `schema/conformance/stop_traces.json` (run
 * by both `stops.test.ts` here and `tests/unit/test_stop_conformance.py`)
 * proves THAT function stays in lock-step with the Python side.
 *
 * Scope of that guarantee, precisely: `flowedPrefix` and
 * `composeStopWithHistory` have no Python counterpart, and the corpus cannot
 * cover them, because every corpus case composes from a freshly-tapped state
 * (`engine.start()` plus `prefix_choices`) and so never exercises a resumed
 * one. They are frontend-only reader concerns (UW-F38) and the Python
 * `compose_stop` has no production caller today: its only consumers are
 * `test_stop_conformance.py` and the structural walk documented in
 * `validator/choice_grammar.py`. A green corpus therefore attests that
 * `composeStop` parity is UNCHANGED, not that resumed-stop behaviour is
 * cross-verified. Port both functions before relying on it for that.
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
import type { ReadingState, Storybook, StoryNode, VarState } from './types'

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
  // readonly: a Stop is the pure result of composition, and a caller that
  // rewrote terminalReason or swapped state would silently desync from
  // nodeIds without the shared conformance corpus noticing (it only checks
  // freshly composed stops). Mirrors `@dataclass(frozen=True)` on the Python
  // Stop; like that decorator, this does not deep-freeze nodeIds or state, so
  // the guarantee is the same shallow one on both sides.
  readonly originNode: string
  readonly nodeIds: string[]
  readonly state: ReadingState
  readonly terminalReason: StopTerminalReason
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
 *
 * Note the arity difference from `player/stops.py::compose_stop`, which takes
 * `(story, engine, state)`: that is a consequence of the two engines' shapes,
 * not a divergence in behaviour. `StoryEngine` is a Python class holding
 * per-story state, so the instance must be passed in; `engine.ts` exposes
 * `choose()` as a free function this module imports directly. Both delegate
 * every transition to the engine identically.
 */
export function composeStop(
  story: Storybook,
  state: ReadingState,
  alreadyInStop: readonly string[] = []
): Stop {
  const nodes = nodeIndex(story)
  const nodeIds = [state.current_node]
  // `alreadyInStop` is the flowed prefix `composeStopWithHistory` re-derived
  // from history, and it participates in loop detection without being walked
  // again. A resumed cycle is why: for a persisted `n_a -> n_b -> n_a` stop
  // resumed at `n_b`, a forward pass with a fresh `seen` retakes the
  // `n_b -> n_a` edge and yields `[n_a, n_b, n_a]`, duplicating that node's
  // prose and making `backOneStop` call `back()` once too often. The stop must
  // end at `n_b`, exactly where it ended before the read was persisted.
  // Default empty, so a direct `composeStop` call behaves as it always has.
  const seen = new Set([...alreadyInStop, ...nodeIds])
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
    const choices = node.choices ?? []
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

/**
 * The already-traversed node ids that flowed INTO `state.current_node`, oldest
 * first, or `[]` when `current_node` is a genuine stop origin.
 *
 * `composeStop` only walks forward, by design (see its doc). That is complete
 * for a state produced by a real tap, and incomplete for a state RESUMED from
 * storage: a flowed run persists its terminal (ADR-026 decision 2 requires the
 * hops' effects to apply for real), so re-entering a book, or any remount of
 * the reader, hands `composeStop` the terminal of a stop whose earlier nodes
 * it cannot see. Composed forward from there the stop is length 1 and the
 * flowed prose is silently dropped: the child resumes at the fork and never
 * reads the passage that set it up (UW-F38).
 *
 * This re-derives that missing prefix from `state.path`, which already records
 * the real traversal, so nothing is re-simulated and no effect is re-applied.
 * A predecessor belongs to the same stop exactly when it has one choice
 * targeting the next node in the path, which is the same boundary rule
 * `composeStop` applies walking the other way.
 *
 * Deliberately structural, with no condition re-evaluation: `var_state` has
 * moved on since those hops were taken, so re-evaluating a hop's condition now
 * could answer a different question than the one the traversal already
 * answered. The recorded path is the authority on what happened.
 *
 * Fails closed. Any ambiguity (a path that does not end at `current_node`, an
 * unknown node, a repeat) stops the walk and yields the shorter prefix, so the
 * worst case is today's behavior rather than a wrong one.
 */
export function flowedPrefix(story: Storybook, state: ReadingState): string[] {
  // #CRITICAL: data-integrity: the recorded path describes a traversal of the
  // story version the state was made against; `engine.ts` stamps
  // `version: story.version` on every transition precisely so that is
  // knowable. `ReaderPage` loads the story at a route-selected version and the
  // reading state by `(profileId, storybookId)` alone, with no version in the
  // key and no check between them, so a republish CAN hand this function a
  // path recorded against a different topology.
  //
  // The structural guards below already refuse to walk an edge the loaded
  // story does not have, so a mismatch degrades rather than corrupts. This is
  // stricter on purpose: a republish that happens to preserve a single-choice
  // edge would otherwise let a path from another version look walkable, and
  // "it coincidentally still fits" is not a basis for re-rendering prose a
  // child already read or for sizing a Go back rewind.
  //
  // Fails closed for a state that carries no usable version too (a legacy or
  // hand-built row reads 0), which yields today's un-reconstructed behavior.
  // #VERIFY: stops.test.ts "infers nothing when the state was recorded against
  // a different story version".
  if (state.version !== story.version) return []

  const nodes = nodeIndex(story)
  const path = state.path
  let i = path.length - 1
  // The path must actually end where we are, or it is not describing this
  // position and nothing may be inferred from it.
  if (i < 0 || path[i] !== state.current_node) return []

  const prefix: string[] = []
  const seen = new Set<string>([state.current_node])
  while (i > 0) {
    const predecessorId = path[i - 1]
    const predecessor = nodes.get(predecessorId)
    // A node the story no longer contains, or one already inside this stop
    // (the same cycle `composeStop`'s loop guard refuses to walk), ends it.
    if (predecessor === undefined || seen.has(predecessorId)) break
    // `composeStop`'s forward walk tests `is_ending` BEFORE it counts choices,
    // so the walk-back has to as well or the two disagree on an ending that
    // carries a choice. That shape is schema-invalid, which is exactly why it
    // is checked here: this function's contract is to fail closed on
    // inconsistent data, not to assume the data is consistent.
    if (predecessor.is_ending) break
    // 2+ choices is the previous stop's terminal (a real decision the child
    // stopped at); 0 is an ending. Only a single-choice node ever flows.
    if ((predecessor.choices ?? []).length !== 1) break
    if (predecessor.choices?.[0]?.target !== path[i]) break
    prefix.unshift(predecessorId)
    seen.add(predecessorId)
    i -= 1
  }
  return prefix
}

/**
 * `composeStop`, plus any flowed prefix already recorded in `state.path`.
 *
 * Use this wherever a stop is composed from a state that may have been resumed
 * rather than freshly tapped into (the reader's mount path). Forward behavior
 * is `composeStop`'s, unchanged: the terminal `state` and `terminalReason` are
 * taken from it verbatim, and only `nodeIds`/`originNode` widen to include
 * nodes the reader already walked.
 *
 * Widening `nodeIds` also repairs Go back on a resumed read: `backOneStop`
 * calls `back()` once per node in the stop, so a stop truncated to its
 * terminal rewound into the middle of its own flow instead of to the previous
 * stop's terminal.
 */
export function composeStopWithHistory(story: Storybook, state: ReadingState): Stop {
  // Prefix first, then compose forward with it already counted as part of this
  // stop, so a resumed cycle closes where it originally closed instead of
  // retaking an edge the reader already took.
  const prefix = flowedPrefix(story, state)
  const forward = composeStop(story, state, prefix)
  if (prefix.length === 0) return forward
  return {
    originNode: prefix[0],
    nodeIds: [...prefix, ...forward.nodeIds],
    state: forward.state,
    terminalReason: forward.terminalReason,
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

// #CRITICAL: data-integrity: `seed` must be forwarded to every `back()` call
// below, and every caller must pass the same seed the read began with.
// `back()` replays the recorded path from the read's OWN start
// (`engine.ts::replayRecordedPath`: `start(story)` unseeded,
// `startContinuation(story, null, seed)` seeded) and accepts only a replay
// whose terminal var_state is exactly equal to the live one. Two callers
// disagreeing about the seed therefore disagree about whether Go back is
// possible at all, which is how ADR-028 Task 9 first shipped: the reader's
// availability check omitted the seed while the machine's BACK guard used it,
// so on a seeded read the button rendered and the event was swallowed.
// #VERIFY: stops.test.ts "rewinds a stop on a seeded read only when the seed
// is forwarded".

/** Rewind from a stop's terminal state to the previous stop's terminal node,
 * via `nodeIds.length` calls to `back()`; `null` when there is no previous
 * stop (this was the first stop) or the recorded path cannot be replayed
 * from the read's own start (the seeded start when a seed is given; same
 * fail-closed contract as `back()`). The input is not mutated. */
export function backOneStop(story: Storybook, stop: Stop, seed?: VarState): ReadingState | null {
  let current: ReadingState | null = stop.state
  for (let i = 0; i < stop.nodeIds.length; i += 1) {
    if (current === null) return null
    current = back(story, current, seed)
  }
  return current
}

/** Whether `backOneStop` would succeed for this stop, under the same seed. */
export function canGoBackOneStop(story: Storybook, stop: Stop, seed?: VarState): boolean {
  return backOneStop(story, stop, seed) !== null
}
