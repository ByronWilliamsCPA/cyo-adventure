import { describe, it, expect } from 'vitest'
import { start, visibleChoices, choose } from './engine'
import type { Storybook } from './types'

/**
 * UW-C282 regression. `choices` on a node and `variables` on a storybook are
 * OPTIONAL in schema/storybook.schema.json, which requires only `id` and `body`
 * on a node. The blob reaches the player unnormalised: the read route carries no
 * `response_model`, and `generation/persistence.py` stores a shallow dict copy
 * with no Pydantic round-trip. 777 nodes across 28 of 31 committed filled books
 * omit `choices` on their ending nodes, so before this fix the reader threw
 * `Cannot read properties of undefined (reading 'filter')` at nearly every
 * ending, and `story.variables is not iterable` on a story without variables.
 *
 * Both threw when written; they are the reproduction, not a hypothetical.
 */
const endingWithoutChoicesKey = {
  id: 's',
  version: 1,
  title: 'T',
  start_node: 'n0',
  nodes: [
    { id: 'n0', body: 'open', is_ending: false, choices: [{ id: 'c', label: 'go', target: 'n_end' }] },
    {
      id: 'n_end',
      body: 'done',
      is_ending: true,
      ending: { id: 'e', valence: 'positive', kind: 'success', title: 'W' },
    },
  ],
  variables: [],
  metadata: {},
} as unknown as Storybook

const storyWithoutVariablesKey = {
  id: 's',
  version: 1,
  title: 'T',
  start_node: 'n0',
  nodes: [
    { id: 'n0', body: 'open', is_ending: false, choices: [{ id: 'c', label: 'go', target: 'n_end' }] },
    {
      id: 'n_end',
      body: 'done',
      is_ending: true,
      ending: { id: 'e', valence: 'positive', kind: 'success', title: 'W' },
    },
  ],
  metadata: {},
} as unknown as Storybook

describe('schema-optional fields reach the player unnormalised', () => {
  it('visibleChoices returns empty at an ending with no choices key', () => {
    const atEnding = choose(endingWithoutChoicesKey, start(endingWithoutChoicesKey), 'c')
    expect(atEnding.current_node).toBe('n_end')
    expect(visibleChoices(endingWithoutChoicesKey, atEnding)).toEqual([])
  })

  it('start() works on a story with no variables key', () => {
    const state = start(storyWithoutVariablesKey)
    expect(state.current_node).toBe('n0')
    expect(state.var_state).toEqual({})
  })

  it('a full read to an ending never throws', () => {
    expect(() => {
      const s = choose(storyWithoutVariablesKey, start(storyWithoutVariablesKey), 'c')
      visibleChoices(storyWithoutVariablesKey, s)
    }).not.toThrow()
  })
})
