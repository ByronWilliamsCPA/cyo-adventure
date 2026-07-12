import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import './guardian.css'

/**
 * Layout chrome for the parent surface (wireframe section 2: the guardian
 * session is fully separate from the kid surface; nothing here links to it).
 */
export function GuardianShell() {
  const { principal, signOut } = useAuth()
  const [signOutError, setSignOutError] = useState(false)

  // #EDGE: external-resources: signOut rejects when Supabase cannot revoke
  // the session (network down). Surface it so the tap doesn't silently no-op
  // while the guardian believes they signed out on a shared device.
  // #VERIFY: AuthContext.test.tsx covers signOut rejection propagation.
  async function startSignOut() {
    setSignOutError(false)
    try {
      await signOut()
    } catch {
      setSignOutError(true)
    }
  }

  // Role is 'guardian' | 'child' | 'admin' (see auth/types.ts); GuardianShell
  // only ever mounts for a guardian or admin principal in practice (routed
  // behind ProtectedRoute's role gate), but the hint is written to degrade to
  // nothing rather than mislabel a 'child' principal if that ever changes.
  const roleHint =
    principal === null
      ? null
      : principal.role === 'admin'
        ? 'Admin'
        : principal.role === 'guardian'
          ? 'Guardian'
          : null

  return (
    <div className="guardian-shell">
      <header className="guardian-shell__header">
        <span className="guardian-shell__brand">
          <span className="guardian-shell__title">CYO Adventure</span>
          {roleHint ? <span className="guardian-shell__role">{roleHint}</span> : null}
        </span>
        {principal ? (
          <button
            type="button"
            className="guardian-shell__sign-out"
            onClick={() => void startSignOut()}
          >
            Sign out
          </button>
        ) : null}
      </header>
      <nav className="guardian-shell__nav" aria-label="Guardian">
        <NavLink to="/guardian" end>
          Console
        </NavLink>
        <NavLink to="/guardian/intake">Request a story</NavLink>
        {principal?.role === 'guardian' ? (
          <NavLink to="/guardian/books">Books</NavLink>
        ) : null}
        <NavLink to="/guardian/requests">Story requests</NavLink>
        <NavLink to="/guardian/profiles">Profiles</NavLink>
      </nav>
      {signOutError ? (
        <p role="alert" className="guardian-shell__error cyo-text-error">
          Sign-out failed. Check your connection and try again.
        </p>
      ) : null}
      <main className="guardian-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
