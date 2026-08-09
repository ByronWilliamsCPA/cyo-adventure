import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { createActor } from 'xstate'
import { describe, expect, it, vi } from 'vitest'

import { choose, startContinuation } from './engine'
import { readerMachine } from './machine'
import type { ContinuationSeed } from './series'
import type { Storybook } from './types'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const traces = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { name: string; story: Storybook }[]
  }
).traces
const lantern = traces[0].story
const seededStory = traces.find((t) => t.name === 'seeded_might_carries_into_the_read')!.story

describe('reader machine', () => {
  it('starts in the reading state at the start node', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    expect(actor.getSnapshot().value).toBe('reading')
    expect(actor.getSnapshot().context.reading.current_node).toBe('n_entrance')
  })

  it('transitions to ended when a choice reaches an ending node', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
    expect(actor.getSnapshot().value).toBe('reading')
    actor.send({ type: 'CHOOSE', choiceId: 'c_bright_tunnel' })
    expect(actor.getSnapshot().value).toBe('ended')
    expect(actor.getSnapshot().context.reading.current_node).toBe('n_exit')
  })

  it('restarts back to the start node', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_bright_tunnel' })
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().value).toBe('reading')
    expect(actor.getSnapshot().context.reading.current_node).toBe('n_entrance')
  })

  it('RESTART preserves the seed rather than fabricating declared initials', () => {
    // #460: a continuation read restarted with start() re-derives
    // might=0 from the declared initial, discarding the value the child
    // actually carried in. The reader has no way back to it.
    const actor = createActor(readerMachine, {
      input: { story: seededStory, seed: { might: 2 } },
    }).start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_press_on' })
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().context.reading.var_state.might).toBe(2)
  })

  it('RESTART with no seed still starts from declared initials', () => {
    const actor = createActor(readerMachine, { input: { story: seededStory } }).start()
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().context.reading.var_state.might).toBe(0)
  })
})

describe('reader machine BACK', () => {
  // A three-node trail where both the choice effects and the on_enter effects
  // move variables, so a BACK that merely "reversed" the last step (instead of
  // replaying the shorter path) would leave the wrong var_state behind.
  const trail: Storybook = {
    schema_version: '2.0',
    id: 's_trail',
    version: 1,
    title: 'Trail',
    metadata: {},
    variables: [
      { name: 'torch', type: 'bool', initial: false },
      { name: 'coins', type: 'int', initial: 0, min: 0, max: 9 },
    ],
    start_node: 'n_camp',
    nodes: [
      {
        id: 'n_camp',
        body: 'camp',
        is_ending: false,
        choices: [
          {
            id: 'c_torch',
            label: 'Take the torch.',
            target: 'n_woods',
            effects: [{ op: 'set', var: 'torch', value: true }],
          },
        ],
      },
      {
        id: 'n_woods',
        body: 'woods',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'coins', value: 1 }],
        choices: [
          {
            id: 'c_river',
            label: 'Cross the river.',
            target: 'n_river',
            effects: [{ op: 'inc', var: 'coins', value: 2 }],
          },
        ],
      },
      {
        id: 'n_river',
        body: 'river',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'coins', value: 1 }],
        choices: [],
      },
    ],
  }

  it('is a no-op at the start node with an empty choice history', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    const before = actor.getSnapshot().context.reading
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('reading')
    expect(actor.getSnapshot().context.reading).toBe(before)
  })

  it('after two choices lands on the node after the first choice with replayed variables', () => {
    const actor = createActor(readerMachine, { input: { story: trail } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_torch' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_river' })
    expect(actor.getSnapshot().context.reading.var_state).toEqual({ torch: true, coins: 4 })
    actor.send({ type: 'BACK' })
    const { reading } = actor.getSnapshot().context
    expect(reading.current_node).toBe('n_woods')
    expect(reading.path).toEqual(['n_camp', 'n_woods'])
    // Replayed, not reversed: coins is back to the single n_woods on_enter
    // increment, and the choice/on_enter effects of the undone step are gone.
    expect(reading.var_state).toEqual({ torch: true, coins: 1 })
    expect(reading.visit_set).toEqual(['n_camp', 'n_woods'])
  })

  it('from an ending returns into the story one step earlier', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_take_lantern' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_dark_passage' })
    expect(actor.getSnapshot().value).toBe('ended')
    actor.send({ type: 'BACK' })
    const snapshot = actor.getSnapshot()
    expect(snapshot.value).toBe('reading')
    expect(snapshot.context.reading.current_node).toBe('n_cave_fork')
    expect(snapshot.context.reading.var_state).toEqual({ has_lantern: true })
  })

  it('replays the branch actually taken when a same-target sibling choice exists', () => {
    // n_entrance offers two choices to n_cave_fork with different effects; the
    // replay must reconstruct the ignore-lantern branch, not the take branch.
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
    actor.send({ type: 'BACK' })
    const { reading } = actor.getSnapshot().context
    expect(reading.current_node).toBe('n_entrance')
    expect(reading.path).toEqual(['n_entrance'])
    expect(reading.var_state).toEqual({ has_lantern: false })
  })

  it('leaves RESTART working after a BACK', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_take_lantern' })
    actor.send({ type: 'BACK' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_bright_tunnel' })
    expect(actor.getSnapshot().value).toBe('ended')
    actor.send({ type: 'RESTART' })
    const snapshot = actor.getSnapshot()
    expect(snapshot.value).toBe('reading')
    expect(snapshot.context.reading.current_node).toBe('n_entrance')
    expect(snapshot.context.reading.var_state).toEqual({ has_lantern: false })
    expect(snapshot.context.reading.path).toEqual(['n_entrance'])
  })
})

