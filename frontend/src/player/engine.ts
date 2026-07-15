/**
 * Deterministic story player engine (Story Runtime Semantics v1), TypeScript port.
 *
 * This mirrors the Python reference engine
 * (`src/cyo_adventure/player/engine.py`) exactly so the player and validator
 * never disagree. The shared player-trace conformance corpus
 * (`schema/conformance/player_traces.json`) is run by both implementations.
 *
 * Transition order on every choice: evaluate condition -> apply choice effects
 * -> set current_node -> apply target on_enter effects (once:true first entry).
 * The engine is pure: choose() returns a new ReadingState and never mutates input.
 */

import { evaluate } from './evaluator'
import type { Choice, Effect, ReadingState, Storybook, StoryNode, VarState } from './types'

function nodeIndex(story: Storybook): Map<string, StoryNode> {
  return new Map(story.nodes.map((node) => [node.id, node]))
}

function intBounds(story: Storybook): Map<string, [number | null, number | null]> {
  const bounds = new Map<string, [number | null, number | null]>()
  for (const v of story.variables) {
    if (v.type === 'int') {
      bounds.set(v.name, [v.min ?? null, v.max ?? null])
    }
  }
  return bounds
}

function clamp(
  bounds: Map<string, [number | null, number | null]>,
  name: string,
  value: number
): number {
  const [low, high] = bounds.get(name) ?? [null, null]
  if (low !== null && value < low) return low
  if (high !== null && value > high) return high
  return value
}

function applyEffect(
  varState: VarState,
  effect: Effect,
  bounds: Map<string, [number | null, number | null]>
): void {
  if (effect.op === 'set') {
    const value = effect.value ?? 0
    // Clamp a numeric set to the variable's bounds, like inc/dec, so the TS and
    // Python engines agree and a story cannot seed an out-of-range value.
    varState[effect.var] = typeof value === 'number' ? clamp(bounds, effect.var, value) : value
    return
  }
  const current = varState[effect.var]
  const base = typeof current === 'number' ? current : 0
  const delta = typeof effect.value === 'number' ? effect.value : 0
  const updated = effect.op === 'inc' ? base + delta : base - delta
  varState[effect.var] = clamp(bounds, effect.var, updated)
}

function enterNode(
  story: Storybook,
  state: ReadingState,
  nodeId: string,
  firstEntry: boolean,
  bounds: Map<string, [number | null, number | null]>
): void {
  if (!state.visit_set.includes(nodeId)) {
    state.visit_set.push(nodeId)
  }
  const node = nodeIndex(story).get(nodeId)
  // Mirror the Python engine: entering an unknown node id is an error, not a
  // silent no-op, so a dangling choice target fails loudly in both runtimes.
  if (!node) {
    throw new Error(`node '${nodeId}' does not exist in the story`)
  }
  for (const effect of node.on_enter ?? []) {
    if (effect.once && !firstEntry) continue
    applyEffect(state.var_state, effect, bounds)
  }
}

// #ASSUME: data-integrity: enterNode trusts that nodeId exists in the story.
// A dangling target (choice pointing to a non-existent node) throws immediately,
// matching the Python engine and the Layer-1 L1-2 reference-integrity check.
// #VERIFY: the validator rejects stories with dangling targets before they reach
// the reader, so this throw is a belt-and-suspenders guard, not a normal path.

/** Begin a new read at start_node with initial variable values. */
export function start(story: Storybook): ReadingState {
  const varState: VarState = {}
  for (const v of story.variables) {
    varState[v.name] = v.initial
  }
  const state: ReadingState = {
    current_node: story.start_node,
    var_state: varState,
    path: [story.start_node],
    visit_set: [],
    version: story.version,
    state_revision: 0,
    save_slots: {},
  }
  enterNode(story, state, story.start_node, true, intBounds(story))
  return state
}

// #CRITICAL: data-integrity: a continuation state cannot be reproduced by
// replaying choices from start_node, so continuation saves MUST NOT carry a
// choice_path (the server would replay-from-start and reject them; see
// api/reading.py's note that choice_path may become required). The server's
// structural floor (player/replay.py::_check_structure) is what admits these
// saves, so this function must uphold its exact invariants: every declared
// variable present, values correctly typed and in-bounds (clamped below),
// current_node === path[path.length - 1], all node ids known.
// #VERIFY: engine.test.ts "startContinuation" describe block; if choice_path
// ever becomes required server-side, the server needs a continuation-aware
// replay mode first.
/** Begin a continuation read at a declared entry node, seeding name-matched
 * carried variables (WS-G decision G3). Wrong-typed carried values are
 * skipped (the declared initial stands); carried ints are clamped to the
 * variable's declared bounds. */
