import { useState } from 'react'

import { useAuth } from '../auth/useAuth'
import './guardian.css'

/**
 * Minimum password length enforced client-side.
 *
 * #ASSUME: data-integrity: intended to be kept at or below the Supabase
 * project's own minimum so a value this form accepts is never rejected by the
 * backend for length alone; not verified against the live project config. A
 * stricter server policy still surfaces via the updatePassword rejection path
 * below (shown verbatim, see submit()'s catch block).
 * #VERIFY: confirm this project's Supabase dashboard > Authentication >
 * Policies minimum password length matches or is below 8; lower this
 * constant if not.
 */
const MIN_PASSWORD_LENGTH = 8

type SetNewPasswordFormError =
  | { kind: 'mismatch' }
  | { kind: 'too-short' }
  | { kind: 'server'; message: string }

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
  const [error, setError] = useState<SetNewPasswordFormError | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError({ kind: 'too-short' })
      return
    }
    if (newPassword !== confirm) {
      setError({ kind: 'mismatch' })
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await updatePassword(newPassword)
      // On success the context clears `recovery`; LoginPage unmounts this form
      // and redirects. Leave `submitting` true so the button stays disabled
      // during that hand-off rather than flickering back to enabled.
    } catch (err) {
      // #ASSUME: security: updatePassword rethrows Supabase's error (weak
      // password, reused password, or an expired recovery session). Unlike
      // the login/reset forms, enumeration resistance does not apply here:
      // the guardian already holds a proven recovery session, so showing
      // Supabase's actual reason (e.g. "New password should be different
      // from the old password") lets them fix the real problem instead of
      // resubmitting the same rejected password blindly. Falls back to a
      // generic message only for a non-Error rejection.
      // #VERIFY: SetNewPasswordForm.test.tsx surfaces the real rejection
      // message and the non-Error fallback.
      setError({
        kind: 'server',
        message:
          err instanceof Error
            ? err.message
            : "We couldn't update your password. Please try again.",
      })
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
      {error?.kind === 'too-short' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          Your password must be at least {MIN_PASSWORD_LENGTH} characters.
        </p>
      ) : null}
      {error?.kind === 'mismatch' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          Those passwords don&apos;t match. Please try again.
        </p>
      ) : null}
      {error?.kind === 'server' ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          {error.message}
        </p>
      ) : null}
    </form>
  )
}
