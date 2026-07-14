import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import {
  AUTHORIZE_DEVICE_INTENT_PARAM,
  AUTHORIZE_DEVICE_INTENT_VALUE,
  GUARDIAN_LOGIN_PATH,
} from '../routes'
import { logApiError } from '../hooks/logApiError'
import { hasValidDeviceGrant, hydrateDeviceGrant } from './deviceGrant'
import { parkAdultGate } from './parentalGateState'

type GateStatus = 'checking' | 'authorized' | 'unauthorized'

/**
 * Route guard for the entire kid surface (ADR-014 Phase 4): wraps `/kids`,
 * `/library/:profileId`, and `/read/*` so none of them render without a
 * valid, local device grant. Deliberately does NOT use `useAuth` or import
 * anything under `auth/` that reaches `supabaseClient` (AuthContext,
 * AdultGate): this component lives in the kid chunk's import graph
 * (router.tsx wraps KidShell's children with it), and the kid chunk must
 * never pull in @supabase/supabase-js (see router.tsx's header comment and
 * GuardianAuthLayout.tsx). `deviceGrant.ts` and `parentalGateState.ts` are
 * both Supabase-free for the same reason.
 *
 * The common case (a valid grant already in localStorage) renders `<Outlet
 * />` on the first render with no async work. When localStorage holds
 * nothing valid, a brief "checking" state covers the async IndexedDB-mirror
 * fallback (offline resilience: a localStorage clear should not strand an
 * otherwise-valid grant); only after that resolves to nothing does this
 * redirect to guardian login.
 *
 * #CRITICAL: security: entering the kid surface PARKS the adult gate
 * (ADR-014 Phase 5) so a device that goes from adult hands to a child's and
 * back always re-demands the grown-up password on the way up, regardless of
 * how much of the step-up's TTL window was left. Parking here (not just on
 * sign-out) is what makes "hand the tablet to a kid, take it back a minute
 * later" behave like a boundary crossing instead of a no-op.
 * #VERIFY: AdultGate.test.tsx / DeviceAuthorizedRoute.test.tsx "entering the
 * kid surface parks the adult gate".
 */
export function DeviceAuthorizedRoute() {
  const location = useLocation()
  const [status, setStatus] = useState<GateStatus>(() =>
    hasValidDeviceGrant() ? 'authorized' : 'checking'
  )

  useEffect(() => {
    if (status !== 'checking') return
    let cancelled = false
    void hydrateDeviceGrant()
      .then((grant) => {
        if (cancelled) return
        setStatus(grant ? 'authorized' : 'unauthorized')
      })
      .catch((err: unknown) => {
        // #CRITICAL: security: fail closed. A rejected IndexedDB-mirror read
        // (private-mode/quota/corruption) must NOT leave status on 'checking',
        // which strands the child on the "Loading…" screen indefinitely. Drop
        // to 'unauthorized' so the guard bounces to guardian login instead of
        // hanging on an unusable device.
        // #VERIFY: DeviceAuthorizedRoute.test.tsx "fails closed when device
        // grant hydration rejects".
        if (cancelled) return
        logApiError('device grant hydration failed', err)
        setStatus('unauthorized')
      })
    return () => {
      cancelled = true
    }
  }, [status])

  useEffect(() => {
    if (status === 'authorized') parkAdultGate()
  }, [status])

  if (status === 'checking') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }

  if (status === 'unauthorized') {
    // #ASSUME: security: the intent marker is read-only routing metadata for
    // a future login flow (Phase 5/6); it never authorizes anything itself.
    // `from` lets a future flow return the guardian to `/kids` after
    // authorizing, mirroring ProtectedRoute's `state.from` convention.
    // #VERIFY: DeviceAuthorizedRoute.test.tsx "redirects to guardian login
    // with the authorize-device intent marker".
    return (
      <Navigate
        to={`${GUARDIAN_LOGIN_PATH}?${AUTHORIZE_DEVICE_INTENT_PARAM}=${AUTHORIZE_DEVICE_INTENT_VALUE}`}
        state={{ from: location }}
        replace
      />
    )
  }

  return <Outlet />
}