describe('reader machine error recovery', () => {
  // engine.ts's choose() throws by contract on a structurally invalid choice
  // (dangling target, corrupted cached state). XState's actor runtime catches
  // any throw from inside an assign() action internally and permanently stops
  // the actor before it would ever reach a caller's try/catch around send();
  // applyChoice (machine.ts) must therefore catch it itself and surface
  // context.error, leaving the actor alive and still able to transition.
  it('surfaces context.error instead of dying when a choice does not exist on the node', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      actor.send({ type: 'CHOOSE', choiceId: 'c_does_not_exist' })
      const snapshot = actor.getSnapshot()
      expect(snapshot.status).toBe('active')
      expect(snapshot.value).toBe('reading')
      expect(snapshot.context.error).toBe(true)
      // Unchanged: the failed transition must not have moved the reading state.
      expect(snapshot.context.reading.current_node).toBe('n_entrance')
    } finally {
      logSpy.mockRestore()
    }
  })

  it('stays usable after a failed choice: a valid choice still works', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      actor.send({ type: 'CHOOSE', choiceId: 'c_does_not_exist' })
      actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
      const snapshot = actor.getSnapshot()
      expect(snapshot.context.error).toBe(false)
      expect(snapshot.context.reading.current_node).not.toBe('n_entrance')
    } finally {
      logSpy.mockRestore()
    }
  })

  it('clears context.error on RESTART', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      actor.send({ type: 'CHOOSE', choiceId: 'c_does_not_exist' })
      expect(actor.getSnapshot().context.error).toBe(true)
      actor.send({ type: 'RESTART' })
      const snapshot = actor.getSnapshot()
      expect(snapshot.context.error).toBe(false)
      expect(snapshot.context.reading.current_node).toBe('n_entrance')
    } finally {
      logSpy.mockRestore()
    }
  })

  // start() throws by the same contract as choose()/back() when start_node is
  // dangling. It has no prior reading state to fall back on, so both the
  // initial-context factory and reset (RESTART) must surface context.error
  // instead of letting the throw escape (a synchronous render-time crash for
  // the factory, an actor-killing assign() throw for reset).
  const corrupted: Storybook = { ...lantern, start_node: 'n_does_not_exist' }

  it('surfaces context.error instead of crashing when start_node is dangling', () => {
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const actor = createActor(readerMachine, { input: { story: corrupted } })
      actor.start()
      const snapshot = actor.getSnapshot()
      expect(snapshot.status).toBe('active')
      expect(snapshot.context.error).toBe(true)
    } finally {
      logSpy.mockRestore()
    }
  })

  it('stays alive on RESTART even when the same dangling start_node fails again', () => {
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const actor = createActor(readerMachine, { input: { story: corrupted } })
      actor.start()
      actor.send({ type: 'RESTART' })
      const snapshot = actor.getSnapshot()
      expect(snapshot.status).toBe('active')
      expect(snapshot.context.error).toBe(true)
    } finally {
      logSpy.mockRestore()
    }
  })
})

