import { isAuthApiError } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { LoadingStatus } from '@ds/components/LoadingStatus'
import '../guardian/guardian.css'
import { GUARDIAN_CONSOLE_PATH, GUARDIAN_LOGIN_PATH } from '../routes'
import { adultGateRemainingMs, warmAdultGate } from './parentalGateState'
import { supabase } from './supabaseClient'
import { useAuth } from './useAuth'

/**
 * The signed-in Supabase user as the gate needs to see it: who they are and
 * whether a password re-entry challenge is even possible for them, plus
 * (Requirement 2) whether a Google identity is linked so the locked screen
 * can offer OAuth re-auth as a second path past the challenge.
 */
interface GateUser {
  userId: string
  email: string | null
  hasPassword: boolean
  hasGoogle: boolean
}

type GatePhase =
  | { kind: 'checking' }
  | { kind: 'error' }
  | { kind: 'no-session' }
  | { kind: 'locked'; user: GateUser }
  | { kind: 'unlocked'; user: GateUser }
  | { kind: 'oauth-bypass'; user: GateUser }

/** What went wrong with a password re-entry attempt, mapped to distinct copy. */
type SubmitError = 'credentials' | 'rate-limit' | 'server' | 'connection'

const SUBMIT_ERROR_COPY: Record<SubmitError, string> = {
  credentials: "That password didn't match. Please try again.",
  'rate-limit': 'Too many attempts. Please wait a minute before trying again.',
  server: 'The sign-in service had a problem. Please wait a moment and try again.',
  connection: "We couldn't reach the server. Check your connection and try again.",
}

/**
 * Same discrimination as LoginPage, split further: Supabase's stable
 * `invalid_credentials` code means a wrong password; a 429 is a rate limit
 * (retrying immediately makes a lockout worse, so it must not read as
 * "check your connection"); a 5xx is the service failing; anything else
 * (network, CORS) is a connection problem.
 */
function classifySubmitError(err: unknown): SubmitError {
  if (!isAuthApiError(err)) return 'connection'
  if (err.code === 'invalid_credentials') return 'credentials'
  if (err.status === 429) return 'rate-limit'
  if (err.status >= 500) return 'server'
  return 'connection'
}

/**
 * What went wrong with a switch-account sign-out, mapped to distinct copy.
 * No 'credentials' case: signOut() has no password to reject.
 */
type SwitchAccountError = 'rate-limit' | 'server' | 'connection'

const SWITCH_ACCOUNT_ERROR_COPY: Record<SwitchAccountError, string> = {
  'rate-limit': 'Sign-out failed. Too many attempts, please wait a minute before trying again.',
  server: 'Sign-out failed. The service had a problem, please wait a moment and try again.',
  connection: 'Sign-out failed. Check your connection and try again.',
}

/** Same discrimination as {@link classifySubmitError}, minus the credentials case. */
function classifySwitchAccountError(err: unknown): SwitchAccountError {
  if (!isAuthApiError(err)) return 'connection'
  if (err.status === 429) return 'rate-limit'
  if (err.status >= 500) return 'server'
  return 'connection'
}

/**
 * Collect the auth providers recorded on the Supabase user's app_metadata.
 * `providers` is the full list; `provider` is the first/primary one. Both are
 * loosely typed upstream (`[key: string]: any`), so validate rather than cast.
 */
function readProviders(meta: Record<string, unknown> | undefined): string[] {
  if (!meta) return []
  const providers = Array.isArray(meta.providers)
    ? meta.providers.filter((p): p is string => typeof p === 'string')
    : []
  if (typeof meta.provider === 'string' && !providers.includes(meta.provider)) {
    providers.push(meta.provider)
  }
  return providers
}

