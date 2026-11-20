/**
 * "Try a different choice" (ending screen): where the most recent real
 * decision on this read was, measured in single `back()` steps.
 *
 * This module only MEASURES. It never builds a reading state for the reader to
 * adopt: the reader applies the answer by sending the machine's existing BACK
 * event `steps` times, the same transition "Go back a page" sends, so state,
 * effects and visit sets are rewound by the one replay path the machine
 * already trusts (engine.ts `back()`), never by a second mutation route.
 *
 * Why counting steps is exact: `replayRecordedPath` returns the state after
 * each recorded step (`states[i]` is the state the child was in at
 * `path[i]`), and one `back()` from `states[j]` yields `states[j - 1]`
 * (back() takes `states[length - 2]` of the same replay, and a prefix of a
 * faithful replay replays to the same prefix). So `last - i` BACK events from
 * the live state land exactly on `states[i]`.
 *
 * What counts as a fork: a recorded state whose VISIBLE choice list (the
 * engine's own `visibleChoices`, evaluated against the var_state the child
 * actually had there) holds two or more choices. A node that declares two
 * choices but showed only one on this path (a condition was false) was not a
 * decision for this child and is skipped. This is deliberately independent of
 * ADR-026 rendered stops: a flowed stop's intermediate nodes are single-choice
 * by construction, so they are never forks, and a stop's terminal is a fork
 * exactly when it showed 2+ choices. Landing on a fork therefore lands on a
 * stop terminal at flowed bands, which `useFlowedStop` recomposes like any
 * other Go back landing.
 */

import { choose, replayRecordedPath, visibleChoices } from '../player/engine'
import type { ReadingState, Storybook, VarState } from '../player/types'

export interface LatestFork {
  /** How many BACK events take the live state to the fork. Always >= 1. */
  steps: number
  /** The fork's node id (where the child lands). */
  nodeId: string
  /**
   * The choice the child took at that fork last time, or null when it cannot
   * be told apart from a sibling (two choices with the same target and the
   * same effects produce identical states, so either reconstruction is
   * equally faithful and naming one would be a guess).
   */
  previousChoiceId: string | null
}

function sameStep(a: ReadingState, b: ReadingState): boolean {
  const aKeys = Object.keys(a.var_state)
  if (aKeys.length !== Object.keys(b.var_state).length) return false
  if (!aKeys.every((key) => a.var_state[key] === b.var_state[key])) return false
  const aVisits = new Set(a.visit_set)
  const bVisits = new Set(b.visit_set)
  return aVisits.size === bVisits.size && [...aVisits].every((id) => bVisits.has(id))
}

function previousChoiceAt(story: Storybook, fork: ReadingState, next: ReadingState): string | null {
  const matches = visibleChoices(story, fork).filter((choice) => {
    if (choice.target !== next.current_node) return false
    try {
      return sameStep(choose(story, fork, choice.id), next)
    } catch {
      return false
    }
  })
  return matches.length === 1 ? matches[0].id : null
}

/**
 * The most recent fork strictly before the live position, or null when there
 * is none (a linear read, a read still at its first stop) or when the recorded
 * path cannot be replayed from the read's own start (a series continuation
 * read, a version mismatch): the same fail-closed contract as `canGoBack`, so
 * the action is hidden exactly where Go back would refuse.
 *
 * #CRITICAL: data-integrity: `seed` must be the same seed the machine holds
 * (Reader's `seed` prop). The machine's BACK guard replays with that seed; a
 * seed-blind count here would either disagree about availability (a dead
 * button) or count a different path than the one BACK replays.
 * #VERIFY: rewindToFork.test.ts "returns null on a seeded read when the seed
 * is not forwarded".
 */
export function findLatestFork(
  story: Storybook,
  reading: ReadingState,
  seed?: VarState
): LatestFork | null {
  if (reading.path.length < 2) return null
  const states = replayRecordedPath(story, reading, seed)
  if (states === null || states.length < 2) return null
  const last = states.length - 1
  for (let i = last - 1; i >= 0; i -= 1) {
    if (visibleChoices(story, states[i]).length >= 2) {
      return {
        steps: last - i,
        nodeId: states[i].current_node,
        previousChoiceId: previousChoiceAt(story, states[i], states[i + 1]),
      }
    }
  }
  return null
}
