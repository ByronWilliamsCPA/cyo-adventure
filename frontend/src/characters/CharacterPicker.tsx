import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'

import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { Mascot } from '../kid/Mascot'

import { CharacterCreator } from './CharacterCreator'
import { LOOK_SWATCHES, makeCharactersApi, type CharacterArchetype } from './characterApi'
import './characters.css'

import type { CharacterView } from '../client/types.gen'

export interface CharacterPickerProps {
  profileId: string
  /** Called whenever the active character changes locally, whether from a
   * fresh creation (empty-profile branch) or from choosing a different
   * existing character, so a parent can mirror the new active character
   * without a refetch of its own. */
  onActiveCharacterChange?: (character: CharacterView) => void
}

type PickerState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | { status: 'ready'; characters: CharacterView[] }

const ARCHETYPE_LABELS: Record<CharacterArchetype, string> = {
  scout: 'Scout',
  guardian: 'Guardian',
  trickster: 'Trickster',
  scholar: 'Scholar',
  healer: 'Healer',
  wildheart: 'Wildheart',
}

function archetypeLabel(archetype: string): string {
  return ARCHETYPE_LABELS[archetype as CharacterArchetype] ?? archetype
}

/**
 * The K-register persistent-character picker: pick one of a few large
 * tappable cards, the same interaction shape as ProfilePickerPage. Delegates
 * straight to CharacterCreator when a profile has no characters yet, since
 * an empty grid would be a dead end for a first-time child (nothing here
 * creates a character on its own).
 * #VERIFY: CharacterPicker.test.tsx "a profile with no characters shows the
 * creator, not an empty picker".
 */