export function startContinuation(
  story: Storybook,
  entryNode: string | null,
  carriedVarState?: VarState
): ReadingState {
  const bounds = intBounds(story)
  const varState: VarState = {}
  for (const v of story.variables) {
    varState[v.name] = v.initial
    const carried = carriedVarState?.[v.name]
    if (carried === undefined) continue
    if (v.type === 'bool' && typeof carried === 'boolean') {
      varState[v.name] = carried
    } else if (v.type === 'int' && typeof carried === 'number' && Number.isInteger(carried)) {
      varState[v.name] = clamp(bounds, v.name, carried)
    }
  }
  const nodeId =
    entryNode !== null && story.nodes.some((n) => n.id === entryNode) ? entryNode : story.start_node
  const state: ReadingState = {
    current_node: nodeId,
    var_state: varState,
    path: [nodeId],
    visit_set: [],
    version: story.version,
    state_revision: 0,
    save_slots: {},
  }
  enterNode(story, state, nodeId, true, bounds)
  return state
}

/** Choices visible at the current node (false-condition choices are hidden). */
export function visibleChoices(story: Storybook, state: ReadingState): Choice[] {
  const node = nodeIndex(story).get(state.current_node)
  if (!node) return []
  return node.choices.filter((c) => c.condition == null || evaluate(c.condition, state.var_state))
}

/** Whether the current node is an ending. */
export function isEnding(story: Storybook, state: ReadingState): boolean {
  return nodeIndex(story).get(state.current_node)?.is_ending ?? false
}

/** The stable ending id of the current node, if it is an ending. */
export function currentEndingId(story: Storybook, state: ReadingState): string | null {
  const node = nodeIndex(story).get(state.current_node)
  return node?.is_ending ? (node.ending?.id ?? null) : null
}

// #CRITICAL: timing: choose() transition order (condition check -> choice effects
// -> set current_node -> on_enter effects) MUST stay in sync with the Python
// reference engine (src/cyo_adventure/player/engine.py). Divergence causes the
// Layer-2 validator and the runtime to disagree on reachable states.
// #VERIFY: shared player_traces.json conformance corpus is run by both engines.

/** Apply a choice and return the resulting reading state (input is not mutated). */
export function choose(story: Storybook, state: ReadingState, choiceId: string): ReadingState {
  if (isEnding(story, state)) {
    throw new Error(`cannot choose from ending node '${state.current_node}'`)
  }
  const node = nodeIndex(story).get(state.current_node)
  const choice = node?.choices.find((c) => c.id === choiceId)
  if (!choice) {
    throw new Error(`choice '${choiceId}' does not exist on the current node`)
  }
  if (!(choice.condition == null || evaluate(choice.condition, state.var_state))) {
    throw new Error(`choice '${choiceId}' is not visible in the current state`)
  }
  // #ASSUME: data-integrity: intBounds is rebuilt per choose() call; bounds are
  // not cached across calls. A cached bounds map would go stale if the Storybook
  // object is replaced (e.g. on a story update) without clearing the cache.
  // #VERIFY: choose() receives a fresh story reference on each call from the reader.
  const bounds = intBounds(story)
  const next: ReadingState = {
    current_node: state.current_node,
    var_state: { ...state.var_state },
    path: [...state.path],
    visit_set: [...state.visit_set],
    version: state.version,
    state_revision: state.state_revision,
    save_slots: { ...state.save_slots },
  }
  for (const effect of choice.effects ?? []) {
    applyEffect(next.var_state, effect, bounds)
  }
  next.current_node = choice.target
  const firstEntry = !next.visit_set.includes(choice.target)
  enterNode(story, next, choice.target, firstEntry, bounds)
  next.path.push(choice.target)
  return next
}

// ---------------------------------------------------------------------------
// Go back one page (kid mis-tap recovery). A frontend-only affordance built on
// replay: the previous state is recomputed by replaying the recorded node path
// from the start through this same deterministic engine, never by reversing
// effects, so a post-back state is exactly the state of a shorter read. No new
// state semantic is introduced, so nothing needs mirroring in the Python engine.
// ---------------------------------------------------------------------------

// #EDGE: timing: the path replay backtracks across same-target sibling choices
// (a node may offer two choices to the same target with different effects,
// like the lantern story's take/ignore pair), which is exponential in the
// pathological case. Real stories are short and near-deterministic; this
// budget bounds the search and fails closed (no Go back) if exhausted.
// #VERIFY: engine.test.ts replays the ambiguous lantern ignore-lantern branch.
const MAX_REPLAY_STEPS = 5000

