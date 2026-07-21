import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingStatus } from '@ds/components/LoadingStatus'
import { GUARDIAN_AWAITING_APPROVAL_PATH, GUARDIAN_CONSENT_PATH, KID_PICKER_PATH } from '../routes'
import type { Principal, Role } from './types'
import { useAuth } from './useAuth'

/**
 * Capability check for one allowed-roles entry. 'admin' means the admin
 * CAPABILITY (`principal.isAdmin`), not the base persona, so a dual-role
 * adult (role='guardian', isAdmin=true) passes both a ['guardian'] gate and
 * an ['admin'] gate, mirroring the backend's Principal.is_admin model.
 */
function holdsCapability(principal: Principal, allowed: Role): boolean {
  return allowed === 'admin' ? principal.isAdmin : principal.role === allowed
}

interface ProtectedRouteProps {
  /** Redirect target when unauthenticated (carries the attempted location). */
  redirectTo: string
  /**
   * When set, the principal must hold at least one of these capabilities
   * (see {@link holdsCapability}), not just any authenticated role.
   */
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
      <LoadingStatus />
    )
  }

  // A real Supabase session exists in both cases below (AdultGate's own,
  // independent session check already passed) -- send the guardian to the
  // matching interstitial rather than looping them through login, which
  // would just re-establish the same session and land back here.
  if (status === 'awaiting-approval') {
    return <Navigate to={GUARDIAN_AWAITING_APPROVAL_PATH} replace />
  }
  if (status === 'needs-consent') {
    return <Navigate to={GUARDIAN_CONSENT_PATH} replace />
  }

  if (status !== 'signed-in' || principal === null) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />
  }

  if (allowedRoles && !allowedRoles.some((role) => holdsCapability(principal, role))) {
    // A signed-in principal with the wrong role: send them somewhere they can
    // be (deniedRedirectTo, default the kid picker), NOT redirectTo. redirectTo
    // is the login page, which redirects an already-signed-in user back here and
    // loops.
    return <Navigate to={deniedRedirectTo} replace />
  }

  return <Outlet />
}
