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

// start() throws on a dangling start_node (same contract as choose()/back()),
// but has no prior reading state to fall back on. On that throw, hand back an
// inert placeholder ReadingState with error: true instead of letting the
// throw escape: Reader.tsx renders the error branch before ever reading
// `current_node` off a real node, so the placeholder is never dereferenced.
function safeStart(story: Storybook): { reading: ReadingState; error: boolean } {
  try {
    return { reading: start(story), error: false }
  } catch (err) {
    console.error('reader: start failed', err)
    return {
      reading: {
        current_node: story.start_node,
        var_state: {},
        path: [],
        visit_set: [],
        version: story.version,
        state_revision: 0,
        save_slots: {},
      },
      error: true,
    }
  }
}

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
  // XState's outer machinery ever sees it. start() throws on the same
  // contract (a dangling start_node), and is guarded the same way: both by
  // `reset` (RESTART) and by the initial-context factory below, via
  // safeStart().
  // #CRITICAL: data-integrity: never let choose()/back()/start() throw
  // escape an assign() action or the context factory; the actor would die
  // (or render would crash into the generic AppErrorBoundary instead of the
  // reader's own recovery screen) and even RESTART could stop working.
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
      // Unreachable in practice: this action is wired only to CHOOSE (see
      // `on: { CHOOSE: ... }` below); the check is TS narrowing for `event`,
      // not a real runtime branch.
      /* v8 ignore next */
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
      /* v8 ignore next */
      return previous === null ? {} : { reading: previous }
    }),
    reset: assign(({ context }) => safeStart(context.story)),
  },
  guards: {
    reachedEnding: ({ context }) => isEnding(context.story, context.reading),
    canGoBack: ({ context }) => canGoBack(context.story, context.reading),
  },
}).createMachine({
  id: 'reader',
  context: ({ input }) => {
    if (input.reading) {
      return { story: input.story, reading: input.reading, error: false }
    }
    const { reading, error } = safeStart(input.story)
    return { story: input.story, reading, error }
  },
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
