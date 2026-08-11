import { useCallback, useEffect, useId, useState } from 'react'
import { Navigate } from 'react-router'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import '../guardian/guardian.css'
import { classifyApiError } from '../hooks/classifyApiError'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_AWAITING_APPROVAL_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  GUARDIAN_UNAVAILABLE_PATH,
} from '../routes'
import { RESIDENCE_COUNTRIES } from './residenceCountries'
import { useAuth } from './useAuth'

/**
 * How often the wait state re-checks whether KWS has resolved the attempt.
 *
 * Matches GuardianAwaitingApprovalPage's interval, and for the same reason:
 * the recheck short-circuits before GET /v1/me for a caller in this state, so
 * it costs one onboarding round trip. Slower than that would leave a parent
 * who just clicked the email staring at a stale screen; faster buys nothing,
 * because the thing being waited on is a human reading their inbox.
 */
const AUTO_RECHECK_INTERVAL_MS = 20_000

const START_ERROR = 'We could not send that email. Please try again.'

/**
 * Copy for the two refusals the start endpoint returns by design. Neither is
 * a fault, so neither gets the generic error text: a parent who is told "that
 * did not go through" after we DID send them an email will sit waiting for a
 * second one that is never coming.
 */
const ALREADY_SENT =
  'We have already emailed you a verification link. Please check your inbox, including spam, before asking for another.'
const TOO_MANY =
  'That is as many verification emails as we can send for now. Please check your inbox, including spam, and try again later.'

/**
 * The KWS parent-verification interstitial (ADR-018 D1), shown to an adult in
 * AuthStatus 'needs-verification'. Two faces behind one route:
 *
 * - no attempt yet ('none'): collect the country KWS needs, and send.
 * - an attempt in flight ('pending'): tell them to go read their email, and
 *   poll for the result.
 *
 * The parent finishes verification entirely outside this app. They follow the
 * emailed link into Epic's own hosted flow, and KWS reports the outcome to
 * `api/kws_webhook.py` server-to-server; the browser's return leg lands on a
 * backend-rendered page, not here. So this page cannot observe success
 * directly and does not try: it re-runs the ordinary onboarding resolution
 * and waits for the answer to change, exactly like the approval page above
 * it in the sequence.
 *
 * #ASSUME: security: this route sits outside ProtectedRoute (see router.tsx's
 * comment on it), so a signed-out visitor, or an adult who is already
 * verified, can land here via a direct URL rather than only via
 * ProtectedRoute's redirect. Mirrors the defensive status checks on the
 * awaiting-approval and consent pages for the same reason.
 * #VERIFY: GuardianVerificationPage.test.tsx redirect cases.
 */
