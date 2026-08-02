import { describe, expect, it } from 'vitest'
import type { ReadingState, Storybook } from '../player/types'
import { isFlowedBand, readerPositionCount, readerPositionLabel } from './readerProgress'

function node(id: string, choiceCount: number) {
  return {
    id,
    body: '',
    choices: Array.from({ length: choiceCount }, (_, i) => ({
      id: `${id}_c${i}`,
      label: '',
      target: `n${i}`,
    })),
    is_ending: false,
  }
}

function story(nodeCount: number): Storybook {
  return {
    schema_version: '2.0',
    id: 's',
    version: 1,
    title: 'S',
    metadata: {},
    nodes: Array.from({ length: nodeCount }, (_, i) => node(`n${i}`, 1)),
    start_node: 'n0',
    variables: [],
  }
}

function reading(path: string[]): ReadingState {
  return {
    current_node: path[path.length - 1] ?? 'n0',
    var_state: {},
    path,
    visit_set: [...new Set(path)],
    version: 1,
    state_revision: 0,
    save_slots: {},
  }
}

describe('isFlowedBand', () => {
  it('is true for every ADR-026 flowed band', () => {
    expect(isFlowedBand('8-11')).toBe(true)
    expect(isFlowedBand('10-13')).toBe(true)
    expect(isFlowedBand('13-16')).toBe(true)
    expect(isFlowedBand('16+')).toBe(true)
  })

  it('is false for the page bands and treats an unrecognized or missing band as non-flowed', () => {
    expect(isFlowedBand('3-5')).toBe(false)
    expect(isFlowedBand('5-8')).toBe(false)
    expect(isFlowedBand(undefined)).toBe(false)
    expect(isFlowedBand(null)).toBe(false)
    expect(isFlowedBand('not-a-band')).toBe(false)
  })
})

describe('readerPositionCount / readerPositionLabel (W1.2, AL-029)', () => {
  it('counts each page as itself at page bands (undefined band included)', () => {
    expect(readerPositionCount(story(10), reading(['n0']), undefined)).toBe(1)
    expect(readerPositionCount(story(10), reading(['n0', 'n1', 'n2']), '5-8')).toBe(3)
    expect(readerPositionLabel(story(10), reading(['n0', 'n1']), '3-5')).toBe('Page 2')
  })

  it('counts a flowed run as one stop, not one per node', () => {
    // n0 (2 choices, branch) -> n1 (1 choice) -> n2 (1 choice) -> n3 (2 choices):
    // stop 1 is just n0 (a branch is always its own stop), stop 2 flows n1+n2+n3.
    const flowStory: Storybook = {
      ...story(0),
      nodes: [node('n0', 2), node('n1', 1), node('n2', 1), node('n3', 2)],
    }
    expect(readerPositionCount(flowStory, reading(['n0']), '8-11')).toBe(1)
    expect(readerPositionCount(flowStory, reading(['n0', 'n1']), '8-11')).toBe(2)
    expect(readerPositionCount(flowStory, reading(['n0', 'n1', 'n2']), '8-11')).toBe(2)
    expect(readerPositionCount(flowStory, reading(['n0', 'n1', 'n2', 'n3']), '10-13')).toBe(2)
    expect(readerPositionLabel(flowStory, reading(['n0', 'n1', 'n2', 'n3']), '10-13')).toBe(
      'Page 2'
    )
  })

  it('starts a fresh stop at every branch, even back-to-back ones', () => {
    const allBranches: Storybook = {
      ...story(0),
      nodes: [node('n0', 2), node('n1', 2), node('n2', 2)],
    }
    expect(readerPositionCount(allBranches, reading(['n0', 'n1', 'n2']), '13-16')).toBe(3)
  })

  it('never returns less than 1, even for a degenerate empty path', () => {
    expect(readerPositionCount(story(3), reading([]), undefined)).toBe(1)
    expect(readerPositionCount(story(3), reading([]), '16+')).toBe(1)
  })
})
