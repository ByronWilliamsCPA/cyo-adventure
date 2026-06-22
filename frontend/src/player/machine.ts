/**
 * XState reader machine: the story-as-state-machine player (tech-spec).
 *
 * The machine holds the current ReadingState in context and delegates every
 * transition to the deterministic engine, so it shares the exact Runtime
 * Semantics v1 behaviour (and the cross-implementation conformance) of the
 * engine. It models the reading lifecycle: `reading` until an ending node is
 * reached, then `ended`.
 */

import { assign, setup } from 'xstate'

import { choose, isEnding, start } from './engine'
import type { ReadingState, Storybook } from './types'

export interface ReaderContext {
  story: Storybook
  reading: ReadingState
}

export type ReaderEvent = { type: 'CHOOSE'; choiceId: string } | { type: 'RESTART' }

export interface ReaderInput {
  story: Storybook
  reading?: ReadingState
}

export const readerMachine = setup({
  types: {
    context: {} as ReaderContext,
    events: {} as ReaderEvent,
    input: {} as ReaderInput,
  },
  actions: {
    applyChoice: assign(({ context, event }) => {
      if (event.type !== 'CHOOSE') return {}
      return { reading: choose(context.story, context.reading, event.choiceId) }
    }),
    reset: assign(({ context }) => ({ reading: start(context.story) })),
  },
  guards: {
    reachedEnding: ({ context }) => isEnding(context.story, context.reading),
  },
}).createMachine({
  id: 'reader',
  context: ({ input }) => ({
    story: input.story,
    reading: input.reading ?? start(input.story),
  }),
  initial: 'reading',
  states: {
    reading: {
      always: { target: 'ended', guard: 'reachedEnding' },
      on: {
        CHOOSE: { actions: 'applyChoice' },
        RESTART: { target: 'reading', actions: 'reset', reenter: true },
      },
    },
    ended: {
      on: {
        RESTART: { target: 'reading', actions: 'reset' },
      },
    },
  },
})
