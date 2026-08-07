import { matchPath, Outlet, useLocation } from 'react-router'

import { CharacterCreator } from '../characters/CharacterCreator'
import { useActiveCharacter } from '../characters/useActiveCharacter'
import { ThemeToggle } from '../theme/ThemeToggle'
import { KidNav } from './KidNav'
import { useKidProfile } from './useKidProfile'
import './kid.css'

/**
 * Layout chrome for the kid surface (wireframe section 2: fully separate from
 * the guardian surface, no shared nav or auth UI bridges them).
 *
 * The persistent KidNav bar appears on the library route, where a child needs a
 * visible way to switch readers. The reader route carries its own in-story
 * "Leave" control instead, and the profile picker is itself the top of the kid
 * surface, so neither shows this bar.
 *
 * The theme toggle is the one piece of chrome that DOES float above every kid
 * route, reader included: it's the only door into this surface with no
 * shared header of its own to carry it, and a corner icon is unobtrusive
 * enough not to compete with the in-story controls.
 *
 * `data-age-band`/`data-reduce-motion` on the shell root drive band-tokens.css
 * for every descendant (library, reader): resolved from either the library or
 * reader route's profileId, since band-aware motion/typography should apply
 * while reading, not just while browsing. Absent (profile picker, a lookup
 * still in flight, or a failed lookup) leaves both attributes unset, which
 * band-tokens.css treats as the neutral tier -- never a stale prior child's
 * band.
 *
 * First-run character gate (library route only): a profile with no
 * character yet sees the creator instead of the library Outlet. Gated on
 * `status === 'none'` specifically, never on 'loading'/'error'/anything
 * else, so a lookup that is still in flight or failed cannot be
 * misread as "no character" and bounce a returning child into re-creating
 * one; see useActiveCharacter.ts's own defensiveness note.
 * #VERIFY: KidShell.test.tsx's existing library-route assertions keep
 * passing unmodified (they never produce a well-formed empty character
 * list), plus the character-gate coverage in CharacterPicker.test.tsx /
 * CharacterCreator.test.tsx for the creator itself.
 */
export function KidShell() {
  const location = useLocation()
  const libraryMatch = matchPath('/library/:profileId', location.pathname)
  const readMatch = matchPath('/read/:profileId/:storybookId/:version', location.pathname)
  const navProfileId = libraryMatch?.params.profileId
  const profile = useKidProfile(navProfileId ?? readMatch?.params.profileId)?.profile ?? null
  const activeCharacter = useActiveCharacter(libraryMatch ? navProfileId : undefined)

  // #EDGE: accessibility: while the profile lookup is in flight or has failed,
  // data-reduce-motion is unset and the guardian-set app-level reduce_motion
  // preference fails open to full motion. Accepted bound: band-tokens.css's
  // `@media (prefers-reduced-motion: reduce)` fail-safe is independent of this
  // attribute and still applies for any device with the OS-level preference.
  return (
    <div
      className="kid-shell"
      data-age-band={profile?.age_band}
      data-reduce-motion={profile?.reduce_motion ? 'true' : undefined}
    >
      {navProfileId ? <KidNav profileId={navProfileId} /> : null}
      <ThemeToggle className="kid-shell__theme-toggle" />
      <main className="kid-shell__main">
        {libraryMatch && navProfileId && activeCharacter.state.status === 'none' ? (
          <CharacterCreator profileId={navProfileId} onCreated={activeCharacter.refresh} />
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  )
}
