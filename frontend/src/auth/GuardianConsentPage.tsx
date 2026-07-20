import { useId, useState } from 'react'

import { Button } from '@ds/components/Button'
import '../guardian/guardian.css'
import { classifyApiError } from '../hooks/classifyApiError'
import { useAuth } from './useAuth'

const SUBMIT_ERROR = 'That did not go through. Please try again.'

/**
 * The Phase 2 / ADR-018 D1 verifiable-parental-consent step: shown to an
 * approved guardian (AuthStatus 'needs-consent') before they can reach any
 * other guardian page. A typed full-legal-name attestation plus an explicit
 * checkbox, layered on the Supabase/Google OAuth login that already
 * authenticated this session -- no signature-image capture (see ADR-018
 * D1's decision record for why: no PCI scope, no third-party vendor).
 */
export function GuardianConsentPage() {
  const { recordConsent } = useAuth()
  const [signerName, setSignerName] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameId = useId()
  const checkboxId = useId()

  const trimmedName = signerName.trim()
  // #ASSUME: data-integrity: client-side length floor only (matches the
  // backend's real gate: onboarding.py::_record_consent 422s on an empty
  // signer_name). A determined caller can still bypass this input and hit
  // the API directly with a one-character name; the backend does not
  // enforce a minimum beyond non-empty, so neither does this form.
  const canSubmit = trimmedName.length > 1 && agreed && !busy

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await recordConsent(trimmedName)
      // #ASSUME: timing dependencies: no local success state to set here --
      // recordConsent's own syncPrincipal call transitions AuthStatus to
      // 'signed-in' on success, and ProtectedRoute (this page's caller)
      // re-renders past this component automatically once that happens.
    } catch (err) {
      console.error('consent submission failed:', err instanceof Error ? err.message : err)
      setError(classifyApiError(err, { transient: SUBMIT_ERROR, server: SUBMIT_ERROR }).message)
      setBusy(false)
    }
  }

  return (
    <section className="console" aria-labelledby="consent-title">
      <h1 id="consent-title">Before you get started</h1>
      <p className="console__notice cyo-text-muted">
        Because CYO Adventure creates profiles and stories for children, we need your
        confirmation that you are this child&apos;s parent or legal guardian and that you
        agree to how we handle their information, described in our Privacy Notice.
      </p>
      <form className="guardian-login__form" onSubmit={(event) => void submit(event)}>
        <label className="guardian-login__field" htmlFor={nameId}>
          <span>Your full legal name</span>
          <input
            id={nameId}
            type="text"
            autoComplete="name"
            value={signerName}
            onChange={(event) => setSignerName(event.target.value)}
            disabled={busy}
            required
          />
        </label>
        <label className="guardian-login__field guardian-login__field--checkbox" htmlFor={checkboxId}>
          <input
            id={checkboxId}
            type="checkbox"
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
            disabled={busy}
          />
          <span>
            I am this child&apos;s parent or legal guardian, and typing my name above is my
            electronic signature agreeing to CYO Adventure&apos;s Privacy Notice.
          </span>
        </label>
        {error ? (
          <p role="alert" className="cyo-text-error">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" disabled={!canSubmit}>
          {busy ? 'Submitting…' : 'Agree and continue'}
        </Button>
      </form>
    </section>
  )
}