function sameVarState(a: VarState, b: VarState): boolean {
  const aKeys = Object.keys(a)
  return aKeys.length === Object.keys(b).length && aKeys.every((key) => a[key] === b[key])
}

/** Order-independent id-set equality, mirroring how the backend replay gate
 * compares visit_set (player/replay.py::_check_replay uses set equality). */
function sameIdSet(a: string[], b: string[]): boolean {
  const aSet = new Set(a)
  const bSet = new Set(b)
  return aSet.size === bSet.size && [...aSet].every((id) => bSet.has(id))
}

interface ReplayBudget {
  remaining: number
}

/** Depth-first reconstruction of live.path: at each step try every visible
 * choice whose target is the next recorded node, and accept only a branch
 * whose end state reproduces the live state. Appends to states in place;
 * states[i] is the state after i choices when the search succeeds. */
function searchPathReplay(
  story: Storybook,
  live: ReadingState,
  states: ReadingState[],
  budget: ReplayBudget
): boolean {
  const depth = states.length - 1
  const current = states[depth]
  if (depth === live.path.length - 1) {
    // current_node and path match by construction; the variables and visit set
    // must match too, so an unfaithful reconstruction (a different same-target
    // sibling than the one actually taken) is rejected, not rewritten into
    // the child's history.
    return sameVarState(current.var_state, live.var_state) && sameIdSet(current.visit_set, live.visit_set)
  }
  const targetId = live.path[depth + 1]
  for (const candidate of visibleChoices(story, current)) {
    if (candidate.target !== targetId) continue
    if (budget.remaining <= 0) return false
    budget.remaining -= 1
    let next: ReadingState
    try {
      next = choose(story, current, candidate.id)
    } catch {
      // A dangling target throws inside choose(); treat the branch as dead and
      // fail closed rather than crash the reader on a corrupt story.
      continue
    }
    states.push(next)
    if (searchPathReplay(story, live, states, budget)) return true
    states.pop()
  }
  return false
}

/** Replay live.path from the story's start, returning the state after each
 * recorded step (result[i] is the state after i choices), or null when no
 * replay of the recorded path reproduces the live state. */
function replayRecordedPath(story: Storybook, live: ReadingState): ReadingState[] | null {
  // #EDGE: data-integrity: a continuation read starts mid-story with carried
  // variables (see the #CRITICAL note on startContinuation) and can never be
  // reproduced by replaying from start_node, so it gets no Go back rather
  // than a wrong one.
  // #VERIFY: engine.test.ts "fails closed for a continuation state".
  if (live.path.length === 0 || live.path[0] !== story.start_node) return null
  let initial: ReadingState
  try {
    initial = start(story)
  } catch {
    // A dangling start node: fail closed, same as the dead-branch case above.
    return null
  }
  const states = [initial]
  return searchPathReplay(story, live, states, { remaining: MAX_REPLAY_STEPS }) ? states : null
}

// #ASSUME: data-integrity: a state saved after Go back is indistinguishable
// from having simply made fewer choices, so the existing save path needs no
// change. Verified against src/cyo_adventure/api/reading.py::put_reading_state
// (revision-based optimistic concurrency: 409 only on version/state_revision
// mismatch; nothing requires path to grow between saves) and
// player/replay.py::_check_structure (known node ids, current_node ===
// path[path.length - 1], complete in-bounds var_state), all of which a
// replayed shorter state satisfies by construction; choice_path is optional
// and the frontend does not send it.
// #VERIFY: ReaderPage stamps state_revision from its own revisionRef before
// each PUT, so the revision carried over below never fights the server
// counter; tests/unit/test_replay.py pins the structural floor server-side.
/** The reading state as if the child had made every recorded choice except
 * the last one, recomputed via replay (never by reversing effects); null when
 * there is nothing to undo or the recorded path cannot be faithfully replayed
 * from the start (continuation reads). The input is not mutated. */
export function back(story: Storybook, state: ReadingState): ReadingState | null {
  if (state.path.length <= 1) return null
  const states = replayRecordedPath(story, state)
  if (states === null) return null
  const previous = states[states.length - 2]
  return {
    current_node: previous.current_node,
    var_state: { ...previous.var_state },
    path: [...previous.path],
    visit_set: [...previous.visit_set],
    version: previous.version,
    // Rewind only what choices produced: the server-revision counter and save
    // slots are owned outside the choice history and carry over unchanged.
    state_revision: state.state_revision,
    save_slots: { ...state.save_slots },
  }
}

/** Whether Go back is available: at least one recorded choice, and the
 * recorded path is faithfully replayable from the start. */
export function canGoBack(story: Storybook, state: ReadingState): boolean {
  return back(story, state) !== null
}
