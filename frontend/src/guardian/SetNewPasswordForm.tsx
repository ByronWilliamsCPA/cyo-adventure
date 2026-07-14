import { useState } from 'react'

import { useAuth } from '../auth/useAuth'
import './guardian.css'

/**
 * Minimum password length enforced client-side. Kept at or below the Supabase
 * project's own minimum so a value this form accepts is never rejected by the
 * backend for length alone; a stricter server policy still surfaces via the
 * updatePassword rejection path.
 */
const MIN_PASSWORD_LENGTH = 8

/**
 * The set-new-password step of the guardian password-recovery flow. Rendered by
 * LoginPage while {@link useAuth}().recovery is set (the return leg of a
 * recovery link, where a valid recovery session already exists). It performs
 * only client-side checks (both entries match, minimum length) and delegates
 * the actual change to updatePassword; on success updatePassword clears the
 * recovery flag, which lets LoginPage auto-continue to the console, so this
 * component never navigates itself.
 */
export function SetNewPasswordForm() {
  const { updatePassword } = useAuth()
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<'mismatch' | 'too-short' | 'server' | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError('too-short')
      return
    }
    if (newPassword !== confirm) {
      setError('mismatch')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await updatePassword(newPassword)
      // On success the context clears `recovery`; LoginPage unmounts this form
      // and redirects. Leave `submitting` true so the button stays disabled
      // during that hand-off rather than flickering back to enabled.
    } catch {
      // #ASSUME: security: updatePassword rethrows Supabase's error (weak
      // password, reused password, or an expired recovery session). Show a
      // retryable message rather than leaking the specific reason.
      // #VERIFY: SetNewPasswordForm.test.tsx surfaces a server-side failure.
      setError('server')
      setSubmitting(false)
    }
  }

  return (
    <form
      className="guardian-login__form"
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <h1>Choose a new password</h1>
      <p>Enter a new password for your account.</p>
      <label className="guardian-login__field cyo-field">
        <span>New password</span>
        <input
          type="password"
          name="new-password"
          autoComplete="new-password"
          required
          className="cyo-field__control"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </label>
      <label className="guardian-login__field cyo-field">
        <span>Confirm password</span>
        <input
          type="password"
          name="confirm-password"
          autoComplete="new-password"
          required
          className="cyo-field__control"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </label>
      <button type="submit" className="guardian-login__provider" disabled={submitting}>
        {submitting ? 'Saving...' : 'Set new password'}
      </button>
      {error === 'too-short' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          Your password must be at least {MIN_PASSWORD_LENGTH} characters.
        </p>
      ) : null}
      {error === 'mismatch' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          Those passwords don&apos;t match. Please try again.
        </p>
      ) : null}
      {error === 'server' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          We couldn&apos;t update your password. Please try again.
        </p>
      ) : null}
    </form>
  )
}
