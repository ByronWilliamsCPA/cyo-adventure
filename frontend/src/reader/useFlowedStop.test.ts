/**
 * UW-F38 regression cover for `useFlowedStop`'s silent-advance side effect.
 *
 * The hook walks the engine through a flowed stop's single-choice hops by
 * sending the same public CHOOSE event a tap would send, so the hops' effects
 * and visit_set entries apply for real (ADR-026 decision 2). Since
 * `composeStopWithHistory`, a stop's `nodeIds` can BEGIN with hops the engine
 * already took on an earlier mount and then persisted, so "walk every hop in
 * the stop" is no longer the same thing as "walk the hops that still need
 * taking". These tests pin that distinction, which is invisible to the stop
 * composition tests in `player/stops.test.ts`.
 */

import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { choose, start } from '../player/engine'
import type { ReadingState, Storybook } from '../player/types'

import { useFlowedStop } from './useFlowedStop'

// n_start branches; n_a has the single choice that flows into n_mid's branch.
// A stop entered at n_a is therefore ['n_a', 'n_mid'] with exactly one hop.
const story: Storybook = {
  schema_version: '2.0',
  id: 's_flow',
  version: 1,
  title: 'Flow',
  metadata: {},
  variables: [],
  start_node: 'n_start',
  nodes: [
    {
      id: 'n_start',
      body: 'A fork.',
      is_ending: false,
      choices: [
        { id: 'c_a', label: 'Left', target: 'n_a' },
        { id: 'c_b', label: 'Right', target: 'n_end' },
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
        { id: 'c_x', label: 'Up', target: 'n_end' },
        { id: 'c_y', label: 'Down', target: 'n_end' },
      ],
    },
    {
      id: 'n_end',
      body: 'The end.',
      is_ending: true,
      choices: [],
      ending: { id: 'e', valence: 'positive', kind: 'success', title: 'Done' },
    },
  ],
}

/** A freshly tapped stop origin: the engine sits at n_a and the n_a -> n_mid
 * hop has NOT been taken yet. */
function freshOrigin(): ReadingState {
  return choose(story, start(story), 'c_a')
}

/** What storage holds after that same stop was rendered once and its hop
 * applied: the engine sits at the terminal, n_mid. */
function resumedTerminal(): ReadingState {
  return choose(story, freshOrigin(), 'c_go')
}

describe('useFlowedStop silent advance', () => {
  it('sends CHOOSE for each un-taken hop on a freshly entered stop', () => {
    const send = vi.fn()
    const reading = freshOrigin()
    const { result } = renderHook(() => useFlowedStop(story, reading, send, true))

    expect(result.current.stop?.nodeIds).toEqual(['n_a', 'n_mid'])
    expect(send).toHaveBeenCalledTimes(1)
    expect(send).toHaveBeenCalledWith({ type: 'CHOOSE', choiceId: 'c_go' })
  })

  it('sends no CHOOSE when the stop was reconstructed from a resumed terminal', () => {
    const send = vi.fn()
    const reading = resumedTerminal()
    const { result } = renderHook(() => useFlowedStop(story, reading, send, true))

    // The full stop is on screen, so the child reads n_a's prose again...
    expect(result.current.stop?.nodeIds).toEqual(['n_a', 'n_mid'])
    expect(result.current.stop?.originNode).toBe('n_a')
    // ...but the engine is already past that hop, and re-sending it would
    // re-apply n_mid's on_enter effects and walk the engine past the choice
    // the child is looking at. This is the assertion UW-F38's fix turns on.
    expect(send).not.toHaveBeenCalled()
  })

  it('sends nothing at a plain branch stop', () => {
    const send = vi.fn()
    const reading = start(story)
    const { result } = renderHook(() => useFlowedStop(story, reading, send, true))

    expect(result.current.stop?.nodeIds).toEqual(['n_start'])
    expect(send).not.toHaveBeenCalled()
  })

  it('composes no stop at all at a page band', () => {
    const send = vi.fn()
    const reading = freshOrigin()
    const { result } = renderHook(() => useFlowedStop(story, reading, send, false))

    expect(result.current.stop).toBeNull()
    expect(result.current.originReading).toBeNull()
    expect(send).not.toHaveBeenCalled()
  })
})
