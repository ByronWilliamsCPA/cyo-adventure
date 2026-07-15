/**
 * XState reader machine: the story-as-state-machine player (tech-spec).
 *
 * The machine holds the current ReadingState in context and delegates every
 * transition to the deterministic engine, so it shares the exact Runtime
 * Semantics v1 behaviour (and the cross-implementation conformance) of the
 * engine. It models the reading lifecycle: `reading` until an ending node is
 * reached, then `ended`.
 *
 * BACK undoes the last choice by recomputing the state as if the child had
 * made every recorded choice except the last one: the engine replays the
 * recorded path from the start (never reversing effects, so on_enter effects
 * are recomputed faithfully). It is guarded to be unavailable at the start
 * node with an empty choice history, and for states the engine cannot
 * faithfully replay (continuation reads). From `ended` it returns into the
 * story, which is where trying the other path is most valuable.
 */

import { assign, setup } from 'xstate'

import { back, canGoBack, choose, isEnding, start } from './engine'
import type { ReadingState, Storybook } from './types'

export interface ReaderContext {
  story: Storybook
  reading: ReadingState
  // Set when a transition could not be applied (a structurally invalid
  // choice: a dangling target or corrupted cached state). choose()/back()
  // throw on that by contract (shared with the Python conformance corpus),
  // and XState's actor runtime catches an assign() throw internally and
  // permanently stops the actor rather than letting it propagate to the
  // caller of send() (there is no way to recover an actor once that
  // happens), so the throw MUST be caught here, inside the action, before
  // XState's outer machinery ever sees it.
  // #CRITICAL: data-integrity: never let choose()/back() throw escape an
  // assign() action; the actor would die and even RESTART could stop working.
  // #VERIFY: machine.test.ts "recovers from a throwing transition".
  error: boolean
}

export type ReaderEvent =
  | { type: 'CHOOSE'; choiceId: string }
  | { type: 'BACK' }
  | { type: 'RESTART' }

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
      try {
        return { reading: choose(context.story, context.reading, event.choiceId), error: false }
      } catch (err) {
        console.error('reader: choice transition failed', err)
        return { error: true }
      }
    }),
    applyBack: assign(({ context }) => {
      const previous = back(context.story, context.reading)
      // The canGoBack guard makes null unreachable in practice; keeping the
      // no-op branch means a raw BACK can never corrupt the reading state.
      return previous === null ? {} : { reading: previous }
    }),
    reset: assign(({ context }) => ({ reading: start(context.story), error: false })),
  },
  guards: {
    reachedEnding: ({ context }) => isEnding(context.story, context.reading),
    canGoBack: ({ context }) => canGoBack(context.story, context.reading),
  },
}).createMachine({
  id: 'reader',
  context: ({ input }) => ({
    story: input.story,
    reading: input.reading ?? start(input.story),
    error: false,
  }),
  initial: 'reading',
  states: {
    reading: {
      always: { target: 'ended', guard: 'reachedEnding' },
      on: {
        CHOOSE: { actions: 'applyChoice' },
        BACK: { guard: 'canGoBack', actions: 'applyBack' },
        RESTART: { target: 'reading', actions: 'reset', reenter: true },
      },
    },
    ended: {
      on: {
        // The previous node can never itself be an ending (a choice was made
        // from it, and choose() rejects ending nodes), so BACK always lands
        // back in `reading`.
        BACK: { target: 'reading', guard: 'canGoBack', actions: 'applyBack' },
        RESTART: { target: 'reading', actions: 'reset' },
      },
    },
  },
})
