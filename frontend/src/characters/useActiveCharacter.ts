import { useCallback, useEffect, useRef, useState } from 'react'

import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'

import { makeCharactersApi } from './characterApi'

import type { CharacterView } from '../client/types.gen'

export type ActiveCharacterState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | { status: 'none' }
  | { status: 'ready'; character: CharacterView }

export interface UseActiveCharacterResult {
  state: ActiveCharacterState
  /** Re-runs the fetch. Call after a mutation elsewhere (CharacterPicker's own
   * create/activate calls) may have changed which character is active. */
  refresh: () => void
}

/**
 * Task 9's reader-integration deliverable: resolves which of a profile's
 * characters, if any, is currently active, mirroring the server's "at most
 * one active character per profile" invariant (a partial unique index).
 *
 * #ASSUME: data integrity: an unparseable response (missing/non-array
 * `characters`) resolves to 'error', never to 'none'. An ambiguous response
 * must never read as "this profile has no character": KidShell's first-run
 * gate treats 'none' as "safe to show the creator", and doing that on top of
 * a real, merely-unparsed character would let a child create a second one
 * while masking the first.
 * #VERIFY: useActiveCharacter.test.ts "an unparseable response never
 * resolves to 'none'".
 *
 * #EDGE: data integrity: a profile whose only characters are all retired
 * (none `is_active`) also resolves to 'none' rather than a fourth state.
 * This is a deliberate simplification: creating another character from that
 * state is non-destructive (it does not delete the retired ones), and no
 * Task 8 surface exposes retiring a character, so the state is not reachable
 * from this frontend today.
 */
export function useActiveCharacter(profileId: string | undefined): UseActiveCharacterResult {
  const api = useApi()
  const [state, setState] = useState<ActiveCharacterState>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (!profileId) return undefined
    const id = profileId
    let cancelled = false
    const charactersApi = makeCharactersApi(api)
    // The setState calls live in this nested async function, not the effect
    // body itself, per the set-state-in-effect rule (mirrors
    // LibraryPage.tsx's own load() pattern).
    async function fetchActiveCharacter() {
      setState({ status: 'loading' })
      try {
        const characters = await charactersApi.list(id)
        if (cancelled || !isMountedRef.current) return
        if (!Array.isArray(characters)) {
          setState({ status: 'error' })
          return
        }
        const active = characters.find((character) => character.is_active)
        setState(active ? { status: 'ready', character: active } : { status: 'none' })
      } catch (err) {
        logApiError('active character fetch failed', err)
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
    void fetchActiveCharacter()
    return () => {
      cancelled = true
    }
  }, [api, profileId, reloadKey])

  const refresh = useCallback(() => setReloadKey((key) => key + 1), [])

  return { state, refresh }
}
