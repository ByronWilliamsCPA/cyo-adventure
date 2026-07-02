import { useState } from 'react'
import { Outlet } from 'react-router-dom'

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

  return (
    <div className="guardian-shell">
      <header className="guardian-shell__header">
        <span className="guardian-shell__title">CYO Adventure</span>
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
      {signOutError ? (
        <p role="alert" className="guardian-shell__error">
          Sign-out failed. Check your connection and try again.
        </p>
      ) : null}
      <main className="guardian-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
