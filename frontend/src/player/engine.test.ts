import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { choose, currentEndingId, start, visibleChoices } from './engine'
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
})
