import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import '../guardian/guardian.css'
import { useAuth } from './useAuth'

/**
 * Shown to a self-signed-up guardian (AuthStatus 'awaiting-approval')
 * instead of the console. ProtectedRoute routes here directly; nothing on
 * this page can proceed past it (no polling, no retry-past-the-gate) since
 * only an admin approving the account server-side changes anything. Signing
 * out and back in re-runs AuthContext's onboarding check, which is the only
 * way this page's guardian would ever see it clear.
 */
export function GuardianAwaitingApprovalPage() {
  const { signOut } = useAuth()

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
