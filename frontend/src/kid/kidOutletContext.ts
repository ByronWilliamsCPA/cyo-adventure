import { useOutletContext } from 'react-router'

import type { UseActiveCharacterResult } from '../characters/useActiveCharacter'

/**
 * What KidShell hands its routed children through the Outlet.
 *
 * `activeCharacter` is resolved once per library visit by the shell rather
 * than a second time inside LibraryPage, which would otherwise issue a
 * duplicate `GET /v1/characters` on the surface most likely to be on a slow
 * home connection. Only the library route resolves one; every other kid
 * route passes null.
 *
 * Lives in its own module rather than in KidShell.tsx so a routed page can
 * read the context without importing the shell component (and, with it, the
 * whole kid chrome) into its own lazily-loaded chunk.
 */
export interface KidOutletContext {
  activeCharacter: UseActiveCharacterResult | null
}

/**
 * Reads KidShell's Outlet context from a routed kid page.
 *
 * #ASSUME: data integrity: returns null when the page is mounted outside
 * KidShell. The guardian preview-as-child route renders LibraryPage under
 * GuardianShell, whose Outlet provides no context at all, so callers must
 * keep their own fallback rather than assuming the shell is always above
 * them.
 * #VERIFY: LibraryPage.test.tsx "fetches its own active character when
 * mounted outside KidShell".
 */
export function useKidOutletContext(): KidOutletContext | null {
  return useOutletContext<KidOutletContext | null>()
}
