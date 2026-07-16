import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { GUARDIAN_CONSOLE_PATH } from '../routes'
import '../guardian/guardian.css'
import './admin.css'

/**
 * Layout chrome for the admin console, the parallel adult surface for
 * admin-capability functions (review queue, global story-request queue,
 * moderation admin). Mirrors GuardianShell's structure and reuses its
 * stylesheet so the two consoles read as siblings (admin.css layers the
 * admin-only styles on top); an adult holding both capabilities switches
 * back to the guardian console via the nav link.
 */
export function AdminShell() {
  const { principal, signOut } = useAuth()
  const [signOutError, setSignOutError] = useState(false)

  // #EDGE: external-resources: signOut rejects when Supabase cannot revoke
  // the session (network down). Surface it so the tap doesn't silently no-op
  // while the admin believes they signed out on a shared device.
  // #VERIFY: AuthContext.test.tsx covers signOut rejection propagation.
  async function startSignOut() {
    setSignOutError(false)
    try {
      await signOut()
    } catch {
      setSignOutError(true)
    }
  }

  return (
    <div className="guardian-shell">
      <header className="guardian-shell__header">
        <span className="guardian-shell__brand">
          <span className="guardian-shell__title">CYO Adventure</span>
          <span className="guardian-shell__role">Admin</span>
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
      <nav className="guardian-shell__nav" aria-label="Admin">
        <NavLink to="/admin" end>
          Review queue
        </NavLink>
        <NavLink to="/admin/requests">Story requests</NavLink>
        <NavLink to="/admin/moderation-dashboard">Moderation dashboard</NavLink>
        <NavLink to="/admin/moderation-thresholds">Moderation thresholds</NavLink>
        {principal?.role === 'guardian' ? (
          <NavLink to={GUARDIAN_CONSOLE_PATH}>Guardian console</NavLink>
        ) : null}
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
