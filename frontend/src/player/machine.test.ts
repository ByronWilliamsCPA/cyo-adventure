import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { createActor } from 'xstate'
import { describe, expect, it } from 'vitest'

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