export function GuardianVerificationPage() {
  usePageTitle('Verify You Are an Adult')
  const { status, principal, verificationStatus, startVerification, refreshStatus, signOut } =
    useAuth()
  const [country, setCountry] = useState('')
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const countryId = useId()

  // #ASSUME: external-resources: a failed recheck is swallowed, same as the
  // awaiting-approval page's poll. It is a convenience on top of a process
  // that completes server-side regardless, and an error banner that appears
  // on a timer the parent did not trigger reads as a failure of the thing
  // they ARE waiting for.
  // #VERIFY: GuardianVerificationPage.test.tsx "Check again" tests.
  const checkAgain = useCallback(async () => {
    setChecking(true)
    try {
      await refreshStatus()
    } catch (err) {
      console.error('verification recheck failed', err instanceof Error ? err.message : err)
    } finally {
      setChecking(false)
    }
  }, [refreshStatus])

  // Hooks run unconditionally, ahead of the status-gated returns below (rules
  // of hooks), so the effect gates internally instead. It polls only in the
  // waiting state: with no attempt in flight there is nothing whose result
  // could arrive, so a timer there would be pure noise.
  useEffect(() => {
    if (status !== 'needs-verification' || verificationStatus !== 'pending') return undefined
    const id = setInterval(() => {
      void checkAgain()
    }, AUTO_RECHECK_INTERVAL_MS)
    return () => clearInterval(id)
  }, [status, verificationStatus, checkAgain])

  if (status === 'signed-out') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }
  // The poll above runs the same resolution that classifies an outage as
  // transient, so this page can reach 'backend-unreachable' on its own. Left
  // unhandled it would fall through to the render-nothing branch below and
  // show a blank page for the length of the outage.
  if (status === 'backend-unreachable') {
    return <Navigate to={GUARDIAN_UNAVAILABLE_PATH} replace />
  }
  // The three states that come AFTER this one in the sequence. A parent whose
  // verification resolves while this page is open leaves through here, which
  // is the normal exit rather than an edge case: the poll is what notices.
  if (status === 'awaiting-approval') {
    return <Navigate to={GUARDIAN_AWAITING_APPROVAL_PATH} replace />
  }
  if (status === 'needs-consent') {
    return <Navigate to={GUARDIAN_CONSENT_PATH} replace />
  }
  if (status === 'signed-in') {
    const home = principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH
    return <Navigate to={home} replace />
  }
  if (status !== 'needs-verification') {
    // 'loading': AuthContext has not resolved a status yet; render nothing
    // rather than flash this page's content ahead of a redirect.
    return null
  }

  const canSubmit = country.length > 0 && !busy

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await startVerification(country)
      // No local success state: startVerification re-resolves, which moves
      // verificationStatus to 'pending' and re-renders this component into
      // its waiting face.
    } catch (err) {
      console.error('verification start failed:', err instanceof Error ? err.message : err)
      setError(messageForStartError(err))
      setBusy(false)
    }
  }

  if (verificationStatus === 'pending') {
    return (
      <section className="console" aria-labelledby="verification-title">
        <h1 id="verification-title">Check your email</h1>
        <EmptyState
          title="We sent you a verification link"
          description="Open it on any device to confirm you are an adult. It can take a minute or two to arrive, and it is worth checking your spam folder. You can leave this page open; we will notice as soon as you are done."
        />
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

  return (
    <section className="console" aria-labelledby="verification-title">
      <h1 id="verification-title">First, confirm you are an adult</h1>
      <p className="console__notice cyo-text-muted">
        Children&apos;s privacy law requires us to confirm that a real adult is setting this account
        up before any child profile exists. We will email you a link from our verification partner,
        Epic&apos;s Kids Web Services. It only takes a minute, and you only do it once.
      </p>
      <form className="guardian-login__form" onSubmit={(event) => void submit(event)}>
        <label className="guardian-login__field" htmlFor={countryId}>
          <span>Your country of residence</span>
          <select
            id={countryId}
            value={country}
            onChange={(event) => setCountry(event.target.value)}
            disabled={busy}
            required
          >
            <option value="" disabled>
              Select a country
            </option>
            {RESIDENCE_COUNTRIES.map((entry) => (
              <option key={entry.code} value={entry.code}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <p className="cyo-text-muted">
          This decides which ways of verifying are available to you, so it needs to be where you
          actually live.
        </p>
        {error ? (
          <p role="alert" className="cyo-text-error">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" disabled={!canSubmit}>
          {busy ? 'Sending…' : 'Email me a verification link'}
        </Button>
      </form>
      <p className="console__notice">
        <Button variant="ghost" size="sm" onClick={() => void signOut()}>
          Sign out
        </Button>
      </p>
    </section>
  )
}

/**
 * Turns a failed start into something a waiting parent can act on.
 *
 * 409 and 429 are the endpoint's deliberate refusals, not faults, and both
 * mean an email either is already on its way or has been recently. Reporting
 * the generic "could not send" for them is the specific failure worth
 * avoiding here: it tells a parent to expect nothing, so they stop watching
 * the inbox that already holds their link.
 *
 * #ASSUME: data-integrity: reads the status code off an axios-shaped error
 * without narrowing the type, because classifyApiError already owns the
 * type-safe fallback for everything else; this only diverts the two codes it
 * recognises and hands the rest straight back.
 * #VERIFY: GuardianVerificationPage.test.tsx 409/429/500 message cases.
 */
function messageForStartError(err: unknown): string {
  const status = (err as { response?: { status?: number } }).response?.status
  if (status === 409) return ALREADY_SENT
  if (status === 429) return TOO_MANY
  return classifyApiError(err, { transient: START_ERROR, server: START_ERROR }).message
}