/**
 * Adult step-up gate (ADR-014 Phase 5): a SINGLE pathless layout route at the
 * root of the adult subtree (router.tsx), wrapping both the guardian and
 * admin ProtectedRoute subtrees. This collapses the two former per-page
 * ParentalGate placements (P6-08) into one kid-to-adult BOUNDARY crossing:
 * adult-to-adult navigation (guardian<->guardian, guardian<->admin,
 * admin<->guardian) is free once warm, because this component no longer sits
 * on individual sibling routes that React Router unmounts/remounts during
 * that navigation.
 *
 * Renders `children` when given, otherwise an `<Outlet />` so it can be used
 * as a pathless layout route.
 *
 * State machine:
 *   - no Supabase session -> redirect to guardian login (carrying the
 *     attempted location, same convention as ProtectedRoute).
 *   - session present, NOT warm (cold entry, or returning from kid mode via
 *     parkAdultGate) -> render the "Grown-ups only" password challenge.
 *   - session present, has no password identity (OAuth-only) -> pass through
 *     with a console warning, and warm the gate for consistency (see below).
 *   - session present, warm -> render children/<Outlet/>, free navigation.
 *
 * #CRITICAL: security: this is a client-side deterrent, not a security
 * boundary. Every gated action is still authorized server-side (Supabase JWT
 * verification plus role checks in api/deps.py); a bypassed gate exposes
 * nothing the session's own credentials do not already grant.
 *
 * Server-side approval freshness is DEFERRED, not implemented: the plan's
 * "approval freshness guard" note (a bounded auth_time / iat-recency check on
 * the approve endpoint) is not sound with Supabase sessions, because the
 * client's silent token refresh also mints a fresh iat, so an iat-recency
 * check cannot distinguish a re-authenticated human from a walked-away
 * auto-refreshing session. A real server-side check needs its own attestation
 * design; the candidate is a backend-minted, short-lived re-auth grant issued
 * on a verified password re-entry and demanded by the approve endpoint
 * (future work).
 *
 * #ASSUME: security: a guardian who signed in via OAuth (Google/Apple) has no
 * password to re-enter, and supabase-js offers no client-side OAuth
 * re-auth challenge (`auth.reauthenticate()` exists but only sends a nonce for
 * secure password updates, and re-running signInWithOAuth is a full-page
 * redirect that would drop any in-flight gate state and loop). Locking those
 * guardians out entirely is worse than a weaker gate, so OAuth users pass
 * through with a console-visible warning. The gate is also warmed for them
 * (unlike the pre-Phase-5 ParentalGate, which deliberately left OAuth-bypass
 * unwarmed): warming is what makes a later kid-to-adult crossing consistent
 * for these users too, even though the bypass itself does not depend on
 * warmth (the hasPassword check runs before the warm check below). Follow-up:
 * give OAuth guardians a real challenge (e.g. a gate PIN set at onboarding, or
 * the backend re-auth grant above). This is distinct from Requirement 2's
 * Google button on the `locked` screen below: that button only ever renders
 * for a guardian who DOES have a password identity (hasGoogle is additional,
 * never a substitute), and it is a deliberate, user-initiated click rather
 * than something the gate runs automatically, so the "would drop in-flight
 * state and loop" concern above does not apply to it.
 * #VERIFY: AdultGate.test.tsx "lets an OAuth-only guardian through with a
 * console warning, and warms the gate".
 */
