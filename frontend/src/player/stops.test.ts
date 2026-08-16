import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { choose, currentEndingId, start, startContinuation, visibleChoices } from './engine'
import {
  backOneStop,
  canGoBackOneStop,
  composeStop,
  composeStopWithHistory,
  flowedPrefix,
} from './stops'
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

// ---------------------------------------------------------------------------
// UW-F38: resuming a flowed stop from its persisted terminal.
//
// A flowed run persists its TERMINAL (ADR-026 decision 2 applies each hop's
// effects for real), so a resumed read hands composition a state mid-stop.
// composeStop walks forward only and cannot see the prefix, so the stop
// collapsed to length 1: the flowed prose vanished and backOneStop rewound
// into the middle of the flow instead of to the previous stop's terminal.
// ---------------------------------------------------------------------------

/** A reading state as it comes back from storage: a position plus the path
 * that reached it, with no in-memory composition history. */
function resumedAt(currentNode: string, nodePath: string[], varState: VarState = {}): ReadingState {
  return {
    current_node: currentNode,
    var_state: varState,
    path: nodePath,
    visit_set: [...nodePath],
    version: 1,
    state_revision: 1,
    save_slots: {},
  }
}

/** The state storage really holds after the child tapped c_a at n_start and
 * the flowed run walked n_a -> n_mid: produced by the engine, so its path,
 * visit_set and var_state are all internally consistent and `back()` can
 * replay it (a hand-built var_state cannot, and back() fails closed). */
function playedToFlowedTerminal(): ReadingState {
  return choose(seededFlowStory, choose(seededFlowStory, start(seededFlowStory), 'c_a'), 'c_go')
}

