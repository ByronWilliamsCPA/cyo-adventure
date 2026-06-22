/**
 * Storybook and reading-state types for the client player.
 *
 * These mirror the Pydantic Storybook schema and the runtime-semantics save
 * format. Reading-state fields use snake_case so the same object serializes
 * directly to the reading-state API payload and IndexedDB cache.
 */

import type { Condition, VarState } from './evaluator'

export type { Condition, VarState, VarValue } from './evaluator'

export interface Effect {
  op: 'set' | 'inc' | 'dec'
  var: string
  value?: boolean | number | null
  once?: boolean
}

export interface Ending {
  id: string
  type: string
  title: string
}

export interface Choice {
  id: string
  label: string
  target: string
  condition?: Condition | null
  effects?: Effect[]
}

export interface StoryNode {
  id: string
  body: string
  on_enter?: Effect[]
  choices: Choice[]
  is_ending: boolean
  ending?: Ending | null
  tags?: string[]
}

export interface Variable {
  name: string
  type: 'bool' | 'int'
  initial: boolean | number
  min?: number | null
  max?: number | null
}

export interface Storybook {
  schema_version: string
  id: string
  version: number
  title: string
  metadata: Record<string, unknown>
  variables: Variable[]
  start_node: string
  nodes: StoryNode[]
}

/** A reading-state save; field names match the API and Python save format. */
export interface ReadingState {
  current_node: string
  var_state: VarState
  path: string[]
  visit_set: string[]
  version: number
  state_revision: number
  save_slots: Record<string, unknown>
}
