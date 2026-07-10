import { matchPath, Outlet, useLocation } from 'react-router-dom'

import { KidNav } from './KidNav'
import './kid.css'

/**
 * Layout chrome for the kid surface (wireframe section 2: fully separate from
 * the guardian surface, no shared nav or auth UI bridges them).
 *
 * The persistent KidNav bar appears on the library route, where a child needs a
 * visible way to switch readers. The reader route carries its own in-story
 * "Leave" control instead, and the profile picker is itself the top of the kid
 * surface, so neither shows this bar.
 */
export function KidShell() {
  const location = useLocation()
  const libraryMatch = matchPath('/library/:profileId', location.pathname)
  const profileId = libraryMatch?.params.profileId

  return (
    <div className="kid-shell">
      {profileId ? <KidNav profileId={profileId} /> : null}
      <main className="kid-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
