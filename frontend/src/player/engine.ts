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
import type {
  Choice,
  Effect,
  ReadingState,
  SavedBookmark,
  Storybook,
  StoryNode,
  VarState,
} from './types'

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
    return (
      sameVarState(current.var_state, live.var_state) &&
      sameIdSet(current.visit_set, live.visit_set)
    )
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

// #VERIFY: engine.test.ts "offers Go back on a seeded read", "still fails
// closed when the recorded path does not start where it should", and
// "fails closed for a continuation state (path does not begin at
// start_node)".
/** Replay live.path from the read's own start (the seeded start when a seed
 * is given, story.start_node otherwise), returning the state after each
 * recorded step (result[i] is the state after i choices), or null when no
 * replay of the recorded path reproduces the live state. */
export function replayRecordedPath(
  story: Storybook,
  live: ReadingState,
  seed?: VarState
): ReadingState[] | null {
  // The recorded path must begin where a read with THIS seed begins. The
  // seeded start supplies the carried variables the read actually began
  // with; replaying from declared initials made the terminal var_state
  // comparison in searchPathReplay fail for every seeded read, so Go back
  // was disabled. entryNode is null here, so initial.current_node is still
  // story.start_node in every case: the node comparison below is unchanged,
  // and the fail-closed guarantee it enforces is unchanged with it.
  let initial: ReadingState
  try {
    initial = seed === undefined ? start(story) : startContinuation(story, null, seed)
  } catch {
    // A dangling start node: fail closed, same as the dead-branch case above.
    return null
  }
  if (live.path.length === 0 || live.path[0] !== initial.current_node) return null
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
 * from the read's own start (the seeded start when a seed is given). The
 * input is not mutated. */
export function back(story: Storybook, state: ReadingState, seed?: VarState): ReadingState | null {
  if (state.path.length <= 1) return null
  const states = replayRecordedPath(story, state, seed)
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
 * recorded path is faithfully replayable from the read's own start. */
export function canGoBack(story: Storybook, state: ReadingState, seed?: VarState): boolean {
  return back(story, state, seed) !== null
}

// ---------------------------------------------------------------------------
// Bookmarks (save-slot feature, distinct from the Go back undo above): a
// named snapshot of a reading position a reader chooses to save, so they can
// keep reading past it and return later. Stored in the existing
// `save_slots` field, which the backend has always persisted, synced across
// devices, and byte-capped opaquely (api/schemas.py); nothing here changes
// the wire contract, only what this client chooses to put in that bag.
// ---------------------------------------------------------------------------

const MAX_BOOKMARKS = 10

/** Runtime shape guard: a save_slots value written by a future feature (or a
 * stale format from before this one existed) must never be treated as a
 * bookmark and crash the bookmarks UI; it is silently excluded instead. */
function isSavedBookmark(value: unknown): value is SavedBookmark {
  if (value === null || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return (
    typeof v.current_node === 'string' &&
    typeof v.var_state === 'object' &&
    v.var_state !== null &&
    Array.isArray(v.visit_set) &&
    v.visit_set.every((id) => typeof id === 'string') &&
    Array.isArray(v.path) &&
    v.path.every((id) => typeof id === 'string') &&
    typeof v.label === 'string' &&
    typeof v.saved_at === 'string'
  )
}

/** Every bookmark currently saved, newest first. Any `save_slots` entry that
 * does not look like a bookmark (see `isSavedBookmark`) is silently
 * excluded, never thrown on. */
export function listBookmarks(state: ReadingState): Array<{ id: string; bookmark: SavedBookmark }> {
  return Object.entries(state.save_slots)
    .filter((entry): entry is [string, SavedBookmark] => isSavedBookmark(entry[1]))
    .map(([id, bookmark]) => ({ id, bookmark }))
    .sort((a, b) => b.bookmark.saved_at.localeCompare(a.bookmark.saved_at))
}

/** Whether another bookmark can be saved right now.
 *
 * #ASSUME: data-integrity: 10 is a client-side UX ceiling, not derived from
 * the backend's 64,000-byte save_slots budget (a single bookmark snapshot,
 * dominated by var_state and a short path, is far smaller than that); it
 * exists so a reader cannot turn the bookmarks list into an unusable wall of
 * entries, not to protect the byte cap. #VERIFY: BookmarksPanel.test.tsx
 * asserts Save is disabled at the ceiling.
 */
export function canSaveBookmark(state: ReadingState): boolean {
  return listBookmarks(state).length < MAX_BOOKMARKS
}

/** Save the CURRENT position as a new bookmark under a fresh slot id.
 *
 * Pure and immutable like every other function in this module: returns a
 * new ReadingState, never mutates `state`. `slotId`/`savedAt` are injected
 * (crypto.randomUUID() / new Date().toISOString() at the real call site,
 * player/machine.ts) rather than generated here, so this function stays as
 * deterministically testable as `choose()`/`back()`.
 */
export function saveBookmark(
  state: ReadingState,
  slotId: string,
  label: string,
  savedAt: string
): ReadingState {
  const bookmark: SavedBookmark = {
    current_node: state.current_node,
    var_state: { ...state.var_state },
    visit_set: [...state.visit_set],
    path: [...state.path],
    label,
    saved_at: savedAt,
  }
  return {
    ...state,
    save_slots: { ...state.save_slots, [slotId]: bookmark },
  }
}

/** Remove a bookmark. A missing/already-removed slotId is a no-op (matches
 * `Record` delete semantics), not an error: a doubled delete tap (a slow
 * network response racing a second tap) must never throw. */
export function deleteBookmark(state: ReadingState, slotId: string): ReadingState {
  const nextSlots = { ...state.save_slots }
  delete nextSlots[slotId]
  return { ...state, save_slots: nextSlots }
}

/** Make a saved bookmark the new LIVE position (current_node/var_state/
 * visit_set/path), keeping save_slots (including this same bookmark)
 * unchanged, so "jump to bookmark" does not also delete it.
 *
 * Returns null, never throws, when slotId does not resolve to a bookmark
 * (deleted by another device since the list was rendered, or a corrupt
 * save_slots value) -- the same fail-closed contract as `back()` above, for
 * the same reason: this is driven by a tap on a list the UI already
 * rendered from a possibly-stale snapshot.
 */
export function loadBookmark(state: ReadingState, slotId: string): ReadingState | null {
  const raw = state.save_slots[slotId]
  if (!isSavedBookmark(raw)) return null
  return {
    current_node: raw.current_node,
    var_state: { ...raw.var_state },
    visit_set: [...raw.visit_set],
    path: [...raw.path],
    version: state.version,
    state_revision: state.state_revision,
    save_slots: { ...state.save_slots },
  }
}
