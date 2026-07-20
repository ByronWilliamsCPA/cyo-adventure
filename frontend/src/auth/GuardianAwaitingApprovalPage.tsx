import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { Navigate } from 'react-router-dom'

import '../guardian/guardian.css'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
} from '../routes'
import { useAuth } from './useAuth'

/**
 * Shown to a self-signed-up guardian (AuthStatus 'awaiting-approval')
 * instead of the console. ProtectedRoute routes here directly; nothing on
 * this page can proceed past it (no polling, no retry-past-the-gate) since
 * only an admin approving the account server-side changes anything. Signing
 * out and back in re-runs AuthContext's onboarding check, which is the only
 * way this page's guardian would ever see it clear.
 *
 * #ASSUME: security: this route sits outside ProtectedRoute (see
 * router.tsx's comment on it), so a signed-out visitor or an
 * already-approved/consented guardian could land here via a direct URL, not
 * just via ProtectedRoute's redirect. Mirrors LoginPage's own defensive
 * status checks for the same reason.
 * #VERIFY: GuardianAwaitingApprovalPage.test.tsx redirect cases.
 */
export function GuardianAwaitingApprovalPage() {
  const { status, principal, signOut } = useAuth()

  if (status === 'signed-out') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }
  if (status === 'needs-consent') {
    return <Navigate to={GUARDIAN_CONSENT_PATH} replace />
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
        <Button variant="ghost" size="sm" onClick={() => void signOut()}>
          Sign out
        </Button>
      </p>
    </section>
  )
}
