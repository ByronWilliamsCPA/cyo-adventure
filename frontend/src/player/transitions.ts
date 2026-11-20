/**
 * A read-only broadcast of the reader machine's position-changing transitions.
 *
 * The reading-trail recorder (`reader/readingTrail.ts`) needs to know what the
 * child actually did, not only where they ended up: which of two choices that
 * lead to the same node was tapped, whether a return to the opening node was a
 * Go back or a Start over, and every single-choice node an ADR-026 flowed stop
 * walked through. A ReadingState snapshot cannot answer those (a back to page
 * one and a restart produce identical states, and several machine transitions
 * can land between two React renders), so the machine publishes each
 * transition here as it applies it.
 *
 * Observers cannot influence reading: a listener receives a value, its return
 * is ignored, and anything it throws is swallowed, so a broken observer can
 * never fail a transition. With no listener attached this costs one empty
 * Set iteration per transition.
 */

import type { ReadingState, Storybook } from './types'

export type ReaderTransition =
  | {
      type: 'choose'
      /** The node the choice was made from. */
      from: string
      choiceId: string
      to: ReadingState
    }
  | { type: 'back'; to: ReadingState }
  | { type: 'restart'; to: ReadingState }
  | { type: 'jump'; to: ReadingState }

export type ReaderTransitionListener = (story: Storybook, transition: ReaderTransition) => void

const listeners = new Set<ReaderTransitionListener>()

/** Subscribe to transitions for every reader; returns the unsubscribe. Callers
 * filter by `story` identity, which is the machine's own `context.story`. */
export function onReaderTransition(listener: ReaderTransitionListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Publish one applied transition. Called by the reader machine only. */
export function emitReaderTransition(story: Storybook, transition: ReaderTransition): void {
  for (const listener of listeners) {
    try {
      listener(story, transition)
    } catch {
      // #CRITICAL: data-integrity: an observer must never break reading. This
      // runs inside the machine's assign action, so a throw escaping here
      // would turn a valid choice into the reader's error state.
      // #VERIFY: transitions.test.ts "a throwing listener does not stop the
      // others or reach the caller".
    }
  }
}
