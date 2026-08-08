/**
 * ADR-028 Task 9: reads the bound persistent character's name and carried
 * seed off a reading state, converting the server's JSON `null` to the
 * `undefined` the reader machine expects.
 *
 * Split out of ReaderPage.tsx (not colocated with the component) so this
 * plain function does not trip react-refresh's only-export-components rule
 * on a file that otherwise exports only the ReaderPage component.
 */

import type { ReadingStateView } from '../client/types.gen'
import type { ReadingState, VarState } from '../player/types'

/**
 * Reads the two Task 6/ADR-028 View-only fields the reader needs off a
 * reading state that may, at runtime, actually be a `ReadingStateView`
 * (`character_name`, `seed_var_state`) even though `ReadingState` itself
 * does not model them (matching the four pre-existing View-only fields'
 * precedent: offline/sync.test.ts's `FORBIDDEN_VIEW_KEYS`/`viewShapedState`).
 * `getReadingState`/`fetchServerState`/a conflict-adopt's `currentRow` are
 * all typed `ReadingState`, but every one of them can carry a real server
 * View at runtime, so this is the single place that widens the type back
 * out rather than trusting each call site to remember to.
 *
 * #ASSUME: data-integrity: `state.seed_var_state` arrives as `null` (not
 * `undefined`) from JSON when no character is bound; `?? undefined`
 * converts both `null` and a genuinely absent property to `undefined`
 * here, once, so `undefined` is the only "no seed" value anything
 * downstream (readerMachine's `context.seed`, whose own type is
 * `VarState | undefined`) ever has to handle. Piping the raw `null`
 * through instead would still type-check today only via a loosened prop
 * type; this conversion keeps `Reader`'s `seed` prop exactly as narrow as
 * `ReaderInput.seed`.
 * #VERIFY: ReaderPage.test.tsx "converts a null seed_var_state to undefined
 * before it reaches the rendered reader".
 *
 * The character's NAME is read from this same reading state (never from
 * `useActiveCharacter`), and deliberately so: this is the character the
 * server actually snapshotted a seed from when the read (or its
 * continuation) began, which can differ from whichever character is active
 * on the profile right now (a later-created or later-retired character).
 * Showing "whoever is active today" here would let the chrome name a
 * character whose attributes were never the ones this read's seed, path,
 * and var_state are actually built from, exactly the drift ADR-028's
 * snapshot-at-creation design exists to prevent.
 */
export function deriveCharacterSeed(state: ReadingState | undefined): {
  characterName: string | null
  seed: VarState | undefined
} {
  if (state === undefined) return { characterName: null, seed: undefined }
  const view = state as unknown as Partial<ReadingStateView>
  return {
    characterName: view.character_name ?? null,
    seed: view.seed_var_state ?? undefined,
  }
}
