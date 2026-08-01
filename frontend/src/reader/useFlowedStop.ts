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
 * produced.
 *
 * Two distinct mechanisms are at work, each used for what it is actually
 * for:
 * 1. Which stop is on screen is DERIVED state (a pure function of `reading`
 *    and `flowed`), so it is computed and stored via React's own sanctioned
 *    "adjusting state when a prop changes" pattern (a conditional
 *    `setState` call during the render body itself, not inside an effect;
 *    see https://react.dev/learn/you-might-not-need-an-effect#adjusting-
 *    -some-state-when-a-prop-changes) rather than a `useEffect`. This keeps
 *    it out of `useEffect`/`useLayoutEffect` entirely (no
 *    render-then-effect-then-rerender waterfall, and no
 *    `react-hooks/set-state-in-effect` violation), and it is naturally
 *    idempotent under StrictMode's double-render (composeStop is pure).
 * 2. Firing the silent CHOOSE batch is a genuine SIDE EFFECT against an
 *    external system (the XState actor) and belongs in a
 *    `useLayoutEffect`, fired before the browser ever paints the un-flowed
 *    origin node so a child never sees a flash of "Continue". This is the
 *    part StrictMode's double-invoked mount effect can fire twice, so it is
 *    the part guarded against that (by stop object identity, below).
 *
 * #ASSUME: data-integrity: recognising "this `reading` change was our own
 * silent advance completing" (rather than a genuinely new stop) is done
 * structurally: `reading.current_node === tracked.stop.state.current_node`.
 * This is unambiguous for every topology this integration composes
 * (composeStop already guards single-choice loops within one stop), except
 * a pathological branch node whose OWN choice targets itself, which the
 * schema does not forbid. In that one case a genuinely new transition could
 * be mistaken for the advance completing, and the choice list would keep
 * showing the pre-transition state's visible choices until the next render.
 * Accepted: no fixture in the corpus exercises a self-targeting branch
 * choice, and the failure mode is a stale choice-visibility computation,
 * not a stuck or duplicated read.
 * #VERIFY: Reader.test.tsx "does not double-apply a flowed run under
 * StrictMode's double-invoked mount effect".
 */

import { useLayoutEffect, useRef, useState } from 'react'

import type { ReaderEvent } from '../player/machine'
import { composeStop, type Stop } from '../player/stops'
import type { ReadingState, Storybook } from '../player/types'

export interface FlowedStopResult {
  /** The composed stop currently on screen, or null at page bands (3-5/5-8)
   * and on the very first render before this hook has synced at all. */
  stop: Stop | null
  /** The reading state the CURRENTLY DISPLAYED stop was actually composed
   * from (its true origin), pinned even after the live `reading` has moved
   * on to the stop's terminal. Distinct from the live `reading` passed in:
   * a caller that needs "was this the very first page of the read"
   * (Reader.tsx's dedication overlay) must ask this, not the live state. */
  originReading: ReadingState | null
}

interface Tracked {
  /** The `reading` value this hook has already accounted for -- either the
   * value `composeStop` was called on, or (once the silent advance below
   * lands) whatever later `reading` matches the stop's terminal. Comparing
   * against this is what makes "has anything changed" an identity check
   * instead of a recompute. */
  forReading: ReadingState
  stop: Stop
  originReading: ReadingState
}

export function useFlowedStop(
  story: Storybook,
  reading: ReadingState,
  send: (event: ReaderEvent) => void,
  flowed: boolean
): FlowedStopResult {
  const [tracked, setTracked] = useState<Tracked | null>(null)

  // Derived-state sync, not an effect (see module doc, point 1). Runs at
  // most twice per real change: once to notice `reading` moved, once
  // (React's own immediate re-render after a render-phase `setState`) to
  // settle on the new value.
  if (flowed) {
    if (tracked === null || tracked.forReading !== reading) {
      if (tracked !== null && reading.current_node === tracked.stop.state.current_node) {
        // Our own silent advance (the layout effect below) landed exactly
        // where this stop's composition already said it would end: still
        // the SAME stop, just the real engine catching up. Keep it, only
        // stop re-checking against the now-stale `forReading`.
        setTracked({ ...tracked, forReading: reading })
      } else {
        // A genuine new stop origin: a fresh read, RESTART, a real tap on a
        // visible choice, or a Go back landing. composeStop's own
        // precondition (only ever called on a genuine origin) holds here by
        // construction.
        setTracked({ forReading: reading, stop: composeStop(story, reading), originReading: reading })
      }
    }
  } else if (tracked !== null) {
    setTracked(null)
  }

  const stop = flowed ? (tracked?.forReading === reading ? tracked.stop : null) : null
  const originReading = flowed ? (tracked?.forReading === reading ? tracked.originReading : null) : null

  // The one real side effect: silently walk the machine through the stop's
  // single-choice hops via the SAME public CHOOSE event a tap would send
  // (see module doc, point 2).
  // #CRITICAL: timing dependencies: <StrictMode> (main.tsx) double-invokes a
  // mount-time layout effect. Without `advancedForRef`, the second, synthetic
  // invocation would re-fire the CHOOSE batch for the SAME stop, silently
  // walking the engine an extra hop or two further than the child ever saw
  // and double-applying a flowed node's effects.
  // #VERIFY: Reader.test.tsx "does not double-apply a flowed run under
  // StrictMode's double-invoked mount effect".
  const advancedForRef = useRef<Stop | null>(null)
  useLayoutEffect(() => {
    if (!stop || advancedForRef.current === stop) {
      return
    }
    advancedForRef.current = stop
    if (stop.state.current_node === stop.originNode) {
      // Already a branch, an ending, or a dead-end/loop guard: nothing to
      // silently walk through.
      return
    }
    const nodesById = new Map(story.nodes.map((node) => [node.id, node]))
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
  }, [stop, story, send])

  return { stop, originReading }
}
