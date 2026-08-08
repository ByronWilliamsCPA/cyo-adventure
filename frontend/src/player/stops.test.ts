import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { choose, currentEndingId, start, startContinuation, visibleChoices } from './engine'
import { backOneStop, canGoBackOneStop, composeStop } from './stops'
import type { Stop, StopTerminalReason } from './stops'
import type { ReadingState, Storybook, VarState } from './types'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/stop_traces.json')

interface StopExpectation {
  origin_node: string
  node_ids: string[]
  terminal_reason: StopTerminalReason
  current_node: string
  var_state: VarState
  visit_set: string[]
  ending_id: string | null
  visible_choice_ids: string[]
}

interface StopCase {
  name: string
  prefix_choices: string[]
  expected: StopExpectation
  back_check?: { prefix_choices: string[]; expected: StopExpectation }
  story: Storybook
}

const corpus = JSON.parse(readFileSync(tracesPath, 'utf-8')) as { cases: StopCase[] }

function reachOrigin(story: Storybook, prefixChoices: string[]): ReadingState {
  let state = start(story)
  for (const choiceId of prefixChoices) {
    state = choose(story, state, choiceId)
  }
  return state
}

function assertStopMatches(story: Storybook, stop: Stop, expected: StopExpectation): void {
  expect(stop.originNode).toBe(expected.origin_node)
  expect(stop.nodeIds).toEqual(expected.node_ids)
  expect(stop.terminalReason).toBe(expected.terminal_reason)
  expect(stop.state.current_node).toBe(expected.current_node)
  expect(stop.state.var_state).toEqual(expected.var_state)
  expect([...stop.state.visit_set].sort()).toEqual([...expected.visit_set].sort())
  expect(currentEndingId(story, stop.state)).toBe(expected.ending_id)
  const visible = visibleChoices(story, stop.state).map((c) => c.id)
  expect(visible).toEqual(expected.visible_choice_ids)
}

describe('stop composition cross-implementation conformance', () => {
  it.each(corpus.cases.map((c) => [c.name, c] as const))(
    'composes the expected stop for %s',
    (_name, testCase) => {
      const origin = reachOrigin(testCase.story, testCase.prefix_choices)
      const stop = composeStop(testCase.story, origin)
      assertStopMatches(testCase.story, stop, testCase.expected)
    }
  )
})

describe('go-back-by-stop (backOneStop)', () => {
  const backCases = corpus.cases.filter(
    (c): c is StopCase & { back_check: NonNullable<StopCase['back_check']> } =>
      c.back_check !== undefined
  )

  it.each(backCases.map((c) => [c.name, c] as const))(
    'rewinds from %s to the previous stop terminal',
    (_name, testCase) => {
      const origin = reachOrigin(testCase.story, testCase.prefix_choices)
      const stop = composeStop(testCase.story, origin)

      expect(canGoBackOneStop(testCase.story, stop)).toBe(true)
      const previous = backOneStop(testCase.story, stop)
      expect(previous).not.toBeNull()
      // The rewound state must match the previous stop's own composed
      // terminal state exactly: same current_node, var_state, and visit_set.
      const expected = testCase.back_check.expected
      expect(previous?.current_node).toBe(expected.current_node)
      expect(previous?.var_state).toEqual(expected.var_state)
      expect([...(previous?.visit_set ?? [])].sort()).toEqual([...expected.visit_set].sort())
    }
  )

  it('is unavailable from the very first stop (nothing precedes start_node)', () => {
    const flowCase = corpus.cases.find((c) => c.name === 'flow_effects_in_order_to_branch')
    if (!flowCase) throw new Error('fixture missing: flow_effects_in_order_to_branch')
    const origin = reachOrigin(flowCase.story, flowCase.prefix_choices)
    const stop = composeStop(flowCase.story, origin)
    expect(stop.originNode).toBe(flowCase.story.start_node)
    expect(canGoBackOneStop(flowCase.story, stop)).toBe(false)
    expect(backOneStop(flowCase.story, stop)).toBeNull()
  })
})

