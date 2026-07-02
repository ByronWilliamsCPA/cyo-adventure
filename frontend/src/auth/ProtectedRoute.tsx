import { Navigate, Outlet, useLocation } from 'react-router-dom'

import type { Role } from './types'
import { useAuth } from './useAuth'

interface ProtectedRouteProps {
  /** Redirect target when unauthenticated or role-mismatched. */
  redirectTo: string
  /** When set, the principal's role must be one of these, not just any authenticated role. */
  allowedRoles?: Role[]
}

/**
 * Route guard: renders the nested route tree only for a signed-in principal
 * whose role (if restricted) is allowed. Redirects to redirectTo otherwise,
 * carrying the attempted location so a login page can return the user here.
 */
export function ProtectedRoute({ redirectTo, allowedRoles }: ProtectedRouteProps) {
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
    return <Navigate to={redirectTo} replace />
  }

  return <Outlet />
}
