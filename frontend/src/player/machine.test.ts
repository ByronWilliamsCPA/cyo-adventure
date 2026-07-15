import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { createActor } from 'xstate'
import { describe, expect, it, vi } from 'vitest'

import { readerMachine } from './machine'
import type { Storybook } from './types'

const here = path.dirname(fileURLToPath(import.meta.url))
const tracesPath = path.resolve(here, '../../../schema/conformance/player_traces.json')
const lantern = (
  JSON.parse(readFileSync(tracesPath, 'utf-8')) as {
    traces: { story: Storybook }[]
  }
).traces[0].story

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
})
