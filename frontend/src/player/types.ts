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

// Closed unions, never bare strings, mirroring the backend's EndingKind and
// Valence StrEnums (storybook/models.py): the response side keeps the same
// compile-time guarantee as the schema that produced it.
export type EndingKind = 'success' | 'setback' | 'death' | 'capture' | 'completion' | 'discovery'
export type EndingValence = 'positive' | 'neutral' | 'negative'

export interface Ending {
  id: string
  kind: EndingKind
  valence: EndingValence
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

/**
 * One bookmark: a named snapshot of a reading position, stored as one value
 * in `ReadingState.save_slots` (keyed by an opaque slot id). The backend
 * treats `save_slots` as an opaque `dict[str, object]` (api/schemas.py's
 * `ReadingStateBody`/`ReadingStateView`, byte-capped at 64KB, no shape
 * imposed); this shape is a client-side convention only, defined and
 * consumed entirely in `player/engine.ts`'s bookmark functions.
 */
export interface SavedBookmark {
  current_node: string
  var_state: VarState
  visit_set: string[]
  path: string[]
  label: string
  /** ISO 8601 timestamp; sorts bookmark lists newest-first as a plain string
   * comparison, no Date parsing needed. */
  saved_at: string
}
