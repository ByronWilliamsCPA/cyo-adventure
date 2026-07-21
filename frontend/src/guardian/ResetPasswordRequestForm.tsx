import { useState } from 'react'

import { useAuth } from '../auth/useAuth'
import { logApiError } from '../hooks/logApiError'
import './guardian.css'

/**
 * The "email me a reset link" step of the guardian password-recovery flow.
 * Rendered by LoginPage while its `showReset` panel is open (toggled by the
 * "Forgot your password?" button, which stays in LoginPage since it is the
 * panel's visibility control, not part of the form itself). This component
 * owns only the request itself; the return leg (setting the new password once
 * the emailed link is followed) is the separate {@link SetNewPasswordForm}.
 */
export function ResetPasswordRequestForm() {
  const { requestPasswordReset } = useAuth()
  const [resetEmail, setResetEmail] = useState('')
  const [resetStatus, setResetStatus] = useState<'idle' | 'sent' | 'error'>('idle')
  const [resetSubmitting, setResetSubmitting] = useState(false)

  // #ASSUME: security: requestPasswordReset resolves whether or not the address
  // is registered (Supabase does not disclose it), so a resolution always maps
  // to the neutral "if an account exists" confirmation, never a "sent" that
  // would confirm the email. Only an operational rejection (rate limit, network,
  // 5xx) surfaces a distinct, retryable connection error. Enumeration-resistant
  // by construction, matching the login form's generic-credentials stance.
  // #VERIFY: ResetPasswordRequestForm.test.tsx forgot-password
  // neutral-confirmation + error cases.
  async function submitReset() {
    setResetStatus('idle')
    setResetSubmitting(true)
    try {
      await requestPasswordReset(resetEmail)
      setResetStatus('sent')
    } catch (err) {
      // The user-facing message stays the same generic "couldn't send a
      // reset link" regardless of cause (no enumeration leak either way);
      // logging the real cause here is what makes a genuine bug
      // distinguishable from a transient network blip in production
      // monitoring, since nothing else observes this rejection.
      logApiError('password-reset request failed', err)
      setResetStatus('error')
    } finally {
      setResetSubmitting(false)
    }
  }

  return (
    <form
      className="guardian-login__form"
      onSubmit={(event) => {
        event.preventDefault()
        void submitReset()
      }}
    >
      <label className="guardian-login__field cyo-field">
        <span>Email for reset link</span>
        <input
          type="email"
          name="reset-email"
          autoComplete="email"
          required
          className="cyo-field__control"
          value={resetEmail}
          onChange={(e) => setResetEmail(e.target.value)}
        />
      </label>
      <button type="submit" className="guardian-login__provider" disabled={resetSubmitting}>
        {resetSubmitting ? 'Sending...' : 'Send reset link'}
      </button>
      {resetStatus === 'sent' ? (
        <p role="status" aria-live="polite" className="guardian-login__note">
          If an account exists for that email, we&apos;ve sent a reset link. Check your inbox.
        </p>
      ) : null}
      {resetStatus === 'error' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          We couldn&apos;t send a reset link. Check your connection and try again.
        </p>
      ) : null}
    </form>
  )
}