describe('composeStop behaviour', () => {
  it('does not mutate the input state', () => {
    const flowCase = corpus.cases.find((c) => c.name === 'flow_effects_in_order_to_branch')
    if (!flowCase) throw new Error('fixture missing: flow_effects_in_order_to_branch')
    const origin = start(flowCase.story)
    const snapshotNode = origin.current_node
    const snapshotPath = [...origin.path]
    composeStop(flowCase.story, origin)
    expect(origin.current_node).toBe(snapshotNode)
    expect(origin.path).toEqual(snapshotPath)
  })

  it('terminates a single-choice cycle inside one composed stop (#CRITICAL loop guard)', () => {
    const loopCase = corpus.cases.find((c) => c.name === 'loop_back_ends_stop')
    if (!loopCase) throw new Error('fixture missing: loop_back_ends_stop')
    const origin = start(loopCase.story)
    const stop = composeStop(loopCase.story, origin)
    expect(stop.terminalReason).toBe('loop')
    expect(stop.nodeIds).toEqual(['n_p', 'n_q'])
  })
})

// A hand-written fixture (the shared conformance corpus has no seeded case,
// and go-back-by-stop is frontend-only so nothing there mirrors it): stop 1
// is the lone branch at n_start, stop 2 flows n_a into n_mid's branch, and
// `might` is a declared int the seed moves off its initial.
const seededFlowStory: Storybook = {
  schema_version: '2.0',
  id: 's_seeded_stop',
  version: 1,
  title: 'Seeded Stop',
  metadata: {},
  variables: [{ name: 'might', type: 'int', initial: 0, min: 0, max: 5 }],
  start_node: 'n_start',
  nodes: [
    {
      id: 'n_start',
      body: 'A fork.',
      is_ending: false,
      choices: [
        { id: 'c_a', label: 'Left', target: 'n_a' },
        { id: 'c_b', label: 'Right', target: 'n_b' },
      ],
    },
    {
      id: 'n_a',
      body: 'A corridor.',
      is_ending: false,
      choices: [{ id: 'c_go', label: 'On', target: 'n_mid' }],
    },
    {
      id: 'n_mid',
      body: 'A junction.',
      is_ending: false,
      choices: [
        { id: 'c_x', label: 'Up', target: 'n_b' },
        { id: 'c_y', label: 'Down', target: 'n_b' },
      ],
    },
    {
      id: 'n_b',
      body: 'The end.',
      is_ending: true,
      choices: [],
      ending: { id: 'e_b', valence: 'positive', kind: 'success', title: 'Done' },
    },
  ],
}

describe('go-back-by-stop on a seeded read (ADR-028 Task 9)', () => {
  it('rewinds a stop on a seeded read only when the seed is forwarded', () => {
    const seed: VarState = { might: 3 }
    const origin = choose(seededFlowStory, startContinuation(seededFlowStory, null, seed), 'c_a')
    const stop = composeStop(seededFlowStory, origin)
    expect(stop.nodeIds).toEqual(['n_a', 'n_mid'])

    // Forwarded: every back() call replays from the SEEDED start, reproduces
    // the live var_state, and the rewind lands on the previous stop's
    // terminal node.
    expect(canGoBackOneStop(seededFlowStory, stop, seed)).toBe(true)
    expect(backOneStop(seededFlowStory, stop, seed)?.current_node).toBe('n_start')

    // Dropped: back() replays from the declared initials (might 0), which can
    // never reproduce a live might of 3, so it fails closed. Two callers
    // disagreeing about the seed is exactly the reader defect this parameter
    // exists to prevent, so the two answers must be allowed to differ here
    // and must never differ between Reader.tsx and machine.ts.
    expect(canGoBackOneStop(seededFlowStory, stop)).toBe(false)
    expect(backOneStop(seededFlowStory, stop)).toBeNull()
  })
})