export function CharacterPicker({ profileId, onActiveCharacterChange }: CharacterPickerProps) {
  const api = useApi()
  // Memoized so its identity is stable across renders (matches
  // LibraryPage.tsx's own `useMemo(() => makeLibraryApi(api), [api])`
  // pattern), which lets the fetch effect below list it as a real
  // dependency instead of needing an exhaustive-deps suppression.
  const charactersApi = useMemo(() => makeCharactersApi(api), [api])
  const [state, setState] = useState<PickerState>({ status: 'loading' })
  const [activatingId, setActivatingId] = useState<string | null>(null)
  const [activateError, setActivateError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    // The setState calls live in this nested async function, not the effect
    // body itself, per the set-state-in-effect rule (mirrors
    // LibraryPage.tsx's own load() pattern).
    async function fetchCharacters() {
      setState({ status: 'loading' })
      try {
        const characters = await charactersApi.list(profileId)
        if (cancelled || !isMountedRef.current) return
        setState({ status: 'ready', characters })
      } catch (err) {
        logApiError('character list failed', err)
        if (cancelled || !isMountedRef.current) return
        const { kind } = classifyApiError(err)
        if (kind === 'unauthenticated') {
          setState({ status: 'unauthenticated' })
        } else if (kind === 'forbidden') {
          setState({ status: 'forbidden' })
        } else {
          setState({ status: 'error' })
        }
      }
    }
    void fetchCharacters()
    return () => {
      cancelled = true
    }
  }, [profileId, reloadKey, charactersApi])

  const handleCreated = useCallback(
    (character: CharacterView) => {
      setState({ status: 'ready', characters: [character] })
      onActiveCharacterChange?.(character)
    },
    [onActiveCharacterChange]
  )

  // #ASSUME: timing dependencies: activate() updates local state directly
  // from the response body instead of refetching the list, so a chosen
  // character stops-being/becomes active in the same render pass with no
  // reload. #VERIFY: CharacterPicker.test.tsx "choosing a different
  // character calls activate and updates selection without a page reload".

  // #ASSUME: concurrency: `activatingIdRef` mirrors `activatingId` so the
  // settle handlers below can tell a CURRENT activation's response apart
  // from a STALE one without waiting on a re-render (state updates are not
  // synchronously readable from inside the very closure that scheduled
  // them). Every tile is also disabled for the whole grid, not just the one
  // being activated (see the `disabled={activatingId !== null}` below), so a
  // second tap cannot start a concurrent `activate()` call through the UI in
  // the first place; the ref check is the second, defensive layer for the
  // case a caller invokes `activate` some other way. Without both, tapping A
  // then B would let A's `.finally` clear B's still-in-flight busy state,
  // and whichever request resolved last (not whichever the child tapped
  // last) would win `is_active` and fire `onActiveCharacterChange`.
  // #VERIFY: CharacterPicker.test.tsx "disables every tile while an
  // activation is in flight, so a second tap cannot start a concurrent
  // activate".
  const activatingIdRef = useRef<string | null>(null)

  const activate = useCallback(
    (characterId: string) => {
      if (activatingIdRef.current !== null) return
      setActivateError(null)
      setActivatingId(characterId)
      activatingIdRef.current = characterId
      charactersApi
        .activate(characterId)
        .then((activated) => {
          if (!isMountedRef.current || activatingIdRef.current !== characterId) return
          setState((prev) =>
            prev.status === 'ready'
              ? {
                  status: 'ready',
                  characters: prev.characters.map((character) =>
                    character.id === activated.id ? activated : { ...character, is_active: false }
                  ),
                }
              : prev
          )
          onActiveCharacterChange?.(activated)
        })
        .catch((err: unknown) => {
          logApiError('character activate failed', err)
          if (!isMountedRef.current || activatingIdRef.current !== characterId) return
          setActivateError("That didn't work. Let's try again.")
        })
        .finally(() => {
          // Only the activation that is still current clears the shared
          // busy state; a stale settle (already superseded, or the request
          // this function early-returned on) must not clobber it.
          if (activatingIdRef.current === characterId) {
            activatingIdRef.current = null
            if (isMountedRef.current) setActivatingId(null)
          }
        })
    },
    [charactersApi, onActiveCharacterChange]
  )

  if (state.status === 'loading') {
    return (
      <div className="character-picker__loading" role="status" aria-live="polite">
        <Mascot size={72} />
        <p>Finding your characters…</p>
      </div>
    )
  }
  if (state.status === 'unauthenticated' || state.status === 'forbidden') {
    return (
      <EmptyState
        title="Time to find your grown-up"
        description="Your grown-up needs to sign in again before your character can load."
        icon={<Mascot size={96} />}
      />
    )
  }
  if (state.status === 'error') {
    return (
      <EmptyState
        title="We lost your character"
        description="Something went wrong loading your character."
        icon={<Mascot size={96} />}
        actions={
          <Button variant="primary" size="lg" onClick={() => setReloadKey((key) => key + 1)}>
            Try again
          </Button>
        }
      />
    )
  }

  const { characters } = state
  if (characters.length === 0) {
    return <CharacterCreator profileId={profileId} onCreated={handleCreated} />
  }

  return (
    <div className="character-picker">
      <h2 className="character-picker__heading">Choose your character</h2>
      {/* A plain list of toggle buttons, deliberately NOT a radiogroup. The
          ARIA radio pattern promises APG keyboard behavior (arrow keys move
          the selection, the group is a single tab stop) that this component
          does not implement: every tile is its own tab stop and there is no
          arrow-key handling. Rather than build a roving-tabindex model for
          two-to-a-handful of tiles, the markup states what the widget
          actually is, a list of independently focusable pressed/unpressed
          toggles, so the announced contract matches the real behavior. */}
      <ul className="character-picker__grid" aria-label="Choose your character">
        {characters.map((character) => {
          const isActive = character.is_active
          const busy = activatingId === character.id
          return (
            <li key={character.id} className="character-picker__grid-item">
              <button
                type="button"
                aria-pressed={isActive}
                aria-busy={busy || undefined}
                // Every tile, not just the one being activated: see the
                // #ASSUME note on `activate` above. Disabling only `busy`'s
                // own tile left every OTHER tile tappable while a request
                // was in flight, which is exactly the race that let a second
                // `activate()` start concurrently.
                disabled={activatingId !== null}
                className={isActive ? 'character-tile character-tile--selected' : 'character-tile'}
                onClick={() => {
                  if (!isActive) activate(character.id)
                }}
              >
                {/* Avatar-led, mirroring ProfilePickerPage's AvatarCircle as
                    the tile's primary visual identifier: decorative
                    (aria-hidden) since the visible name text below already
                    carries the accessible name, so the swatch is never
                    announced twice. */}
                <span className="character-tile__avatar" aria-hidden="true">
                  {LOOK_SWATCHES[character.look]}
                </span>
                <span className="character-tile__name">{character.name}</span>
                <span className="character-tile__hint">{archetypeLabel(character.archetype)}</span>
                {/* aria-pressed above already carries the selected state to
                    assistive tech; this visible text gives a sighted child
                    the same signal without relying on the selected-state
                    border color alone. */}
                {isActive ? (
                  <span className="character-tile__badge">Currently reading as</span>
                ) : null}
              </button>
            </li>
          )
        })}
      </ul>
      {activateError ? (
        <p role="alert" className="character-picker__error">
          {activateError}
        </p>
      ) : null}
    </div>
  )
}
