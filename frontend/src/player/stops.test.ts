import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { choose, currentEndingId, start, visibleChoices } from './engine'
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
