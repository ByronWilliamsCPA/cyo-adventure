import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { back, choose, start, startContinuation } from '../player/engine'
import type { ReadingState, Storybook } from '../player/types'
import { runStory } from '../test/runStory'
import { findLatestFork } from './rewindToFork'

const here = path.dirname(fileURLToPath(import.meta.url))
const lantern = (
  JSON.parse(
    readFileSync(path.resolve(here, '../../../schema/conformance/player_traces.json'), 'utf-8')
  ) as { traces: { story: Storybook }[] }
).traces[0].story

function play(story: Storybook, choiceIds: string[], from?: ReadingState): ReadingState {
  return choiceIds.reduce((state, id) => choose(story, state, id), from ?? start(story))
}

function rewind(story: Storybook, state: ReadingState, steps: number): ReadingState {
  let current = state
  for (let i = 0; i < steps; i += 1) {
    const previous = back(story, current)
    if (previous === null) throw new Error('back() refused mid-rewind')
    current = previous
  }
  return current
}

describe('findLatestFork', () => {
  it('skips a single-choice run before the ending and lands on the fork', () => {
    const ended = play(runStory, ['c_go', 'c_left', 'c_a1', 'c_a2'])
    const fork = findLatestFork(runStory, ended)
    expect(fork).toEqual({ steps: 3, nodeId: 'n_fork', previousChoiceId: 'c_left' })
    // Applying it through back() reproduces the state the child had at the
    // fork, effects included: the corridor's +1s are undone.
    const landed = rewind(runStory, ended, fork?.steps ?? 0)
    expect(landed).toEqual(
      expect.objectContaining({
        current_node: 'n_fork',
        path: ['n_intro', 'n_fork'],
        var_state: { steps: 0 },
      })
    )
    expect(landed.visit_set).not.toContain('n_a1')
  })

  it('returns null when no earlier point offered two or more choices', () => {
    const atFirst = start(runStory)
    expect(findLatestFork(runStory, atFirst)).toBeNull()
    const linear = play(runStory, ['c_go'])
    expect(findLatestFork(runStory, linear)).toBeNull()
  })

  it('counts only visible choices: a fork whose second choice was hidden is skipped', () => {
    // Ignoring the lantern hides c_dark_passage at n_cave_fork, so that node
    // offered one choice on this path; the real decision was n_entrance.
    const ended = play(lantern, ['c_ignore_lantern', 'c_bright_tunnel'])
    const fork = findLatestFork(lantern, ended)
    expect(fork?.nodeId).toBe('n_entrance')
    expect(fork?.steps).toBe(2)
  })

  it('treats the same node as a fork when its conditional choice was visible', () => {
    const ended = play(lantern, ['c_take_lantern', 'c_bright_tunnel'])
    expect(findLatestFork(lantern, ended)).toEqual({
      steps: 1,
      nodeId: 'n_cave_fork',
      previousChoiceId: 'c_bright_tunnel',
    })
  })

  it('names the previous choice only when the replay can tell siblings apart', () => {
    // c_take_lantern and c_ignore_lantern share a target but differ in
    // effects, so the one taken is recoverable.
    const ended = play(lantern, ['c_ignore_lantern', 'c_bright_tunnel'])
    expect(findLatestFork(lantern, ended)?.previousChoiceId).toBe('c_ignore_lantern')
  })

  it('fails closed for a continuation read, matching Go back', () => {
    const entered = startContinuation(runStory, 'n_fork', {})
    const ended = play(runStory, ['c_left', 'c_a1', 'c_a2'], entered)
    expect(findLatestFork(runStory, ended)).toBeNull()
  })

  it('returns null on a seeded read when the seed is not forwarded', () => {
    const seed = { steps: 5 }
    const seeded = startContinuation(runStory, null, seed)
    const ended = play(runStory, ['c_go', 'c_left', 'c_a1', 'c_a2'], seeded)
    expect(findLatestFork(runStory, ended)).toBeNull()
    expect(findLatestFork(runStory, ended, seed)?.nodeId).toBe('n_fork')
  })
})
