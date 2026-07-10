import { describe, expect, it } from 'vitest'

import { SATISFYING_ENDING_KINDS, parseContinuation, seriesMeta } from './series'
import type { Storybook } from './types'

const base: Storybook = {
  schema_version: '2.0',
  id: 's_x',
  version: 1,
  title: 'X',
  metadata: {},
  variables: [],
  start_node: 'n_a',
  nodes: [{ id: 'n_a', body: '', is_ending: true, ending: null, choices: [] }],
}

const block = {
  series_id: 'ser-1',
  book_index: 1,
  series_entry_node: 'n_a',
  is_final: false,
  carries_state: true,
}

describe('seriesMeta', () => {
  it('parses a well-formed embedded block', () => {
    const story = { ...base, metadata: { series: block } }
    expect(seriesMeta(story)).toEqual({
      seriesId: 'ser-1',
      bookIndex: 1,
      entryNode: 'n_a',
      isFinal: false,
      carriesState: true,
    })
  })

  it('returns null when metadata has no series block', () => {
    expect(seriesMeta(base)).toBeNull()
  })

  it('returns null when the block is malformed', () => {
    const story = { ...base, metadata: { series: { series_id: 7 } } }
    expect(seriesMeta(story)).toBeNull()
  })

  it('maps a missing entry node to null', () => {
    const story = {
      ...base,
      metadata: { series: { ...block, series_entry_node: undefined } },
    }
    expect(seriesMeta(story)?.entryNode).toBeNull()
  })
})

describe('SATISFYING_ENDING_KINDS', () => {
  it('matches the validator: success and completion only', () => {
    expect([...SATISFYING_ENDING_KINDS].sort()).toEqual(['completion', 'success'])
    expect(SATISFYING_ENDING_KINDS.has('discovery')).toBe(false)
  })
})

describe('parseContinuation', () => {
  it('parses a navigation-state continuation seed', () => {
    const state = { continuation: { entryNode: 'n_a', varState: { courage: 3 } } }
    expect(parseContinuation(state)).toEqual({ entryNode: 'n_a', varState: { courage: 3 } })
  })

  it('returns undefined for absent or malformed state', () => {
    expect(parseContinuation(null)).toBeUndefined()
    expect(parseContinuation({})).toBeUndefined()
    expect(parseContinuation({ continuation: 'nope' })).toBeUndefined()
  })

  it('defaults a missing entryNode to null', () => {
    expect(parseContinuation({ continuation: {} })).toEqual({
      entryNode: null,
      varState: undefined,
    })
  })
})