export function AdultGate({ children }: { children?: ReactNode }) {
  const { signInWithPassword, signInWithOAuth, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [phase, setPhase] = useState<GatePhase>({ kind: 'checking' })
  const [password, setPassword] = useState('')
  const [error, setError] = useState<SubmitError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [switchingAccount, setSwitchingAccount] = useState(false)
  const [switchAccountError, setSwitchAccountError] = useState<SwitchAccountError | null>(null)
  // Requirement 2: Google re-auth on the locked screen, alongside the
  // password form. googleError is a bare boolean (not a discriminated union
  // like SubmitError): signInWithOAuth only ever fails BEFORE the redirect
  // starts (a network problem reaching Supabase/Google), the same single
  // failure shape LoginPage's startSignIn already reports generically.
  const [googleSigningIn, setGoogleSigningIn] = useState(false)
  const [googleError, setGoogleError] = useState(false)
  // Bumped by the error phase's "Try again" button to re-run the session
  // lookup effect below.
  const [attempt, setAttempt] = useState(0)

  // Resolve who is behind the current session and whether the gate is already
  // warm for them. getSession() reads supabase-js's local session state; no
  // network round-trip is required to render the challenge.
  useEffect(() => {
    let cancelled = false
    void supabase.auth
      .getSession()
      .then(({ data }) => {
        if (cancelled) return
        const sessionUser = data.session?.user
        if (!sessionUser) {
          // A missing session here means either a genuinely signed-out
          // visitor (this gate now sits ABOVE ProtectedRoute, so it is the
          // first thing to see a stale/expired session) or a race with a
          // sign-out event. Either way, fail closed toward the login page.
          setPhase({ kind: 'no-session' })
          return
        }
        const email =
          typeof sessionUser.email === 'string' && sessionUser.email !== ''
            ? sessionUser.email
            : null
        const providers = readProviders(sessionUser.app_metadata)
        const hasPassword = providers.includes('email') && email !== null
        const hasGoogle = providers.includes('google')
        const user: GateUser = { userId: sessionUser.id, email, hasPassword, hasGoogle }
        if (!hasPassword) {
          console.warn(
            'AdultGate: session has no password identity (OAuth sign-in); ' +
              'passing through without a re-auth challenge. See AdultGate.tsx ' +
              'for the documented limitation and follow-up.'
          )
          warmAdultGate(user.userId)
          setPhase({ kind: 'oauth-bypass', user })
          return
        }
        setPhase(
          adultGateRemainingMs(user.userId) > 0
            ? { kind: 'unlocked', user }
            : { kind: 'locked', user }
        )
      })
      .catch((err: unknown) => {
        // #EDGE: external resources: getSession() reads local session state
        // and should not reject, but if it ever does the gate must not hang
        // on the "checking" spinner forever. Fail closed to an explicit error
        // phase with a retry affordance instead of a silent dead end.
        // #VERIFY: AdultGate.test.tsx "recovers from a failed session
        // lookup via the retry button".
        console.error('AdultGate: could not resolve the current session:', err)
        if (!cancelled) setPhase({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  // #ASSUME: timing dependencies: ADULT_GATE_TTL_MS is an IDLE window
  // (Requirement 1), not an absolute one: while unlocked, pointerdown/keydown
  // activity re-warms the gate (throttled to ~30s so it does not thrash
  // sessionStorage on every keystroke), so a guardian actively using the
  // console is never dropped mid-task. Only true inactivity, or a
  // navigation into kid mode (parkAdultGate), or sign-out (clearAdultGate),
  // re-cold the gate. Because activity can slide the stored expiry forward
  // at any moment from an event-listener closure, a single setTimeout
  // scheduled once at mount cannot track it; the re-lock check is instead a
  // periodic poll of the sessionStorage-backed expiry (cheap: a JSON parse
  // plus a comparison), frequent enough to lock within one poll interval of
  // true expiry. Background tabs throttle timers and bfcache restores revive
  // stored state past the TTL, so visibilitychange/pageshow still separately
  // re-check the wall clock and lock immediately when warmth has already
  // expired, same as before.
  // #VERIFY: AdultGate.test.tsx TTL-expiry (no-activity), idle-slide
  // (activity keeps it unlocked past the original TTL), throttle,
  // throttled-tab, and bfcache-restore re-lock tests (fake timers).
  useEffect(() => {
    if (phase.kind !== 'unlocked') return
    const user = phase.user
    const lockNow = () => {
      setSwitchAccountError(null)
      setPhase({ kind: 'locked', user })
    }
    const lockIfExpired = () => {
      if (adultGateRemainingMs(user.userId) <= 0) lockNow()
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') lockIfExpired()
    }
    // How often the poll re-checks the stored expiry. Small enough that
    // locking feels immediate at page granularity against a 30-minute idle
    // window; large enough to be free in practice.
    const POLL_INTERVAL_MS = 5_000
    // Already-expired (a race between the state update and this effect) is
    // caught by this same poll rather than a synchronous setState in the
    // effect body (react-hooks/set-state-in-effect); scheduling it via
    // setInterval's own first tick would wait a full POLL_INTERVAL_MS, so an
    // immediate zero-delay check runs once up front too.
    const raceCheck = setTimeout(lockIfExpired, 0)
    const pollTimer = setInterval(lockIfExpired, POLL_INTERVAL_MS)

    // #CRITICAL: security: re-warming on activity must only ever extend the
    // SAME user's existing warm entry (warmAdultGate always keys off
    // user.userId, the current phase's own user), never adopt or create a
    // warm entry for anyone else. This is the same single-user invariant
    // parentalGateState.ts documents for the initial warm.
    const REWARM_THROTTLE_MS = 30_000
    let lastWarmAt = Date.now()
    const onActivity = () => {
      const now = Date.now()
      if (now - lastWarmAt < REWARM_THROTTLE_MS) return
      lastWarmAt = now
      warmAdultGate(user.userId, now)
    }
    document.addEventListener('pointerdown', onActivity)
    document.addEventListener('keydown', onActivity)
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('pageshow', lockIfExpired)
    return () => {
      clearTimeout(raceCheck)
      clearInterval(pollTimer)
      document.removeEventListener('pointerdown', onActivity)
      document.removeEventListener('keydown', onActivity)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('pageshow', lockIfExpired)
    }
  }, [phase])

  // #ASSUME: security: signInWithPassword against the CURRENT session user's
  // email is the re-auth primitive (reused from AuthContext, same Supabase
  // client). Success replaces the session with an equivalent fresh one (the
  // AuthProvider re-resolves /me on the SIGNED_IN event, which also warms the
  // gate independently -- see AuthContext.tsx -- so the explicit warmAdultGate
  // call here is what makes THIS render transition straight to unlocked
  // without waiting on that separate effect); failure leaves the existing
  // session untouched, so a wrong password never signs the guardian out. The
  // password lives only in component state and is cleared on success.
  // #VERIFY: AdultGate.test.tsx unlock + wrong-password tests.
  async function submit(event: FormEvent) {
    event.preventDefault()
    // #CRITICAL: concurrency: a second submit while one is in flight (Enter
    // key on the still-focused input; the disabled attribute only guards the
    // button) must not stack a second re-auth call on the first. Also guards
    // against switchAccount() racing a concurrent signOut(), and against
    // continueWithGoogle() racing a concurrent signInWithOAuth(), against the
    // same Supabase client: without these, a sign-in already in flight (via
    // password re-auth OR the Google redirect) could land after the sign-out
    // and undo it, or two sign-ins could race which one lands last. The guard
    // family is symmetric: submit(), switchAccount(), and continueWithGoogle()
    // each bail on all three in-flight states.
    // #VERIFY: AdultGate.test.tsx "ignores a re-entrant submit", "disables
    // the Confirm button while a switch-account sign-out is in flight".
    if (submitting) return
    if (switchingAccount) return
    if (googleSigningIn) return
    if (phase.kind !== 'locked' || phase.user.email === null) return
    setError(null)
    setSubmitting(true)
    try {
      await signInWithPassword({ email: phase.user.email, password })
      warmAdultGate(phase.user.userId)
      setPassword('')
      setPhase({ kind: 'unlocked', user: phase.user })
    } catch (err) {
      setError(classifySubmitError(err))
    } finally {
      setSubmitting(false)
    }
  }

  // #ASSUME: security: the gate only knows how to re-authenticate the
  // CURRENT session's owner (no email field on the challenge form), so a
  // guardian who needs a different account (a test account, or one whose
  // password identity differs from the signed-in session) has no path
  // forward except signing out and going back through LoginPage, which
  // supports both Google and password. signOut() also clears the warm adult
  // gate state (AuthContext), so the next sign-in re-challenges as expected.
  // #VERIFY: AdultGate.test.tsx "signs out and lets a different account
  // sign back in".
  async function switchAccount() {
    // #CRITICAL: concurrency: same re-entrant guard as submit() above (a slow
    // network letting a second click land before the button disables): a
    // stacked second signOut() call is wasted work at best and a race against
    // the first at worst. Also cross-guards against submit() and
    // continueWithGoogle(): without these, signOut() and signInWithPassword()
    // (or signInWithOAuth()) could run concurrently against the same Supabase
    // client, racing which one lands last.
    // #VERIFY: AdultGate.test.tsx "ignores a re-entrant switch-account
    // click while one is already in flight", "disables the switch-account
    // link while a password submit is in flight".
    if (switchingAccount) return
    if (submitting) return
    if (googleSigningIn) return
    setSwitchAccountError(null)
    setSwitchingAccount(true)
    try {
      await signOut()
      // No manual navigation: AdultGate's own no-session branch (above) fires
      // once the session change propagates, same as ProtectedRoute would for
      // any other signed-out visitor.
    } catch (err) {
      // #EDGE: external-resources: signOut rejects when Supabase cannot
      // revoke the session (network down); surface it instead of silently
      // leaving the guardian stuck on a challenge they cannot get past.
      // #VERIFY: AdultGate.test.tsx "shows an inline error when sign-out
      // fails while switching accounts".
      setSwitchAccountError(classifySwitchAccountError(err))
      setSwitchingAccount(false)
    }
  }

  // #ASSUME: security: Requirement 2. A guardian who signed in with Google AND
  // has an email/password identity linked to the same account (hasGoogle)
  // gets a second path past the locked screen besides typing a password:
  // reuse LoginPage's exact `signInWithOAuth('google')` primitive
  // (AuthContext.tsx), the SAME re-auth LoginPage itself offers, not a new
  // one. Unlike submit()/switchAccount(), this never sets phase directly:
  // signInWithOAuth resolving only means the browser is about to navigate
  // away to Google's consent screen (a full-page redirect back to
  // GUARDIAN_LOGIN_PATH), which unmounts this component. AuthContext's
  // onAuthStateChange warms the gate on that later SIGNED_IN event (see
  // AuthContext.tsx's syncPrincipal), so this handler must NOT call
  // warmAdultGate itself, or a failed /me resolution after the redirect
  // would leave a stale warm entry behind for a principal that never
  // actually got signed in.
  // #VERIFY: AdultGate.test.tsx "shows a Continue with Google option ...
  // starts the OAuth redirect on click", "shows a connection error ... when
  // the OAuth redirect fails to start".
  async function continueWithGoogle() {
    // #CRITICAL: concurrency: same re-entrant guard family as submit() and
    // switchAccount() above: a second click while the redirect is starting,
    // or a click landing while a password submit or switch-account sign-out
    // is already in flight, must not fire a second signInWithOAuth call (or
    // race signOut()) against the same Supabase client.
    // #VERIFY: AdultGate.test.tsx "ignores a re-entrant Google click while
    // one is already in flight", "disables the password Confirm button
    // while the Google redirect is starting".
    if (submitting) return
    if (switchingAccount) return
    if (googleSigningIn) return
    setGoogleError(false)
    setGoogleSigningIn(true)
    try {
      await signInWithOAuth('google')
    } catch {
      // #EDGE: external-resources: signInWithOAuth rejects when Supabase
      // cannot start the OAuth redirect (network down, misconfigured
      // provider). Without this the click would silently no-op, same failure
      // mode LoginPage's startSignIn guards against.
      setGoogleError(true)
      setGoogleSigningIn(false)
    }
  }

  function cancelChallenge() {
    // Deep-link/bookmark entries have no in-app history to pop
    // (location.key === 'default' is the router's first-entry signal), so
    // navigate(-1) would no-op or leave the SPA. Fall back to the guardian
    // console root, a deterministic in-app destination reachable by both a
    // guardian and an admin-only adult (ProtectedRoute's allowedRoles admits
    // the admin capability there too).
    if (location.key === 'default') {
      void navigate(GUARDIAN_CONSOLE_PATH, { replace: true })
    } else {
      void navigate(-1)
    }
  }

  if (phase.kind === 'checking') {
    return <LoadingStatus />
  }

  if (phase.kind === 'error') {
    return (
      <div className="guardian-login parental-gate">
        <div role="alert">
          <h1>Grown-ups only</h1>
          <p>We couldn&apos;t check who is signed in. Please try again.</p>
        </div>
        <button
          type="button"
          className="guardian-login__provider"
          onClick={() => {
            setPhase({ kind: 'checking' })
            setAttempt((n) => n + 1)
          }}
        >
          Try again
        </button>
      </div>
    )
  }

  if (phase.kind === 'no-session') {
    // Carry the attempted location like ProtectedRoute does, so a re-login
    // returns the guardian here instead of the generic console.
    return <Navigate to={GUARDIAN_LOGIN_PATH} state={{ from: location }} replace />
  }

  if (phase.kind === 'locked') {
    return (
      <div className="guardian-login parental-gate">
        {/* Announce the loading-to-challenge transition to screen readers
            (same pattern as the loading state above and ProtectedRoute). */}
        <div role="status" aria-live="polite">
          <h1>Grown-ups only</h1>
          <p>
            Re-enter the password for <strong>{phase.user.email}</strong> to continue. This keeps
            reviewing, approving, and family settings behind a parent.
          </p>
        </div>
        {phase.user.hasGoogle ? (
          <>
            <button
              type="button"
              className="guardian-login__provider"
              disabled={googleSigningIn || submitting || switchingAccount}
              onClick={() => void continueWithGoogle()}
            >
              {googleSigningIn ? 'Redirecting…' : 'Continue with Google'}
            </button>
            {!googleSigningIn && googleError ? (
              <p role="alert" className="guardian-login__error">
                Sign-in didn&apos;t start. Check your connection and try again.
              </p>
            ) : null}
            <div className="guardian-login__divider">
              <span>or use your password</span>
            </div>
          </>
        ) : null}
        <form className="guardian-login__form" onSubmit={(event) => void submit(event)}>
          <label className="guardian-login__field">
            <span>Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button
            type="submit"
            className="guardian-login__provider"
            disabled={submitting || switchingAccount || googleSigningIn}
          >
            {submitting ? 'Checking...' : 'Confirm'}
          </button>
          <button type="button" className="guardian-login__provider" onClick={cancelChallenge}>
            Go back
          </button>
          {!submitting && error !== null ? (
            <p role="alert" className="guardian-login__error">
              {SUBMIT_ERROR_COPY[error]}
            </p>
          ) : null}
        </form>
        <button
          type="button"
          className="guardian-login__link"
          disabled={switchingAccount || submitting || googleSigningIn}
          onClick={() => void switchAccount()}
        >
          {switchingAccount ? 'Signing out…' : 'Not you? Sign out and use a different account'}
        </button>
        {!switchingAccount && switchAccountError !== null ? (
          <p role="alert" className="guardian-login__error">
            {SWITCH_ACCOUNT_ERROR_COPY[switchAccountError]}
          </p>
        ) : null}
      </div>
    )
  }

  return <>{children ?? <Outlet />}</>
}
