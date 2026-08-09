import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  back,
  canGoBack,
  canSaveBookmark,
  choose,
  currentEndingId,
  deleteBookmark,
  listBookmarks,
  loadBookmark,
  replayRecordedPath,
  saveBookmark,
  start,
  startContinuation,
  visibleChoices,
} from './engine'
import type { ReadingState, Storybook, VarState } from './types'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')

interface Trace {
  name: string
  seed?: VarState
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

const seededStory = corpus.traces.find(
  (t) => t.name === 'seeded_might_carries_into_the_read'
)!.story

function play(story: Storybook, choices: string[], seed?: VarState): ReadingState {
  // Route an unseeded trace through plain start() rather than
  // startContinuation(story, null, undefined): the two are equivalent today,
  // but routing every trace through the continuation path left start()
  // itself uncovered by the conformance corpus, the one suite whose job is
  // to catch exactly this class of divergence between the two.
  let state = seed === undefined ? start(story) : startContinuation(story, null, seed)
  for (const choiceId of choices) {
    state = choose(story, state, choiceId)
  }
  return state
}

describe('player engine cross-implementation conformance', () => {
  it.each(corpus.traces.map((t) => [t.name, t] as const))(
    'reaches the expected state for %s',
    (_name, trace) => {
      const state = play(trace.story, trace.choices, trace.seed)
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

describe('back / canGoBack (go back one page via replay)', () => {
  const lantern = corpus.traces[0].story
  const onceLoop = corpus.traces[2].story

  it('is unavailable at the start node with an empty choice history', () => {
    const state = start(lantern)
    expect(canGoBack(lantern, state)).toBe(false)
    expect(back(lantern, state)).toBeNull()
  })

  it('returns the state of the shorter read after one choice, without mutating the input', () => {
    const state = choose(lantern, start(lantern), 'c_take_lantern')
    const previous = back(lantern, state)
    expect(previous).toEqual(start(lantern))
    // The input state is untouched (engine purity, same contract as choose).
    expect(state.current_node).toBe('n_cave_fork')
    expect(state.path).toEqual(['n_entrance', 'n_cave_fork'])
  })

  it('recomputes once-only on_enter effects by replay, never by reversing', () => {
    // n_room's on_enter inc is once:true, so both the two-step and the
    // one-step read have counter 1; a naive reversal would decrement it.
    const state = choose(onceLoop, start(onceLoop), 'c_again')
    expect(state.var_state).toEqual({ counter: 1 })
    const previous = back(onceLoop, state)
    expect(previous?.current_node).toBe('n_room')
    expect(previous?.path).toEqual(['n_room'])
    expect(previous?.var_state).toEqual({ counter: 1 })
  })

  it('reconstructs the same-target sibling branch actually taken', () => {
    // Both entrance choices target n_cave_fork; only the ignore branch leaves
    // has_lantern false, and the replay must find it despite trying siblings.
    const state = choose(lantern, start(lantern), 'c_ignore_lantern')
    const previous = back(lantern, state)
    expect(previous).toEqual(start(lantern))
  })

  it('carries the live server-revision counter over instead of rewinding it', () => {
    const state = { ...choose(lantern, start(lantern), 'c_take_lantern'), state_revision: 7 }
    expect(back(lantern, state)?.state_revision).toBe(7)
  })

  it('fails closed for a continuation state (path does not begin at start_node)', () => {
    const story: Storybook = {
      schema_version: '2.0',
      id: 's_cont_back',
      version: 1,
      title: 'Continuation Back',
      metadata: {},
      variables: [],
      start_node: 'n_one',
      nodes: [
        {
          id: 'n_one',
          body: 'one',
          is_ending: false,
          choices: [{ id: 'c_a', label: 'On.', target: 'n_two' }],
        },
        {
          id: 'n_two',
          body: 'two',
          is_ending: false,
          choices: [{ id: 'c_b', label: 'On.', target: 'n_three' }],
        },
        { id: 'n_three', body: 'three', is_ending: false, choices: [] },
      ],
    }
    const state = choose(story, startContinuation(story, 'n_two'), 'c_b')
    expect(state.path).toEqual(['n_two', 'n_three'])
    expect(canGoBack(story, state)).toBe(false)
    expect(back(story, state)).toBeNull()
  })

  it('fails closed when no replay of the recorded path reproduces the live state', () => {
    const state = choose(lantern, start(lantern), 'c_take_lantern')
    const forged = { ...state, visit_set: [...state.visit_set, 'n_exit'] }
    expect(canGoBack(lantern, forged)).toBe(false)
    expect(back(lantern, forged)).toBeNull()
  })

  it('offers Go back on a seeded read', () => {
    // Previously replayRecordedPath returned null for any state whose
    // path[0] was not start_node, which is every continuation read. With
    // the seed available the replay is reproducible, so the affordance
    // comes back.
    const live = play(seededStory, ['c_press_on'], { might: 2 })
    expect(replayRecordedPath(seededStory, live, { might: 2 })).not.toBeNull()
  })

  it('still fails closed when the recorded path does not start where it should', () => {
    const live = play(seededStory, ['c_press_on'], { might: 2 })
    const corrupted = { ...live, path: ['n_nowhere', ...live.path.slice(1)] }
    expect(replayRecordedPath(seededStory, corrupted, { might: 2 })).toBeNull()
  })
})

describe('bookmarks (save/load/delete/list save-slots)', () => {
  const lantern = corpus.traces[0].story

  it('saves a snapshot of the current position under a fresh slot id', () => {
    const state = choose(lantern, start(lantern), 'c_take_lantern')
    const withBookmark = saveBookmark(state, 'slot-1', 'Before the fork', '2026-08-09T00:00:00Z')
    expect(withBookmark.save_slots['slot-1']).toEqual({
      current_node: state.current_node,
      var_state: state.var_state,
      visit_set: state.visit_set,
      path: state.path,
      label: 'Before the fork',
      saved_at: '2026-08-09T00:00:00Z',
    })
    // Purity: the live position is unchanged by saving a bookmark of it.
    expect(withBookmark.current_node).toBe(state.current_node)
    expect(withBookmark.path).toEqual(state.path)
  })

  it('does not mutate the input state', () => {
    const state = start(lantern)
    saveBookmark(state, 'slot-1', 'Start', '2026-08-09T00:00:00Z')
    expect(state.save_slots).toEqual({})
  })

  it('lists saved bookmarks newest first', () => {
    let state = saveBookmark(start(lantern), 'slot-1', 'First', '2026-08-09T00:00:00Z')
    state = saveBookmark(state, 'slot-2', 'Second', '2026-08-09T01:00:00Z')
    const listed = listBookmarks(state)
    expect(listed.map((b) => b.id)).toEqual(['slot-2', 'slot-1'])
    expect(listed.map((b) => b.bookmark.label)).toEqual(['Second', 'First'])
  })

  it('excludes a save_slots entry that does not look like a bookmark', () => {
    const state = { ...start(lantern), save_slots: { legacy: { some: 'future-format' } } }
    expect(listBookmarks(state)).toEqual([])
  })

  it('deletes a bookmark by slot id', () => {
    const state = saveBookmark(start(lantern), 'slot-1', 'First', '2026-08-09T00:00:00Z')
    const after = deleteBookmark(state, 'slot-1')
    expect(after.save_slots).toEqual({})
  })

  it('deleting an unknown slot id is a no-op, not an error', () => {
    const state = start(lantern)
    expect(() => deleteBookmark(state, 'does-not-exist')).not.toThrow()
    expect(deleteBookmark(state, 'does-not-exist').save_slots).toEqual({})
  })

  it('loads a bookmark as the new live position, keeping save_slots intact', () => {
    const start_ = start(lantern)
    const afterChoice = choose(lantern, start_, 'c_take_lantern')
    const withBookmark = saveBookmark(afterChoice, 'slot-1', 'Fork', '2026-08-09T00:00:00Z')
    // Keep reading past the bookmark.
    const further = {
      ...withBookmark,
      current_node: 'n_somewhere_else',
      path: [...withBookmark.path, 'n_somewhere_else'],
    }

    const loaded = loadBookmark(further, 'slot-1')

    expect(loaded).not.toBeNull()
    expect(loaded?.current_node).toBe(afterChoice.current_node)
    expect(loaded?.path).toEqual(afterChoice.path)
    expect(loaded?.var_state).toEqual(afterChoice.var_state)
    // save_slots (including this same bookmark) is preserved, not cleared.
    expect(loaded?.save_slots).toEqual(further.save_slots)
    // Server-owned fields carry over from the state loadBookmark was called on.
    expect(loaded?.state_revision).toBe(further.state_revision)
  })

  it('returns null for an unknown slot id instead of throwing', () => {
    const state = start(lantern)
    expect(loadBookmark(state, 'does-not-exist')).toBeNull()
  })

  it('returns null when a save_slots entry exists but is not a well-formed bookmark', () => {
    const state = { ...start(lantern), save_slots: { corrupt: { current_node: 'n_x' } } }
    expect(loadBookmark(state, 'corrupt')).toBeNull()
  })

  it('caps how many bookmarks can be saved', () => {
    let state = start(lantern)
    for (let i = 0; i < 10; i += 1) {
      expect(canSaveBookmark(state)).toBe(true)
      state = saveBookmark(state, `slot-${i}`, `Spot ${i}`, '2026-08-09T00:00:00Z')
    }
    expect(canSaveBookmark(state)).toBe(false)
  })
})
