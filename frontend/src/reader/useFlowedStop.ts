/**
 * Reader-side integration of ADR-026 rendered-stop flow (W1.1).
 *
 * `composeStop` (player/stops.ts) is a pure, read-only view: given the
 * engine's real current reading state, it tells you which further
 * single-choice nodes would flow into the same rendered stop, WITHOUT
 * changing that state. Something still has to make the engine's real state
 * catch up to match what the child is looking at (ADR-026 decision 2: a
 * flowed node's effects and visit_set entry apply "exactly as if tapped"),
 * and `backOneStop`/`canGoBackOneStop` are built assuming that real state
 * already sits at a stop's terminal (their doc: "calling back() once per
 * node in the current stop always lands on the previous stop's terminal
 * node").
 *
 * The reader's XState machine (player/machine.ts) has no "jump to this
 * state" event, only CHOOSE/BACK/RESTART, and this integration must not
 * modify it (it is shared, corpus-proven engine wiring outside this
 * package's scope). So this hook drives the SAME public CHOOSE event the
 * machine already exposes, once per single-choice hop composeStop found,
 * silently and synchronously, so the real reading state ends up identical
 * to what a human tapping through each hop one at a time would have
 * produced. Fired from a layout effect (not a plain effect) so React commits
 * the fully-advanced state before the browser ever paints the un-flowed
 * origin node; a child never sees a flash of "Continue".
 */

import { useLayoutEffect, useRef, useState } from 'react'

import type { ReaderEvent } from '../player/machine'
import { composeStop, type Stop } from '../player/stops'
import type { ReadingState, Storybook } from '../player/types'

export interface FlowedStopResult {
  /** The composed stop currently on screen, or null at page bands (3-5/5-8)
   * and whenever `reading` is not itself a genuine stop origin yet (the very
   * first render before this hook's own layout effect has run once). */
  stop: Stop | null
  /** The reading state the CURRENTLY DISPLAYED stop was composed from (its
   * origin, before this hook's own silent advance). Distinct from the live
   * `reading` passed in: by the time a multi-node stop has finished
   * advancing, the live reading state has moved on to the stop's terminal,
   * so a caller that needs "was this the very first page of the read"
   * (Reader.tsx's dedication overlay) must ask this, not the live state. */
  originReading: ReadingState | null
}

export function useFlowedStop(
  story: Storybook,
  reading: ReadingState,
  send: (event: ReaderEvent) => void,
  flowed: boolean
): FlowedStopResult {
  const [result, setResult] = useState<FlowedStopResult>({ stop: null, originReading: null })

  // Guards two hazards, both about telling a REAL new stop origin apart from
  // a `reading` value this hook produced itself:
  // #CRITICAL: timing dependencies: <StrictMode> (main.tsx) double-invokes a
  // mount-time layout effect. Re-running the CHOOSE batch on that second,
  // synthetic invocation would silently walk the engine two hops further
  // than the child ever saw, applying a flowed node's effects twice.
  // #VERIFY: Reader.test.tsx "does not double-apply a flowed run's effects
  // under StrictMode's double-invoked mount effect".
  const lastSeenReadingRef = useRef<ReadingState | null>(null)
  // #CRITICAL: timing dependencies: the CHOOSE batch below changes `reading`,
  // which re-runs this same effect; that re-run must be recognised as "our
  // own advance completing", not as a second genuine stop to compose (which
  // would violate composeStop's documented precondition: it must only ever
  // be called on a genuine stop origin, never on a mid-flow state).
  // #VERIFY: Reader.test.tsx "flows a single-choice run into one stop
  // without ever rendering a mid-flow Continue state".
  const advancingRef = useRef(false)

  useLayoutEffect(() => {
    if (!flowed) {
      setResult({ stop: null, originReading: null })
      return
    }
    if (lastSeenReadingRef.current === reading) {
      return
    }
    lastSeenReadingRef.current = reading
    if (advancingRef.current) {
      advancingRef.current = false
      return
    }
    const stop = composeStop(story, reading)
    setResult({ stop, originReading: reading })
    if (stop.state.current_node === reading.current_node) {
      // Already a branch, an ending, or a dead-end/loop guard: nothing to
      // silently walk through.
      return
    }
    const nodesById = new Map(story.nodes.map((node) => [node.id, node]))
    advancingRef.current = true
    for (let i = 0; i < stop.nodeIds.length - 1; i += 1) {
      const hop = nodesById.get(stop.nodeIds[i])
      const choiceId = hop?.choices[0]?.id
      // #EDGE: data-integrity: unreachable given composeStop's own contract
      // (every hop but the last has exactly one choice, or composition would
      // have stopped there instead), kept as a fail-closed guard rather than
      // a non-null assertion so a future stops.ts change degrades to "stop
      // advancing" instead of sending a malformed event.
      if (choiceId === undefined) break
      send({ type: 'CHOOSE', choiceId })
    }
  }, [story, reading, flowed, send])

  return flowed ? result : { stop: null, originReading: null }
}
