import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { Navigate } from 'react-router'

import '../guardian/guardian.css'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_AWAITING_APPROVAL_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
} from '../routes'
import { useAuth } from './useAuth'

// Matches GuardianAwaitingApprovalPage's AUTO_RECHECK_INTERVAL_MS: the two
// interstitials poll the same refreshStatus() call, and a guardian who has
// seen one should not find the other behaving differently.
const AUTO_RETRY_INTERVAL_MS = 20_000

// #ASSUME: timing: unlike the awaiting-approval poll, this one is capped.
// That poll re-checks a LIVE backend and short-circuits cheaply before
// GET /v1/me, so it can run indefinitely; every attempt here targets a host
// that is by definition down, so each one costs a full request timeout. Five
// minutes of hands-off retrying covers a service restart or a brief network
// blip, which is the case worth automating; a longer outage is not something
// an abandoned browser tab should keep polling through. The manual button
// stays available after the cap, so nothing becomes unrecoverable.
// #VERIFY: GuardianBackendUnavailablePage.test.tsx asserts the timer stops
// after MAX_AUTO_RETRIES ticks and that the button still works afterwards.
const MAX_AUTO_RETRIES = 15

/**
 * Shown when a Supabase session resolved fine but our own backend could not
 * be reached to turn it into a Principal (AuthStatus 'backend-unreachable').
 * ProtectedRoute and LoginPage both route here.
 *
 * This is the interstitial that issue #452 was missing. Before it, a
 * transient backend outage was handled as a terminal auth failure: the
 * guardian was signed out and sent to login, login re-established the same
 * perfectly valid Supabase session, resolution failed against the same
 * downed backend, and they looped. Because AuthContext now keeps the token
 * on the transient branch, a retry from this page can reach 'signed-in'
 * directly with no re-login.
 *
 * #ASSUME: security: this route sits outside ProtectedRoute (see router.tsx's
 * comment on it), so a signed-out visitor or a fully signed-in guardian can
 * land here via a direct URL, not just via a redirect. The status guards
 * below are load-bearing for that reason, not defensive extras. Mirrors
 * GuardianAwaitingApprovalPage and LoginPage.
 * #VERIFY: GuardianBackendUnavailablePage.test.tsx redirect cases.
 */
export function GuardianBackendUnavailablePage() {
  usePageTitle('Connection Problem')
  const { status, principal, signOut, refreshStatus } = useAuth()
  const [checking, setChecking] = useState(false)
  const [autoRetriesExhausted, setAutoRetriesExhausted] = useState(false)
  const autoRetryCountRef = useRef(0)

  // #ASSUME: external-resources: refreshStatus() resolves rather than
  // rejecting when principal resolution fails (syncPrincipal catches
  // internally and reports the outcome as a status transition), so the
  // ordinary "still down" case is not an exception at all and needs no
  // banner: the page simply stays put. This catch covers the narrower case
  // of getSession() itself throwing, and stays silent for the same reason
  // the awaiting-approval page does: retrying is a convenience, and Back to
  // sign-in is always available as the escape.
  // #VERIFY: GuardianBackendUnavailablePage.test.tsx "try again" tests.
  const tryAgain = useCallback(async () => {
    setChecking(true)
    try {
      await refreshStatus()
    } catch (err) {
      console.error('backend-unreachable retry failed', err instanceof Error ? err.message : err)
    } finally {
      setChecking(false)
    }
  }, [refreshStatus])

  // Hooks must run unconditionally before the status-gated early returns
  // below (rules of hooks), so the poll effect gates on status internally
  // instead of the component returning early first. clearInterval in the
  // teardown is what keeps a retry from firing after unmount; syncPrincipal's
  // own cancelledRef/isStale guard is the second line of defence for a call
  // already in flight when the page goes away.
  useEffect(() => {
    // The ref, not the `autoRetriesExhausted` state, is what gates this. The
    // cap has to be enforced synchronously inside the callback: a setState
    // does not stop an interval, it only schedules a re-render whose effect
    // teardown clears the timer, and every tick that fires in between still
    // counts. The state flag exists purely to change the copy below.
    if (status !== 'backend-unreachable' || autoRetryCountRef.current >= MAX_AUTO_RETRIES) {
      return undefined
    }
    const id = setInterval(() => {
      autoRetryCountRef.current += 1
      if (autoRetryCountRef.current >= MAX_AUTO_RETRIES) {
        clearInterval(id)
        setAutoRetriesExhausted(true)
      }
      void tryAgain()
    }, AUTO_RETRY_INTERVAL_MS)
    return () => clearInterval(id)
  }, [status, tryAgain])

  if (status === 'signed-out') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }
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
  if (status !== 'backend-unreachable') {
    // 'loading': AuthContext has not resolved a status yet; render nothing
    // rather than flash an outage message ahead of a redirect.
    return null
  }

  return (
    <section className="console" aria-labelledby="backend-unavailable-title">
      <h1 id="backend-unavailable-title">We can't reach CYO Adventure</h1>
      <EmptyState
        title="Something on our end isn't responding"
        description="You're signed in, but we couldn't load your account because the app's server didn't answer. This is usually temporary and nothing on your side is wrong. You do not need to sign in again."
      />
      <p className="console__notice cyo-text-muted" aria-live="polite">
        {autoRetriesExhausted
          ? "We've stopped checking automatically. Try again whenever you're ready."
          : "We'll keep checking in the background, or you can try right now."}
      </p>
      <p className="console__notice">
        <Button variant="ghost" size="sm" onClick={() => void tryAgain()} disabled={checking}>
          {checking ? 'Trying…' : 'Try again'}
        </Button>{' '}
        <Button variant="ghost" size="sm" onClick={() => void signOut()}>
          Back to sign-in
        </Button>
      </p>
    </section>
  )
}
