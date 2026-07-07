import { describe, expect, it } from 'vitest'
import type { ReadingState, Storybook } from '../player/types'
import { readerProgressLabel, readerProgressPercent } from './readerProgress'

function story(nodeCount: number): Storybook {
  return {
    schema_version: '2.0',
    id: 's',
    version: 1,
    title: 'S',
    metadata: {},
    nodes: Array.from({ length: nodeCount }, (_, i) => ({
      id: `n${i}`,
      body: '',
      choices: [],
      is_ending: false,
    })),
    start_node: 'n0',
    variables: [],
  }
}

function reading(visited: number): ReadingState {
  return {
    current_node: 'n0',
    var_state: {},
    path: [],
    visit_set: Array.from({ length: visited }, (_, i) => `n${i}`),
    version: 1,
    state_revision: 0,
    save_slots: {},
  }
}

describe('readerProgress', () => {
  it('computes clamped percent of visited nodes', () => {
    expect(readerProgressPercent(story(10), reading(3))).toBe(30)
    expect(readerProgressPercent(story(10), reading(20))).toBe(100)
  })

  it('returns 0 when the story has no nodes', () => {
    expect(readerProgressPercent(story(0), reading(0))).toBe(0)
  })

  it('formats a pages-explored label matching the library wording', () => {
    expect(readerProgressLabel(story(14), reading(2))).toBe('2 of 14 pages explored')
  })

  it('clamps the label so a stale visit_set cannot exceed the total', () => {
    expect(readerProgressLabel(story(10), reading(20))).toBe('10 of 10 pages explored')
  })
})
