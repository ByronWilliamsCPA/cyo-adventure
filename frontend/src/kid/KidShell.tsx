import { Outlet } from 'react-router-dom'

import './kid.css'

/**
 * Layout chrome for the kid surface (wireframe section 2: fully separate
 * from the guardian surface, no shared nav or auth UI bridges them).
 */
export function KidShell() {
  return (
    <div className="kid-shell">
      <main className="kid-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
