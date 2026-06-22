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
  Storybook,
  StoryNode,
  VarState,
  VarValue,
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
    varState[effect.var] = (effect.value ?? 0) as VarValue
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
  for (const effect of node?.on_enter ?? []) {
    if (effect.once && !firstEntry) continue
    applyEffect(state.var_state, effect, bounds)
  }
}

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
