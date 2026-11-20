import { afterEach, describe, expect, it, vi } from 'vitest'
import { createActor } from 'xstate'

import { readerMachine } from './machine'
import { emitReaderTransition, onReaderTransition, type ReaderTransition } from './transitions'
import type { Storybook } from './types'

const STORY: Storybook = {
  schema_version: '1',
  id: 's',
  version: 1,
  title: 'T',
  metadata: {},
  start_node: 'a',
  nodes: [
    {
      id: 'a',
      body: '',
      is_ending: false,
      choices: [
        { id: 'c1', label: 'one', target: 'b' },
        { id: 'c2', label: 'two', target: 'b' },
      ],
    },
    { id: 'b', body: '', is_ending: false, choices: [{ id: 'c3', label: 'on', target: 'e' }] },
    {
      id: 'e',
      body: '',
      is_ending: true,
      ending: { id: 'e1', kind: 'success', valence: 'positive', title: 'E' },
    },
  ],
}

const unsubscribers: Array<() => void> = []

afterEach(() => {
  for (const unsubscribe of unsubscribers.splice(0)) unsubscribe()
})

function collect(): ReaderTransition[] {
  const seen: ReaderTransition[] = []
  unsubscribers.push(
    onReaderTransition((story, transition) => {
      if (story === STORY) seen.push(transition)
    })
  )
  return seen
}

describe('reader transitions broadcast', () => {
  it('a throwing listener does not stop the others or reach the caller', () => {
    unsubscribers.push(
      onReaderTransition(() => {
        throw new Error('observer bug')
      })
    )
    const seen = collect()
    const to = {
      current_node: 'a',
      var_state: {},
      path: ['a'],
      visit_set: ['a'],
      version: 1,
      state_revision: 0,
      save_slots: {},
    }
    expect(() => emitReaderTransition(STORY, { type: 'back', to })).not.toThrow()
    expect(seen).toHaveLength(1)
  })

  it('unsubscribe stops delivery', () => {
    const listener = vi.fn()
    const unsubscribe = onReaderTransition(listener)
    unsubscribe()
    emitReaderTransition(STORY, {
      type: 'jump',
      to: {
        current_node: 'a',
        var_state: {},
        path: ['a'],
        visit_set: ['a'],
        version: 1,
        state_revision: 0,
        save_slots: {},
      },
    })
    expect(listener).not.toHaveBeenCalled()
  })

  it('the machine publishes the tapped choice id, BACK, and RESTART as it applies them', () => {
    const seen = collect()
    const actor = createActor(readerMachine, { input: { story: STORY } }).start()
    actor.send({ type: 'CHOOSE', choiceId: 'c2' })
    actor.send({ type: 'CHOOSE', choiceId: 'c3' })
    actor.send({ type: 'BACK' })
    actor.send({ type: 'RESTART' })
    actor.stop()
    expect(seen.map((t) => t.type)).toEqual(['choose', 'choose', 'back', 'restart'])
    expect(seen[0]).toMatchObject({ type: 'choose', from: 'a', choiceId: 'c2' })
    expect(seen[0].to.current_node).toBe('b')
    expect(seen[2].to.current_node).toBe('b')
    expect(seen[3].to.path).toEqual(['a'])
    // Machine behaviour is unchanged by observation.
    expect(actor.getSnapshot().context.reading.current_node).toBe('a')
  })

  it('a refused choice publishes nothing', () => {
    const seen = collect()
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const actor = createActor(readerMachine, { input: { story: STORY } }).start()
    actor.send({ type: 'CHOOSE', choiceId: 'no_such_choice' })
    actor.stop()
    errors.mockRestore()
    expect(seen).toEqual([])
  })
})