describe('reader machine RESTART on a continuation read (issue #460)', () => {
  // Book 2 of a series: every declared initial CONTRADICTS the value the
  // child carries in, so a restart that fell back to start() would be visible
  // in var_state as well as in current_node.
  const book2: Storybook = {
    schema_version: '2.0',
    id: 's_book2',
    version: 1,
    title: 'Book Two',
    metadata: {
      series: {
        series_id: 's_saga',
        book_index: 2,
        series_entry_node: 'n_woods',
        carries_state: true,
      },
    },
    variables: [
      { name: 'torch', type: 'bool', initial: false },
      { name: 'coins', type: 'int', initial: 0, min: 0, max: 9 },
    ],
    start_node: 'n_camp',
    nodes: [
      {
        id: 'n_camp',
        body: 'the prologue a continuation read is meant to skip',
        is_ending: false,
        choices: [{ id: 'c_torch', label: 'Take the torch.', target: 'n_woods' }],
      },
      {
        id: 'n_woods',
        body: 'woods',
        is_ending: false,
        on_enter: [{ op: 'inc', var: 'coins', value: 1 }],
        choices: [{ id: 'c_river', label: 'Cross the river.', target: 'n_river' }],
      },
      { id: 'n_river', body: 'river', is_ending: true, choices: [] },
    ],
  }
  const seed: ContinuationSeed = { entryNode: 'n_woods', varState: { torch: true, coins: 4 } }
  // What startContinuation produces from `seed`: declared initials overlaid
  // with the carried pair, then n_woods's on_enter increment on top.
  const carried = { torch: true, coins: 5 }

  it('returns to the entry node with carried variables, not to start_node with declared initials', () => {
    const actor = createActor(readerMachine, {
      input: {
        story: book2,
        reading: startContinuation(book2, seed.entryNode, seed.varState),
        continuation: seed,
      },
    })
    actor.start()
    expect(actor.getSnapshot().context.reading.var_state).toEqual(carried)
    actor.send({ type: 'CHOOSE', choiceId: 'c_river' })
    expect(actor.getSnapshot().value).toBe('ended')
    actor.send({ type: 'RESTART' })
    const { reading } = actor.getSnapshot().context
    expect(actor.getSnapshot().value).toBe('reading')
    expect(reading.current_node).toBe('n_woods')
    expect(reading.path).toEqual(['n_woods'])
    expect(reading.var_state).toEqual(carried)

    // The seed is provenance, not a one-shot token: `reset` reads it without
    // clearing it, so a second RESTART must reproduce the same continuation
    // start rather than decaying to the new-reader path.
    actor.send({ type: 'RESTART' })
    const again = actor.getSnapshot().context.reading
    expect(again.current_node).toBe('n_woods')
    expect(again.path).toEqual(['n_woods'])
    expect(again.var_state).toEqual(carried)
  })

  it('restarts to the continuation entry point even when the read resumed from saved progress', () => {
    // The seed is ignored for the INITIAL state whenever saved progress exists
    // (ReaderPage's rule), but the carried series state is a fact about the
    // child's history, so a restart must still honour it.
    // Built by actually taking the choice rather than by overriding
    // current_node, so the fixture keeps the invariant the server enforces on
    // saved progress (player/replay.py::_check_structure: current_node ===
    // path[path.length - 1]). A hand-patched current_node is a state no save
    // path could ever have produced.
    const saved = choose(
      book2,
      startContinuation(book2, 'n_woods', { torch: true, coins: 4 }),
      'c_river'
    )
    const actor = createActor(readerMachine, {
      input: { story: book2, reading: saved, continuation: seed },
    })
    actor.start()
    expect(actor.getSnapshot().context.reading.current_node).toBe('n_river')
    actor.send({ type: 'RESTART' })
    const { reading } = actor.getSnapshot().context
    expect(reading.current_node).toBe('n_woods')
    expect(reading.var_state).toEqual(carried)
  })

  it('falls back to start() when no continuation seed was supplied', () => {
    const actor = createActor(readerMachine, { input: { story: book2 } })
    actor.start()
    actor.send({ type: 'RESTART' })
    const { reading } = actor.getSnapshot().context
    expect(reading.current_node).toBe('n_camp')
    expect(reading.var_state).toEqual({ torch: false, coins: 0 })
  })

  it('restarts as a continuation, not as a character read, when both seeds are present', () => {
    // ReaderPage never sets both for one read (a continuation read is
    // deliberately not seeded from the active character), so this pins
    // safeStart's precedence for the only case that can still reach it: both
    // props surviving to a RESTART. The two branches are distinguishable by
    // construction, because a character seed enters at start_node while a
    // continuation enters at its declared entry node.
    //
    // Without this test nothing in the suite separates the two orderings: the
    // whole reader suite stays green with the precedence inverted, which is
    // why the assertion is on current_node and not only on var_state.
    const characterSeed = { torch: false, coins: 9 }
    const actor = createActor(readerMachine, {
      input: {
        story: book2,
        reading: startContinuation(book2, seed.entryNode, seed.varState),
        continuation: seed,
        seed: characterSeed,
      },
    })
    actor.start()
    actor.send({ type: 'RESTART' })
    const { reading } = actor.getSnapshot().context
    // Continuation wins: the entry node, not book 2's own start_node.
    expect(reading.current_node).toBe('n_woods')
    expect(reading.var_state).toEqual(carried)
    // And specifically NOT the character-seeded start.
    expect(reading.current_node).not.toBe('n_camp')
    expect(reading.var_state).not.toEqual({ torch: false, coins: 9 })
  })

  it('surfaces context.error instead of dying when the continuation restart throws', () => {
    // startContinuation throws on the same contract as start(): an unknown
    // entryNode falls back to start_node (engine.ts), so a dangling start_node
    // is the one condition under which it has no node to enter.
    //
    // `reading` is supplied on purpose. Without it the initial-context factory
    // calls safeStart itself and context.error is already true before RESTART
    // is ever sent, which makes the assertion below pass whether or not
    // `reset` has a working catch. Starting from a healthy state and asserting
    // error is false first means only reset's own catch can flip it.
    //
    // What this test deliberately does NOT prove: that the continuation branch
    // threw rather than the start() branch. startContinuation can only throw
    // where start() would throw too, so no fixture can separate them; the two
    // tests above are what pin the continuation branch.
    const corruptedBook2: Storybook = { ...book2, start_node: 'n_does_not_exist' }
    const healthy = startContinuation(book2, 'n_woods', { torch: true, coins: 4 })
    const logSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const actor = createActor(readerMachine, {
        input: {
          story: corruptedBook2,
          reading: healthy,
          continuation: { entryNode: 'n_also_missing' },
        },
      })
      actor.start()
      expect(actor.getSnapshot().context.error).toBe(false)
      actor.send({ type: 'RESTART' })
      const snapshot = actor.getSnapshot()
      expect(snapshot.status).toBe('active')
      expect(snapshot.context.error).toBe(true)
    } finally {
      logSpy.mockRestore()
    }
  })
})

