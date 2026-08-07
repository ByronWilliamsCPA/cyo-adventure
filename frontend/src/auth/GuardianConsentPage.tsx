import { useId, useState } from 'react'
import { Navigate } from 'react-router'

import { Button } from '@ds/components/Button'
import '../guardian/guardian.css'
import { classifyApiError } from '../hooks/classifyApiError'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_AWAITING_APPROVAL_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  GUARDIAN_UNAVAILABLE_PATH,
} from '../routes'
import { RESIDENCE_COUNTRIES } from './residenceCountries'
import { useAuth } from './useAuth'

const SUBMIT_ERROR = 'That did not go through. Please try again.'

/**
 * The Phase 2 / ADR-018 D1 verifiable-parental-consent step: shown to an
 * approved guardian (AuthStatus 'needs-consent') before they can reach any
 * other guardian page. A typed full-legal-name attestation plus an explicit
 * checkbox, layered on the Supabase/Google OAuth login that already
 * authenticated this session -- no signature-image capture (see ADR-018
 * D1's decision record for why: no PCI scope, no third-party vendor).
 *
 * Also carries two pre-launch compliance fields on the same form and the
 * same submission: O-117 (country of residence, a required <select>) and
 * O-119 (an adulthood attestation checkbox, distinct from the guardianship
 * checkbox above -- see db/models.py::User's residence_country /
 * adulthood_attested_at comments for why these are new columns rather than
 * a reinterpretation of the existing guardianship attestation).
 *
 * #ASSUME: security: this route sits outside ProtectedRoute (see
 * router.tsx's comment on it), so a signed-out visitor or an
 * already-approved/consented guardian could land here via a direct URL, not
 * just via ProtectedRoute's redirect. Mirrors LoginPage's own defensive
 * status checks for the same reason.
 * #VERIFY: GuardianConsentPage.test.tsx redirect cases.
 */
export function GuardianConsentPage() {
  usePageTitle('Consent Required')
  const { status, principal, recordConsent } = useAuth()
  const [signerName, setSignerName] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [residenceCountry, setResidenceCountry] = useState('')
  const [adulthoodAttested, setAdulthoodAttested] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameId = useId()
  const checkboxId = useId()
  const countryId = useId()
  const adulthoodCheckboxId = useId()

  if (status === 'signed-out') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }
  // #452: recordConsent rethrows a failed submit rather than reaching
  // syncPrincipal, so this page cannot reach the status through its own
  // action; it can still arrive here from a sibling tab's poll or a direct
  // URL. Handled for the same reason as the branch on the awaiting-approval
  // page: the alternative is a blank screen from the catch-all below.
  if (status === 'backend-unreachable') {
    return <Navigate to={GUARDIAN_UNAVAILABLE_PATH} replace />
  }
  if (status === 'awaiting-approval') {
    return <Navigate to={GUARDIAN_AWAITING_APPROVAL_PATH} replace />
  }
  if (status === 'signed-in') {
    const home = principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH
    return <Navigate to={home} replace />
  }
  if (status !== 'needs-consent') {
    // 'loading': AuthContext has not resolved a status yet; render nothing
    // rather than flash this page's content ahead of a redirect.
    return null
  }

  const trimmedName = signerName.trim()
  // #ASSUME: data-integrity: client-side length floor only (matches the
  // backend's real gate: onboarding.py::_record_consent 422s on an empty
  // signer_name). A determined caller can still bypass this input and hit
  // the API directly with a one-character name; the backend does not
  // enforce a minimum beyond non-empty, so neither does this form.
  // #VERIFY: GuardianConsentPage.test.tsx pins that submit stays disabled
  // until the name field is non-empty.
  // #ASSUME: data-integrity: O-117/O-119: residenceCountry and
  // adulthoodAttested are equally required gates on submit, mirroring
  // signerName/agreed above -- the backend rejects a consent payload
  // missing either (onboarding.py::_record_consent), so the form does not
  // let a guardian reach that 422.
  // #VERIFY: GuardianConsentPage.test.tsx pins that submit stays disabled
  // until both residenceCountry and adulthoodAttested are set.
  const canSubmit =
    trimmedName.length > 0 && agreed && residenceCountry.length > 0 && adulthoodAttested && !busy

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await recordConsent(trimmedName, residenceCountry)
      // #ASSUME: timing dependencies: no local success state to set here --
      // recordConsent's own syncPrincipal call transitions AuthStatus to
      // 'signed-in' on success, and ProtectedRoute (this page's caller)
      // re-renders past this component automatically once that happens.
      // #VERIFY: GuardianConsentPage.test.tsx "submits the trimmed typed
      // name on agree" passes without this component setting any local
      // success state.
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
        Because CYO Adventure creates profiles and stories for children, we need your confirmation
        that you are this child&apos;s parent or legal guardian and that you agree to how we handle
        their information, described in our Privacy Notice.
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
        <label
          className="guardian-login__field guardian-login__field--checkbox"
          htmlFor={checkboxId}
        >
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
        <label className="guardian-login__field" htmlFor={countryId}>
          <span>Your country of residence</span>
          <select
            id={countryId}
            value={residenceCountry}
            onChange={(event) => setResidenceCountry(event.target.value)}
            disabled={busy}
            required
          >
            <option value="" disabled>
              Select a country
            </option>
            {RESIDENCE_COUNTRIES.map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </select>
        </label>
        <label
          className="guardian-login__field guardian-login__field--checkbox"
          htmlFor={adulthoodCheckboxId}
        >
          <input
            id={adulthoodCheckboxId}
            type="checkbox"
            checked={adulthoodAttested}
            onChange={(event) => setAdulthoodAttested(event.target.checked)}
            disabled={busy}
          />
          <span>I confirm that I am an adult.</span>
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
