import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { choose, currentEndingId, start, startContinuation, visibleChoices } from './engine'
import type { ReadingState, Storybook, VarState } from './types'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')

interface Trace {
  name: string
  choices: string[]
  expected: {
    current_node: string
    var_state: VarState
    visit_set: string[]
    ending_id: string | null
  }
  story: Storybook
}

const corpus = JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
  traces: Trace[]
}

function play(story: Storybook, choices: string[]): ReadingState {
  let state = start(story)
  for (const choiceId of choices) {
    state = choose(story, state, choiceId)
  }
  return state
}

describe('player engine cross-implementation conformance', () => {
  it.each(corpus.traces.map((t) => [t.name, t] as const))(
    'reaches the expected state for %s',
    (_name, trace) => {
      const state = play(trace.story, trace.choices)
      expect(state.current_node).toBe(trace.expected.current_node)
      expect(state.var_state).toEqual(trace.expected.var_state)
      expect([...state.visit_set].sort()).toEqual([...trace.expected.visit_set].sort())
      expect(currentEndingId(trace.story, state)).toBe(trace.expected.ending_id)
    }
  )
})

describe('player engine behaviour', () => {
  const lantern = corpus.traces[0].story

  it('hides a false-condition choice', () => {
    const state = choose(lantern, start(lantern), 'c_ignore_lantern')
    const visible = visibleChoices(lantern, state).map((c) => c.id)
    expect(visible).toEqual(['c_bright_tunnel'])
  })

  it('does not mutate the input state on choose', () => {
    const initial = start(lantern)
    choose(lantern, initial, 'c_take_lantern')
    expect(initial.current_node).toBe('n_entrance')
    expect(initial.var_state).toEqual({ has_lantern: false })
  })

  it('rejects a hidden choice', () => {
    const state = choose(lantern, start(lantern), 'c_ignore_lantern')
    expect(() => choose(lantern, state, 'c_dark_passage')).toThrow(/not visible/)
  })

  it('rejects choosing from an ending', () => {
    let state = choose(lantern, start(lantern), 'c_ignore_lantern')
    state = choose(lantern, state, 'c_bright_tunnel')
    expect(() => choose(lantern, state, 'anything')).toThrow(/ending/)
  })

  it('rejects a choice id that does not exist on the current node', () => {
    const state = start(lantern)
    expect(() => choose(lantern, state, 'c_does_not_exist')).toThrow(
      /does not exist on the current node/
    )
  })

  it('throws when a choice targets a node id that does not exist in the story', () => {
    // A dangling target: the validator normally rejects this before it reaches
    // the reader (see the #ASSUME note above enterNode), so this is a
    // belt-and-suspenders guard exercised directly here.
    const dangling: Storybook = {
      ...lantern,
      nodes: [
        {
          id: 'n_entrance',
          body: 'Start',
          is_ending: false,
          choices: [{ id: 'c_go', label: 'Go', target: 'n_missing' }],
        },
      ],
    }
    const state = start(dangling)
    expect(() => choose(dangling, state, 'c_go')).toThrow(
      /node 'n_missing' does not exist in the story/
    )
  })
})

describe('startContinuation', () => {
  const story: Storybook = {
    schema_version: '2.0',
    id: 's_cont',
    version: 1,
    title: 'Continuation',
    metadata: {},
    variables: [
      { name: 'courage', type: 'int', initial: 0, min: 0, max: 5 },
      { name: 'brave', type: 'bool', initial: false },
    ],
    start_node: 'n_one',
    nodes: [
      { id: 'n_one', body: 'one', is_ending: false, choices: [] },
      {
        id: 'n_two',
        body: 'two',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'courage', value: 1 }],
        choices: [],
      },
    ],
  }

  it('starts at the entry node with seeded name-matched values', () => {
    const state = startContinuation(story, 'n_two', { courage: 2, brave: true, ghost: 9 })
    expect(state.current_node).toBe('n_two')
    expect(state.path).toEqual(['n_two'])
    // seeded 2, then n_two's on_enter inc applies on top
    expect(state.var_state).toEqual({ courage: 3, brave: true })
    expect(state.state_revision).toBe(0)
  })

  it('skips wrong-typed and non-integer carried values', () => {
    const state = startContinuation(story, 'n_one', { courage: true, brave: 3.5 })
    expect(state.var_state).toEqual({ courage: 0, brave: false })
  })

  it('clamps an out-of-bounds carried int to the declared bounds', () => {
    const state = startContinuation(story, 'n_one', { courage: 99 })
    expect(state.var_state.courage).toBe(5)
  })

  it('clamps a below-bounds carried int up to the declared lower bound', () => {
    // min (1) sits above initial (2) here so the three outcomes are
    // distinguishable: clamped-to-min (1), skipped-keeps-initial (2), or
    // seeded raw (-3).
    const bounded: Storybook = {
      ...story,
      variables: [{ name: 'courage', type: 'int', initial: 2, min: 1, max: 5 }],
    }
    const state = startContinuation(bounded, 'n_one', { courage: -3 })
    expect(state.var_state.courage).toBe(1)
  })

  it('rejects a non-integer carried value for an int variable (initial stands)', () => {
    // Distinct from the wrong-type test above: 2.5 is a number, but the
    // Number.isInteger guard still rejects it rather than clamping it.
    const state = startContinuation(story, 'n_one', { courage: 2.5 })
    expect(state.var_state.courage).toBe(0)
  })

  it('falls back to start_node for a null or unknown entry node', () => {
    expect(startContinuation(story, null, undefined).current_node).toBe('n_one')
    expect(startContinuation(story, 'n_missing', undefined).current_node).toBe('n_one')
  })

  it('without carried state behaves like start() at the entry node', () => {
    const state = startContinuation(story, 'n_two', undefined)
    expect(state.var_state).toEqual({ courage: 1, brave: false })
    expect(state.visit_set).toEqual(['n_two'])
  })
})
