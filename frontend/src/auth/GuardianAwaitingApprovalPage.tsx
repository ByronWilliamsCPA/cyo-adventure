import { useCallback, useEffect, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { Link, Navigate } from 'react-router'

import '../guardian/guardian.css'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  GUARDIAN_UNAVAILABLE_PATH,
  GUARDIAN_VERIFICATION_PATH,
  SUPPORT_PATH,
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
  usePageTitle('Awaiting Approval')
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
  // Verification precedes approval, so this is a step BACKWARD: it happens
  // when a verification lapses or is revoked while this page is open, and the
  // poll below is what notices.
  if (status === 'needs-verification') {
    return <Navigate to={GUARDIAN_VERIFICATION_PATH} replace />
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
      {/* UW-J28: the description used to say "A family administrator needs to approve your
          account ... come back after you've heard from them". Both halves misled. Approval is
          granted by a platform administrator (PATCH /api/v1/admin/users/{id}, admin-only), not by
          anyone in this family, so a guardian went looking for a person who does not exist; and
          nothing in the flow messages them when approval lands, so "heard from them" promised a
          notification that is not sent (registered as UW-J29). The copy now names who acts, and
          says plainly that this page is the thing that notices.
          The support link is the other half of this row: this is the one screen in onboarding a
          guardian can be stuck on indefinitely, and it had no route anywhere. SUPPORT_PATH is
          public and outside every auth gate by construction (see routes.ts), which is exactly why
          it is safe to offer to a caller whose account require_principal still refuses. */}
      <EmptyState
        title="Your account is awaiting approval"
        description="Someone on the CYO Adventure team reviews each new account before it can add child profiles or request stories. Nobody in your family needs to do anything, and you do not need to wait on this page: we check every few seconds while it is open, and you can close it and come back."
        actions={
          <Link className="console__cta" to={SUPPORT_PATH}>
            Waiting longer than expected? Contact support
          </Link>
        }
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
