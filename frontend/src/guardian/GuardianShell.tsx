import { Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import './guardian.css'

/**
 * Layout chrome for the parent surface (wireframe section 2: the guardian
 * session is fully separate from the kid surface; nothing here links to it).
 */
export function GuardianShell() {
  const { principal, signOut } = useAuth()

  return (
    <div className="guardian-shell">
      <header className="guardian-shell__header">
        <span className="guardian-shell__title">CYO Adventure</span>
        {principal ? (
          <button type="button" className="guardian-shell__sign-out" onClick={() => void signOut()}>
            Sign out
          </button>
        ) : null}
      </header>
      <main className="guardian-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
