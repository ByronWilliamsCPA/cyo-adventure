/**
 * ADR-028 Task 9: resolves the bound persistent character's name and carried
 * seed for a read, from whichever surface can answer for the read's phase.
 *
 * There are two such surfaces, and which one applies is decided by whether a
 * reading-state row exists yet:
 *
 * - A RESUMED read has a row, so the server already snapshotted the seed onto
 *   it at read start and `deriveCharacterSeed` reads it back off the
 *   `ReadingStateView`. This is the authoritative answer, and it is a
 *   SNAPSHOT: it keeps naming the character this read actually began with
 *   even after that character is retired or replaced.
 * - A FRESH read has no row, so there is nothing to read a seed off yet: the
 *   server creates the row and snapshots the seed on the first PUT.
 *   `makeFetchActiveCharacterBinding` asks the server for the active
 *   character's own server-computed seed instead.
 *
 * #CRITICAL: data-integrity: the fresh-read seed is CONSUMED from the server
 * (`CharacterView.seed_var_state`), never derived here from
 * `CharacterView.attributes`. A second attribute-to-seed mapping in
 * TypeScript would be free to drift from the backend's
 * `characters/seeding.py::character_seed`, and the server replays a submitted
 * state from the seed IT recorded (`player/replay.py`), so a divergence would
 * 422 the first save carrying a `choice_path` and wedge the read permanently.
 * There is exactly one mapping and it lives server-side.
 * #VERIFY: tests/integration/test_reading_character_binding.py::
 * test_character_view_seed_matches_the_seed_a_read_start_would_bind pins the
 * two server surfaces to one mapping; characterSeed.test.ts "reads the
 * server's seed_var_state and never re-derives one from attributes" pins this
 * adapter to consuming it.
 *
 * Split out of ReaderPage.tsx (not colocated with the component) so these
 * plain functions do not trip react-refresh's only-export-components rule on
 * a file that otherwise exports only the ReaderPage component.
 */

import { makeCharactersApi } from '../characters/characterApi'

import type { AxiosInstance } from 'axios'
import type { ReadingStateView } from '../client/types.gen'
import type { ReadingState, VarState } from '../player/types'

/** Which character (if any) a read is playing as, and the variables it
 * carries in. `seed: undefined` means "open from the story's declared
 * initials"; see `machine.ts::safeStart`. */
export interface CharacterBinding {
  characterName: string | null
  seed: VarState | undefined
}

/** The "no character bound" binding. A module-level constant, not a fresh
 * object literal per call: ReaderPage holds this in state and a new identity
 * each render would churn the Reader's props for no reason. */
export const NO_CHARACTER_BINDING: CharacterBinding = { characterName: null, seed: undefined }

/** Resolves the profile's active character binding for a FRESH read, or null
 * when the profile has no active character (or the lookup fails). */
export type FetchActiveCharacterBinding = (profileId: string) => Promise<CharacterBinding | null>

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
 * The widening is an intersection, not an `as unknown as` hop: `ReadingState`
 * stays on the source side of the cast (so its shared fields are still
 * checked against `ReadingStateView`, which is what the OpenAPI contract gate
 * regenerates `types.gen.ts` to keep honest), and only the two View fields
 * actually read here are added. No other View field becomes silently readable
 * through the alias.
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
 * at the boundary".
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
export function deriveCharacterSeed(state: ReadingState | undefined): CharacterBinding {
  if (state === undefined) return NO_CHARACTER_BINDING
  const view = state as ReadingState &
    Partial<Pick<ReadingStateView, 'character_name' | 'seed_var_state'>>
  return {
    characterName: view.character_name ?? null,
    seed: view.seed_var_state ?? undefined,
  }
}

/**
 * The fresh-read half: asks the server which character this profile is
 * playing as and what numbers it carries, for the case where no
 * reading-state row exists yet to read a seed off.
 *
 * Resolves `null` on every failure mode (no active character, an
 * unauthenticated/forbidden/offline lookup, an unparseable body). `null`
 * means "open this read the way it opened before ADR-028", which is exactly
 * the pre-Task-9 behavior, so a character lookup can never keep a child out
 * of a book they can otherwise read. The cost of that failure is the
 * `#EDGE` residual recorded on `api/reading.py`'s create path: the server
 * still binds the active character on the first save, so an offline fresh
 * read records a seed the client did not open from.
 */
export function makeFetchActiveCharacterBinding(api: AxiosInstance): FetchActiveCharacterBinding {
  const charactersApi = makeCharactersApi(api)
  return async (profileId: string): Promise<CharacterBinding | null> => {
    try {
      const characters = await charactersApi.list(profileId)
      if (!Array.isArray(characters)) return null
      const active = characters.find((character) => character.is_active)
      if (active === undefined) return null
      // `seed_var_state` is the SERVER's computed seed. `active.attributes`
      // is deliberately not touched here: see this module's #CRITICAL note.
      return { characterName: active.name, seed: active.seed_var_state }
    } catch (err) {
      console.warn('reader: active character lookup failed; opening unseeded:', err)
      return null
    }
  }
}