describe('composeStopWithHistory (UW-F38)', () => {
  it('reconstructs the flowed prefix when resuming at a stop terminal', () => {
    const resumed = playedToFlowedTerminal()
    expect(resumed.current_node).toBe('n_mid')
    expect(resumed.path).toEqual(['n_start', 'n_a', 'n_mid'])

    // What the bug looked like: forward-only composition sees one node.
    expect(composeStop(seededFlowStory, resumed).nodeIds).toEqual(['n_mid'])

    const stop = composeStopWithHistory(seededFlowStory, resumed)
    expect(stop.nodeIds).toEqual(['n_a', 'n_mid'])
    expect(stop.originNode).toBe('n_a')
    // Forward results are composeStop's, untouched.
    expect(stop.terminalReason).toBe('branch')
    expect(stop.state.current_node).toBe('n_mid')
  })

  it('rewinds a resumed stop to the previous stop terminal, not into its own flow', () => {
    const stop = composeStopWithHistory(seededFlowStory, playedToFlowedTerminal())
    // backOneStop calls back() once per node in the stop; with the prefix
    // restored that is 2, landing on n_start. Truncated to ['n_mid'] it was
    // 1, landing mid-flow on n_a.
    expect(backOneStop(seededFlowStory, stop)?.current_node).toBe('n_start')
  })

  it('stops the walk-back at a branch, never crossing into the previous stop', () => {
    // n_start offers two choices, so it terminated the PREVIOUS stop and must
    // not be absorbed into this one.
    expect(flowedPrefix(seededFlowStory, resumedAt('n_mid', ['n_start', 'n_a', 'n_mid']))).toEqual([
      'n_a',
    ])
  })

  it('adds nothing on a genuine tap origin, matching composeStop exactly', () => {
    const origin = choose(seededFlowStory, start(seededFlowStory), 'c_a')
    const plain = composeStop(seededFlowStory, origin)
    const withHistory = composeStopWithHistory(seededFlowStory, origin)
    expect(withHistory.nodeIds).toEqual(plain.nodeIds)
    expect(withHistory.originNode).toBe(plain.originNode)
  })

  it('adds nothing at the first node of a read', () => {
    expect(flowedPrefix(seededFlowStory, start(seededFlowStory))).toEqual([])
  })

  it('ends a resumed cycle where it originally ended, without repeating a node', () => {
    // A two-node cycle: n_a's only choice targets n_b, n_b's only choice
    // targets n_a. Composed fresh from n_a the stop is [n_a, n_b], closing on
    // the loop guard; it is persisted at its terminal, n_b.
    const cycle: Storybook = {
      schema_version: '2.0',
      id: 's_cycle',
      version: 1,
      title: 'Cycle',
      metadata: {},
      variables: [],
      start_node: 'n_a',
      nodes: [
        {
          id: 'n_a',
          body: 'Around again.',
          is_ending: false,
          choices: [{ id: 'c_ab', label: 'On', target: 'n_b' }],
        },
        {
          id: 'n_b',
          body: 'And back.',
          is_ending: false,
          choices: [{ id: 'c_ba', label: 'Back', target: 'n_a' }],
        },
      ],
    }
    const fresh = composeStop(cycle, start(cycle))
    expect(fresh.nodeIds).toEqual(['n_a', 'n_b'])
    expect(fresh.terminalReason).toBe('loop')

    // Resuming at that terminal must reproduce the SAME stop. Without the
    // prefix participating in loop detection the forward pass retakes
    // n_b -> n_a and returns [n_a, n_b, n_a]: the node's prose renders twice
    // and backOneStop calls back() three times instead of two.
    const resumed = resumedAt('n_b', ['n_a', 'n_b'])
    const stop = composeStopWithHistory(cycle, resumed)
    expect(stop.nodeIds).toEqual(['n_a', 'n_b'])
    expect(stop.originNode).toBe('n_a')
    expect(new Set(stop.nodeIds).size).toBe(stop.nodeIds.length)
    // The engine is already at the terminal, so nothing remains to walk.
    expect(stop.state.current_node).toBe('n_b')
  })

  it('fails closed when the path does not end where the state says it is', () => {
    // A truncated or foreign path describes some other position, so nothing
    // may be inferred from it; the result is today's behavior, not a guess.
    expect(flowedPrefix(seededFlowStory, resumedAt('n_mid', ['n_start', 'n_a']))).toEqual([])
    expect(flowedPrefix(seededFlowStory, resumedAt('n_mid', []))).toEqual([])
  })

  it('infers nothing when the state was recorded against a different story version', () => {
    // Greptile flagged this on PR #724: ReaderPage keys reading state on
    // (profileId, storybookId) with no version, while loading the story at a
    // route-selected version, so a republish can pair a path with a topology
    // it never described. The structural guards would still refuse a missing
    // edge, but a republish that happens to preserve this single-choice edge
    // would let the stale path look walkable.
    const resumed = { ...playedToFlowedTerminal(), version: 2 }
    expect(seededFlowStory.version).toBe(1)
    expect(flowedPrefix(seededFlowStory, resumed)).toEqual([])
    // ...and the composed stop falls back to forward-only, which is exactly
    // the pre-reconstruction behavior rather than a wrong one.
    expect(composeStopWithHistory(seededFlowStory, resumed).nodeIds).toEqual(['n_mid'])
  })

  it('infers nothing for a state carrying no usable version', () => {
    // A legacy or hand-built row reads 0 and must not be treated as matching.
    const resumed = { ...playedToFlowedTerminal(), version: 0 }
    expect(flowedPrefix(seededFlowStory, resumed)).toEqual([])
  })

  it('fails closed on an unknown node in the recorded path', () => {
    expect(flowedPrefix(seededFlowStory, resumedAt('n_mid', ['n_gone', 'n_mid']))).toEqual([])
  })

  it('stops at a repeat rather than walking a cycle in the path', () => {
    // A path that revisits the stop's own terminal is the cycle composeStop's
    // loop guard refuses to walk; the walk-back refuses it symmetrically.
    expect(flowedPrefix(seededFlowStory, resumedAt('n_mid', ['n_mid', 'n_a', 'n_mid']))).toEqual([
      'n_a',
    ])
  })
})
