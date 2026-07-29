import { isAxiosError } from 'axios'
import { useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { makeInviteGuardianApi } from './inviteGuardianApi'

/**
 * Guardian self-service co-parent invite (G14 register close).
 *
 * Complements the admin-mediated invite (`POST /admin/users`, WS-J admin
 * console, any family): this is the guardian-initiated counterpart, and it
 * is deliberately narrow. There is no family picker and no role choice; the
 * backend (`api/me.py::invite_guardian`) hard-scopes the invite to the
 * calling guardian's own family and always invites a plain guardian, so this
 * form is nothing more than an email field, matching that contract rather
 * than offering choices the endpoint would reject.
 *
 * A submitted invite creates a `status="pending_guardian_invite"` row, which
 * is NOT the same as the `status="pending"` row `POST /admin/users` creates.
 * A guardian can type any email address, so nobody has vetted this invitee:
 * when they first sign in with that email,
 * `api/onboarding.py::_bind_pending_invite` binds them at
 * `awaiting_approval`, and an admin must approve before they can use the
 * account. The copy below says so; promising immediate membership would be a
 * lie, and the gate is deliberate (it stops a guardian from pre-claiming a
 * stranger's address and capturing them into this family).
 *
 * This form does not attempt to show the pending invite afterward; there is
 * no guardian-facing roster view (that is the admin console's
 * `/admin/users`), so a plain success message is the honest end state.
 */
export function InviteCoParentSection() {
  const api = useApi()
  const inviteApi = useMemo(() => makeInviteGuardianApi(api), [api])
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'busy' | 'sent' | 'duplicate' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  async function submit() {
    setStatus('busy')
    setErrorMessage(null)
    try {
      await inviteApi.inviteGuardian({ email })
      setStatus('sent')
      setEmail('')
    } catch (err) {
      logApiError('guardian invite failed', err)
      // The one 409 this endpoint can return is a pending invite already
      // outstanding for this email (api/admin_users.py::create_pending_invite,
      // shared with the admin invite path); classifyApiError's generic
      // 'transient' bucket would otherwise tell a guardian to "please try
      // again" for a request that will never succeed by retrying.
      if (isAxiosError(err) && err.response?.status === 409) {
        setStatus('duplicate')
        return
      }
      setErrorMessage(classifyApiError(err).message)
      setStatus('error')
    }
  }

  return (
    <section aria-label="Invite a co-parent" className="console-invite">
      <h2>Invite a co-parent</h2>
      <p className="console__notice cyo-text-muted">
        Invite another adult to join your family account. They sign in with the email below, and an
        administrator reviews the request before they join. Once approved, they will see everything
        you see for your family.
      </p>
      <form
        className="console-invite__form"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <label className="console-invite__field cyo-field">
          <span>Co-parent&apos;s email</span>
          <input
            type="email"
            name="co-parent-email"
            autoComplete="email"
            required
            className="cyo-field__control"
            value={email}
            disabled={status === 'busy'}
            onChange={(e) => {
              setEmail(e.target.value)
              if (status !== 'idle') setStatus('idle')
            }}
          />
        </label>
        <Button type="submit" size="sm" disabled={status === 'busy' || email.trim() === ''}>
          {status === 'busy' ? 'Sending invite…' : 'Send invite'}
        </Button>
      </form>
      {status === 'sent' ? (
        <p className="console-invite__success" role="status">
          Invite sent. After they sign in with that email, an administrator approves them before
          they join your family.
        </p>
      ) : null}
      {status === 'duplicate' ? (
        <ErrorBanner className="console-invite__error">
          There is already a pending invite for that email.
        </ErrorBanner>
      ) : null}
      {status === 'error' ? (
        <ErrorBanner className="console-invite__error">
          {errorMessage ?? 'Something went wrong. Please try again.'}
        </ErrorBanner>
      ) : null}
    </section>
  )
}
