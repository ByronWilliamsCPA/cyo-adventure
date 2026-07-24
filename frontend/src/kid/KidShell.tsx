import { matchPath, Outlet, useLocation } from 'react-router-dom'

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
 * `data-age-band`/`data-reduce-motion` on the shell root drive band-tokens.css
 * for every descendant (library, reader): resolved from either the library or
 * reader route's profileId, since band-aware motion/typography should apply
 * while reading, not just while browsing. Absent (profile picker, a lookup
 * still in flight, or a failed lookup) leaves both attributes unset, which
 * band-tokens.css treats as the neutral tier -- never a stale prior child's
 * band.
 */
export function KidShell() {
  const location = useLocation()
  const libraryMatch = matchPath('/library/:profileId', location.pathname)
  const readMatch = matchPath('/read/:profileId/:storybookId/:version', location.pathname)
  const navProfileId = libraryMatch?.params.profileId
  const profile = useKidProfile(navProfileId ?? readMatch?.params.profileId)?.profile ?? null

  return (
    <div
      className="kid-shell"
      data-age-band={profile?.age_band}
      data-reduce-motion={profile?.reduce_motion ? 'true' : undefined}
    >
      {navProfileId ? <KidNav profileId={navProfileId} /> : null}
      <main className="kid-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
