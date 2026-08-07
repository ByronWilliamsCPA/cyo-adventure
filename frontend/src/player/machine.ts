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
 * recorded path from the read's own start, the seeded start when this
 * machine was given a seed (never reversing effects, so on_enter effects are
 * recomputed faithfully). It is guarded to be unavailable at the start node
 * with an empty choice history, and for states the engine cannot faithfully
 * replay against that start. From `ended` it returns into the story, which
 * is where trying the other path is most valuable.
 */

import { assign, setup } from 'xstate'

import { back, canGoBack, choose, isEnding, start, startContinuation } from './engine'
import type { ReadingState, Storybook, VarState } from './types'

// An inert placeholder ReadingState, used when start()/startContinuation()
// throws and there is no prior reading state to fall back on. Reader.tsx
// renders the error branch before ever reading `current_node` off a real
// node, so the placeholder is never dereferenced.
function emptyReading(story: Storybook): ReadingState {
  return {
    current_node: story.start_node,
    var_state: {},
    path: [],
    visit_set: [],
    version: story.version,
    state_revision: 0,
    save_slots: {},
  }
}

// start()/startContinuation() throw on a dangling start node (same contract
// as choose()/back()). On that throw, hand back emptyReading() with
// error: true instead of letting the throw escape (see emptyReading above).
function safeStart(story: Storybook, seed?: VarState): { reading: ReadingState; error: boolean } {
  try {
    return {
      reading: seed === undefined ? start(story) : startContinuation(story, null, seed),
      error: false,
    }
  } catch (err) {
    console.error('reader: start failed', err)
    return { reading: emptyReading(story), error: true }
  }
}

export interface ReaderContext {
  story: Storybook
  reading: ReadingState
  // The character's carried stats, if any. Threaded into safeStart() so
  // RESTART (and the seed-aware Go back guard/action below) re-derive the
  // same seeded start the read began with, instead of fabricating declared
  // initials (#460).
  seed?: VarState
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
  // #VERIFY: machine.test.ts "surfaces context.error instead of dying when a
  // choice does not exist on the node" and "surfaces context.error instead
  // of crashing when start_node is dangling".
  error: boolean
}

export type ReaderEvent =
  { type: 'CHOOSE'; choiceId: string } | { type: 'BACK' } | { type: 'RESTART' }

export interface ReaderInput {
  story: Storybook
  reading?: ReadingState
  seed?: VarState
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
      const previous = back(context.story, context.reading, context.seed)
      // The canGoBack guard makes null unreachable in practice; keeping the
      // no-op branch means a raw BACK can never corrupt the reading state.
      /* v8 ignore next */
      return previous === null ? {} : { reading: previous }
    }),
    reset: assign(({ context }) => safeStart(context.story, context.seed)),
  },
  guards: {
    reachedEnding: ({ context }) => isEnding(context.story, context.reading),
    canGoBack: ({ context }) => canGoBack(context.story, context.reading, context.seed),
  },
}).createMachine({
  id: 'reader',
  context: ({ input }) => {
    if (input.reading) {
      return { story: input.story, reading: input.reading, seed: input.seed, error: false }
    }
    const { reading, error } = safeStart(input.story, input.seed)
    return { story: input.story, reading, seed: input.seed, error }
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
