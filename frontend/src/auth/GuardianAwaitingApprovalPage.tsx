import { useCallback, useEffect, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { Navigate } from 'react-router'

import '../guardian/guardian.css'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  GUARDIAN_UNAVAILABLE_PATH,
} from '../routes'
import { useAuth } from './useAuth'

// P-6d: how often this page silently re-checks approval status in the
// background while the guardian is not actively pressing "Check again".
// Cheap (re-reads the current Supabase session, short-circuits before
// GET /v1/me while still awaiting approval; see refreshStatus's doc), so a
// modest interval is fine without adding real server load.
const AUTO_RECHECK_INTERVAL_MS = 20_000

/**
 * Shown to a self-signed-up guardian (AuthStatus 'awaiting-approval')
 * instead of the console. ProtectedRoute routes here directly.
 *
 * P-6d: this used to be a true dead end (sign out was the only escape); it
 * now re-checks status both on a background timer and via a manual "Check
 * again" button, using AuthContext's refreshStatus (re-resolves the
 * principal from the current Supabase session, the same tail recordConsent
 * already uses). Approval itself is still entirely server-side (only an
 * admin approving the account changes anything); this page just stops
 * requiring a sign-out/sign-in round trip to notice.
 *
 * #ASSUME: security: this route sits outside ProtectedRoute (see
 * router.tsx's comment on it), so a signed-out visitor or an
 * already-approved/consented guardian could land here via a direct URL, not
 * just via ProtectedRoute's redirect. Mirrors LoginPage's own defensive
 * status checks for the same reason.
 * #VERIFY: GuardianAwaitingApprovalPage.test.tsx redirect cases.
 */
export function GuardianAwaitingApprovalPage() {
  const { status, principal, signOut, refreshStatus } = useAuth()
  const [checking, setChecking] = useState(false)

  // #ASSUME: external-resources: the recheck call can fail (network,
  // session expiry). Failing silently (no error banner) is deliberate: this
  // is a convenience recheck, not a required action, and the guardian can
  // always retry or fall back to Sign out / signing back in.
  // #VERIFY: GuardianAwaitingApprovalPage.test.tsx "Check again" tests.
  const checkAgain = useCallback(async () => {
    setChecking(true)
    try {
      await refreshStatus()
    } catch (err) {
      console.error('awaiting-approval recheck failed', err instanceof Error ? err.message : err)
    } finally {
      setChecking(false)
    }
  }, [refreshStatus])

  // Hooks must run unconditionally before the status-gated early returns
  // below (rules of hooks), so the poll effect itself gates on status
  // internally instead of the component returning early first.
  useEffect(() => {
    if (status !== 'awaiting-approval') return undefined
    const id = setInterval(() => {
      void checkAgain()
    }, AUTO_RECHECK_INTERVAL_MS)
    return () => clearInterval(id)
  }, [status, checkAgain])

  if (status === 'signed-out') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }
  if (status === 'needs-consent') {
    return <Navigate to={GUARDIAN_CONSENT_PATH} replace />
  }
  // #452: this page's own background poll can produce this status, since
  // refreshStatus() runs the same resolution that now classifies an outage as
  // transient. Without this branch the poll would drop the guardian onto the
  // "not awaiting-approval, render nothing" path below and leave them looking
  // at a blank page for the duration of the outage.
  if (status === 'backend-unreachable') {
    return <Navigate to={GUARDIAN_UNAVAILABLE_PATH} replace />
  }
  if (status === 'signed-in') {
    const home = principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH
    return <Navigate to={home} replace />
  }
  if (status !== 'awaiting-approval') {
    // 'loading': AuthContext has not resolved a status yet; render nothing
    // rather than flash this page's content ahead of a redirect.
    return null
  }

  return (
    <section className="console" aria-labelledby="awaiting-approval-title">
      <h1 id="awaiting-approval-title">Almost there</h1>
      <EmptyState
        title="Your account is awaiting approval"
        description="A family administrator needs to approve your account before you can start adding profiles or requesting stories. This is usually quick -- check back soon, or come back after you've heard from them."
      />
      <p className="console__notice cyo-text-muted">
        We'll check automatically every so often, or you can check right now.
      </p>
      <p className="console__notice">
        <Button variant="ghost" size="sm" onClick={() => void checkAgain()} disabled={checking}>
          {checking ? 'Checking…' : 'Check again'}
        </Button>{' '}
        <Button variant="ghost" size="sm" onClick={() => void signOut()}>
          Sign out
        </Button>
      </p>
    </section>
  )
}
