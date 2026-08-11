import { matchPath, Outlet, useLocation } from 'react-router'

import { SkipLink } from '@ds/components/SkipLink'
import { useActiveCharacter } from '../characters/useActiveCharacter'
import { ThemeToggle } from '../theme/ThemeToggle'
import { KidNav } from './KidNav'
import { useKidProfile } from './useKidProfile'
import './kid.css'

import type { KidOutletContext } from './kidOutletContext'

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
 * Character lookup (library route only): resolved here and handed down
 * through the Outlet context so the library route can decide, per book,
 * whether opening it needs a character first (LibraryPage.tsx's
 * `accepts_character` gate). This shell never gates the route itself on the
 * result; the library Outlet always renders. An earlier version of this
 * branch swapped the whole library for CharacterCreator whenever a profile
 * had no character yet, hard-gating every kid into creating one before
 * reaching their library even though zero catalog books could use one and
 * there was no skip affordance. The owner rejected that: the creator now
 * appears only when a child opens a book that actually declares
 * `accepts_character`, decided at the book, not the route.
 * #VERIFY: KidShell.test.tsx's "KidShell library route character lookup"
 * suite, whose first case ("renders the library Outlet even when the
 * profile has no character") fails if this method regresses to swapping the
 * Outlet for the creator again; the remaining cases pin that the lookup
 * still only runs on the library route and still hands its result through
 * the Outlet context regardless of status ('ready'/'loading'/'error').
 */
export function KidShell() {
  const location = useLocation()
  const libraryMatch = matchPath('/library/:profileId', location.pathname)
  const readMatch = matchPath('/read/:profileId/:storybookId/:version', location.pathname)
  const navProfileId = libraryMatch?.params.profileId
  const profile = useKidProfile(navProfileId ?? readMatch?.params.profileId)?.profile ?? null
  const activeCharacter = useActiveCharacter(libraryMatch ? navProfileId : undefined)
  // Handed to the library route so it reuses this one lookup instead of
  // issuing its own identical GET /v1/characters. Null off the library
  // route, where this shell never fetches one in the first place. Not
  // memoized: `useActiveCharacter` returns a fresh result object on every
  // render anyway, so a useMemo here would signal a stability it cannot
  // deliver. No consumer puts this value in a dependency array.
  const outletContext: KidOutletContext = {
    activeCharacter: libraryMatch ? activeCharacter : null,
  }

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
      <SkipLink targetId="kid-shell-main" />
      {navProfileId ? <KidNav profileId={navProfileId} /> : null}
      <ThemeToggle className="kid-shell__theme-toggle" />
      <main id="kid-shell-main" className="kid-shell__main" tabIndex={-1}>
        <Outlet context={outletContext} />
      </main>
    </div>
  )
}