describe('reader machine bookmarks (SAVE_BOOKMARK/LOAD_BOOKMARK/DELETE_BOOKMARK)', () => {
  it('SAVE_BOOKMARK adds a slot without changing the live position', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_take_lantern' })
    const before = actor.getSnapshot().context.reading
    actor.send({ type: 'SAVE_BOOKMARK', label: 'At the fork' })
    const after = actor.getSnapshot().context.reading
    expect(after.current_node).toBe(before.current_node)
    expect(Object.keys(after.save_slots)).toHaveLength(1)
    const saved = Object.values(after.save_slots)[0] as { label: string; current_node: string }
    expect(saved.label).toBe('At the fork')
    expect(saved.current_node).toBe(before.current_node)
  })

  it('LOAD_BOOKMARK moves the live position back to a saved spot', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_take_lantern' })
    actor.send({ type: 'SAVE_BOOKMARK', label: 'At the fork' })
    const slotId = Object.keys(actor.getSnapshot().context.reading.save_slots)[0]
    actor.send({ type: 'CHOOSE', choiceId: 'c_bright_tunnel' })
    expect(actor.getSnapshot().value).toBe('ended')

    actor.send({ type: 'LOAD_BOOKMARK', slotId })

    expect(actor.getSnapshot().value).toBe('reading')
    expect(actor.getSnapshot().context.reading.current_node).toBe('n_cave_fork')
    // The bookmark itself survives being loaded from.
    expect(Object.keys(actor.getSnapshot().context.reading.save_slots)).toContain(slotId)
  })

  it('LOAD_BOOKMARK with an unknown slot id is a no-op', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_take_lantern' })
    const before = actor.getSnapshot().context.reading
    actor.send({ type: 'LOAD_BOOKMARK', slotId: 'does-not-exist' })
    expect(actor.getSnapshot().context.reading).toEqual(before)
  })

  it('DELETE_BOOKMARK removes a saved slot', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'SAVE_BOOKMARK', label: 'Start' })
    const slotId = Object.keys(actor.getSnapshot().context.reading.save_slots)[0]
    actor.send({ type: 'DELETE_BOOKMARK', slotId })
    expect(actor.getSnapshot().context.reading.save_slots).toEqual({})
  })

  it('SAVE_BOOKMARK and DELETE_BOOKMARK also work from the ended state', () => {
    const actor = createActor(readerMachine, { input: { story: lantern } })
    actor.start()
    actor.send({ type: 'CHOOSE', choiceId: 'c_ignore_lantern' })
    actor.send({ type: 'CHOOSE', choiceId: 'c_bright_tunnel' })
    expect(actor.getSnapshot().value).toBe('ended')

    actor.send({ type: 'SAVE_BOOKMARK', label: 'The end' })
    expect(actor.getSnapshot().value).toBe('ended')
    // Asserted BEFORE the delete below: an unhandled SAVE_BOOKMARK (XState
    // drops an event with no matching `on` handler silently, no throw) would
    // otherwise leave save_slots empty here, and the delete that follows
    // would then no-op on an undefined slotId, making the final `toEqual({})`
    // pass regardless of whether Save actually did anything.
    const slots = Object.keys(actor.getSnapshot().context.reading.save_slots)
    expect(slots).toHaveLength(1)
    const slotId = slots[0]

    actor.send({ type: 'DELETE_BOOKMARK', slotId })
    expect(actor.getSnapshot().value).toBe('ended')
    expect(actor.getSnapshot().context.reading.save_slots).toEqual({})
  })
})
