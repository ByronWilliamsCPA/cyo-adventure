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
import type { ContinuationSeed } from './series'
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

// start()/startContinuation() throw on a dangling start_node (the same
// throwing contract as choose(); back() is the one exception, failing closed
// with null), but have no prior reading state to fall back on. On that throw,
// hand back emptyReading() with error: true instead of letting the throw
// escape (see emptyReading above).
//
// Two seeds can pick the entry point, and `continuation` wins when both are
// present:
//   - a WS-G series continuation (issue #460) resumes at its declared entry
//     node with the carried variables overlaid on this book's declared
//     initials (startContinuation re-filters both by declared type and int
//     bounds);
//   - an ADR-028 character seed always enters at this book's own start_node,
//     with the character's carried stats overlaid.
//
// ReaderPage never supplies both for one read: a continuation read is
// deliberately not seeded from the active character, because layering the two
// would invent a client-side merge the server has no counterpart for (see the
// #CRITICAL note on ReaderPage's fresh-read seed). The precedence here settles
// only the case where both props survive to a RESTART, and it keeps that
// RESTART faithful to how the read actually began.
// #CRITICAL: data-integrity: a continuation read must restart as a
// continuation, never as a character-seeded read; the latter would rewind a
// series reader to this book's start_node and can open a gated branch the
// child never earned.
// #VERIFY: machine.test.ts "reader machine RESTART on a continuation read
// (issue #460)".
function safeStart(
  story: Storybook,
  continuation?: ContinuationSeed,
  seed?: VarState
): { reading: ReadingState; error: boolean } {
  try {
    if (continuation !== undefined) {
      return {
        reading: startContinuation(story, continuation.entryNode, continuation.varState),
        error: false,
      }
    }
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
  // choice: a dangling target or corrupted cached state). choose() throws on
  // that by contract (shared with the Python conformance corpus; back() is the
  // exception, failing closed with null rather than throwing),
  // and XState's actor runtime catches an assign() throw internally and
  // permanently stops the actor rather than letting it propagate to the
  // caller of send() (there is no way to recover an actor once that
  // happens), so the throw MUST be caught here, inside the action, before
  // XState's outer machinery ever sees it. start() throws on the same
  // contract (a dangling start_node), and is guarded the same way: both by
  // `reset` (RESTART) and by the initial-context factory below, via
  // safeStart().
  // #CRITICAL: data-integrity: never let a choose()/start()/startContinuation()
  // throw escape an assign() action or the context factory; the actor would die
  // (or render would crash into the generic AppErrorBoundary instead of the
  // reader's own recovery screen) and even RESTART could stop working.
  // #VERIFY: machine.test.ts "surfaces context.error instead of dying when a
  // choice does not exist on the node" and "surfaces context.error instead
  // of crashing when start_node is dangling".
  error: boolean
  // The continuation provenance of this read (issue #460), retained so RESTART
  // can reproduce it. `input.reading` is a fully-formed state and says nothing
  // about how it was produced, so without these two values `reset` would have
  // to fall back to the new-reader path and would silently replace a child's
  // carried series state with this book's declared initials.
  // #CRITICAL: data-integrity: a continuation read MUST restart as a
  // continuation for as long as this machine is mounted. Dropping the seed
  // rewinds a series reader to this book's own start_node and declared
  // variable values, which can open a gated branch the child never earned (or
  // discard one they did), with nothing logged.
  // #VERIFY: machine.test.ts "reader machine RESTART on a continuation read
  // (issue #460)".
  // #EDGE: data-integrity: that guarantee is session-scoped, and deliberately
  // so for now. The seed reaches us from router location.state (ContinueSeries
  // navigates, ReaderRoute parses), and ReadingState records no continuation
  // provenance, so a read re-entered in a later session (reload, deep link,
  // library re-entry) arrives with `continuation` undefined and restarts as an
  // ordinary new reader, exactly as it did before issue #460. Restart-within-
  // the-session is the case #460 filed; the durable case is the still-open
  // half of debt SL10.
  // #VERIFY: persist the seed with saved progress (SL10 proposes IndexedDB),
  // then assert a restart honours it after a remount with no location.state.
  continuation?: ContinuationSeed
}

export type ReaderEvent =
  { type: 'CHOOSE'; choiceId: string } | { type: 'BACK' } | { type: 'RESTART' }

export interface ReaderInput {
  story: Storybook
  reading?: ReadingState
  /**
   * The character's carried stats (ADR-028), when the read was seeded from the
   * profile's active character. Retained for the same reason as
   * `continuation`; see ReaderContext.seed.
   */
  seed?: VarState
  /**
   * The continuation seed this book was opened with (WS-G), when there is one.
   * It seeds the initial state only when no `reading` is supplied, but is
   * retained either way so RESTART can reproduce a continuation read; see
   * ReaderContext.continuation.
   */
  continuation?: ContinuationSeed
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
    reset: assign(({ context }) => safeStart(context.story, context.continuation, context.seed)),
  },
  guards: {
    reachedEnding: ({ context }) => isEnding(context.story, context.reading),
    canGoBack: ({ context }) => canGoBack(context.story, context.reading, context.seed),
  },
}).createMachine({
  id: 'reader',
  context: ({ input }) => {
    // A supplied `reading` always wins for the INITIAL state (it is the child's
    // saved place, or a continuation state ReaderPage already built); the seed
    // is retained regardless, because RESTART is about where this book begins,
    // not about where this session resumed.
    if (input.reading) {
      return {
        story: input.story,
        reading: input.reading,
        error: false,
        seed: input.seed,
        continuation: input.continuation,
      }
    }
    const { reading, error } = safeStart(input.story, input.continuation, input.seed)
    return {
      story: input.story,
      reading,
      error,
      seed: input.seed,
      continuation: input.continuation,
    }
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
