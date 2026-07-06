import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { KID_PICKER_PATH } from '../routes'
import type { Role } from './types'
import { useAuth } from './useAuth'

interface ProtectedRouteProps {
  /** Redirect target when unauthenticated (carries the attempted location). */
  redirectTo: string
  /** When set, the principal's role must be one of these, not just any authenticated role. */
  allowedRoles?: Role[]
  /**
   * Where to send a signed-in principal whose role is NOT allowed. Defaults to
   * the kid profile picker (KID_PICKER_PATH), deliberately NOT `redirectTo` (the
   * login page): a login page redirects an already-signed-in user back here,
   * which would loop forever for a signed-in but disallowed role (e.g. a child
   * hitting /guardian).
   */
  deniedRedirectTo?: string
}

/**
 * Route guard: renders the nested route tree only for a signed-in principal
 * whose role (if restricted) is allowed. Redirects to redirectTo otherwise,
 * carrying the attempted location so a login page can return the user here.
 */
export function ProtectedRoute({
  redirectTo,
  allowedRoles,
  deniedRedirectTo = KID_PICKER_PATH,
}: ProtectedRouteProps) {
  const { status, principal } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }

  if (status !== 'signed-in' || principal === null) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />
  }

  if (allowedRoles && !allowedRoles.includes(principal.role)) {
    // A signed-in principal with the wrong role: send them somewhere they can
    // be (deniedRedirectTo, default the kid picker), NOT redirectTo. redirectTo
    // is the login page, which redirects an already-signed-in user back here and
    // loops.
    return <Navigate to={deniedRedirectTo} replace />
  }

  return <Outlet />
}
