import { isAuthApiError } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'

import '../guardian/guardian.css'
import { GUARDIAN_CONSOLE_PATH, GUARDIAN_LOGIN_PATH } from '../routes'
import { parentalGateRemainingMs, warmParentalGate } from './parentalGateState'
import { supabase } from './supabaseClient'
import { useAuth } from './useAuth'

/**
 * The signed-in Supabase user as the gate needs to see it: who they are and
 * whether a password re-entry challenge is even possible for them.
 */
interface GateUser {
  userId: string
  email: string | null
  hasPassword: boolean
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
 * Parental gate (P6-08): guardian re-auth wrapper around the sensitive console
 * surfaces (review/approve, moderation settings, profiles, assignments; later,
 * purchases per P8-06). This is the gate pattern Apple expects in Kids
 * Category apps: a deliberate adult action (password re-entry) before anything
 * consequential, so a kid holding a signed-in device cannot wander from the
 * reader into approving stories or editing profiles.
 *
 * When the gate is cold it renders the challenge INSTEAD of the wrapped
 * content; a successful re-auth warms it for PARENTAL_GATE_TTL_MS of
 * in-memory state only (see parentalGateState.ts), so a reload re-challenges.
 *
 * Renders `children` when given, otherwise an `<Outlet />` so it can be used
 * as a pathless layout route in router.tsx.
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
 * redirect that would drop this in-memory gate state and loop). Locking those
 * guardians out of approval entirely is worse than a weaker gate, so OAuth
 * users pass through with a console-visible warning. Follow-up: give OAuth
 * guardians a real challenge (e.g. a gate PIN set at onboarding, or the
 * backend re-auth grant above).
 * #VERIFY: ParentalGate.test.tsx "lets an OAuth-only guardian through with a
 * console warning".
 */
export function ParentalGate({ children }: { children?: ReactNode }) {
  const { signInWithPassword, signOut } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [phase, setPhase] = useState<GatePhase>({ kind: 'checking' })
  const [password, setPassword] = useState('')
  const [error, setError] = useState<SubmitError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [switchingAccount, setSwitchingAccount] = useState(false)
  const [switchAccountError, setSwitchAccountError] = useState(false)
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
          // ProtectedRoute upstream should have redirected already; this only
          // races a sign-out. Fail closed toward the login page.
          setPhase({ kind: 'no-session' })
          return
        }
        const email =
          typeof sessionUser.email === 'string' && sessionUser.email !== ''
            ? sessionUser.email
            : null
        const hasPassword =
          readProviders(sessionUser.app_metadata).includes('email') && email !== null
        const user: GateUser = { userId: sessionUser.id, email, hasPassword }
        if (!hasPassword) {
          console.warn(
            'ParentalGate: session has no password identity (OAuth sign-in); ' +
              'passing through without a re-auth challenge. See ParentalGate.tsx ' +
              'for the documented limitation and follow-up.'
          )
          setPhase({ kind: 'oauth-bypass', user })
          return
        }
        setPhase(
          parentalGateRemainingMs(user.userId) > 0
            ? { kind: 'unlocked', user }
            : { kind: 'locked', user }
        )
      })
      .catch((err: unknown) => {
        // #EDGE: external resources: getSession() reads local session state
        // and should not reject, but if it ever does the gate must not hang
        // on the "checking" spinner forever. Fail closed to an explicit error
        // phase with a retry affordance instead of a silent dead end.
        // #VERIFY: ParentalGate.test.tsx "recovers from a failed session
        // lookup via the retry button".
        console.error('ParentalGate: could not resolve the current session:', err)
        if (!cancelled) setPhase({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  // #ASSUME: timing dependencies: while unlocked, schedule the re-challenge
  // for the moment the TTL runs out, so a guardian who walks away mid-session
  // does not leave the sensitive surfaces open indefinitely in a live tab.
  // Background tabs throttle timers and bfcache restores revive module state
  // past the TTL, so visibilitychange/pageshow re-check the wall clock and
  // lock immediately when the warmth has already expired.
  // #VERIFY: ParentalGate.test.tsx TTL-expiry, throttled-tab, and
  // bfcache-restore re-lock tests (fake timers).
  useEffect(() => {
    if (phase.kind !== 'unlocked') return
    const user = phase.user
    const lockNow = () => setPhase({ kind: 'locked', user })
    const lockIfExpired = () => {
      if (parentalGateRemainingMs(user.userId) <= 0) lockNow()
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') lockIfExpired()
    }
    // Already-expired (a race between the state update and this effect) falls
    // through to a zero-delay timeout rather than a synchronous setState in
    // the effect body (react-hooks/set-state-in-effect).
    const remaining = Math.max(parentalGateRemainingMs(user.userId), 0)
    const timer = setTimeout(lockNow, remaining)
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('pageshow', lockIfExpired)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('pageshow', lockIfExpired)
    }
  }, [phase])

  // #ASSUME: security: signInWithPassword against the CURRENT session user's
  // email is the re-auth primitive (reused from AuthContext, same Supabase
  // client). Success replaces the session with an equivalent fresh one (the
  // AuthProvider re-resolves /me on the SIGNED_IN event); failure leaves the
  // existing session untouched, so a wrong password never signs the guardian
  // out. The password lives only in component state and is cleared on success.
  // #VERIFY: ParentalGate.test.tsx unlock + wrong-password tests.
  async function submit(event: FormEvent) {
    event.preventDefault()
    // #CRITICAL: concurrency: a second submit while one is in flight (Enter
    // key on the still-focused input; the disabled attribute only guards the
    // button) must not stack a second re-auth call on the first.
    // #VERIFY: ParentalGate.test.tsx "ignores a re-entrant submit".
    if (submitting) return
    if (phase.kind !== 'locked' || phase.user.email === null) return
    setError(null)
    setSubmitting(true)
    try {
      await signInWithPassword({ email: phase.user.email, password })
      warmParentalGate(phase.user.userId)
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
  // supports both Google and password. signOut() also cools the module-level
  // warm state (AuthContext), so the next sign-in re-challenges as expected.
  // #VERIFY: ParentalGate.test.tsx "signs out and lets a different account
  // sign back in".
  async function switchAccount() {
    // #CRITICAL: concurrency: same re-entrant guard as submit() above (Enter
    // key vs. click, or a slow network letting a second click land before the
    // button disables): a stacked second signOut() call is wasted work at
    // best and a race against the first at worst.
    // #VERIFY: ParentalGate.test.tsx "ignores a re-entrant switch-account
    // click while one is already in flight".
    if (switchingAccount) return
    setSwitchAccountError(false)
    setSwitchingAccount(true)
    try {
      await signOut()
      // No manual navigation: the enclosing ProtectedRoute (router.tsx) reads
      // the same AuthContext status and redirects to GUARDIAN_LOGIN_PATH once
      // it flips to 'signed-out', same as GuardianShell's sign-out button.
    } catch {
      // #EDGE: external-resources: signOut rejects when Supabase cannot
      // revoke the session (network down); surface it instead of silently
      // leaving the guardian stuck on a challenge they cannot get past.
      setSwitchAccountError(true)
      setSwitchingAccount(false)
    }
  }

  function cancelChallenge() {
    // Deep-link/bookmark entries have no in-app history to pop
    // (location.key === 'default' is the router's first-entry signal), so
    // navigate(-1) would no-op or leave the SPA. Fall back to the guardian
    // console root, a deterministic in-app destination.
    if (location.key === 'default') {
      void navigate(GUARDIAN_CONSOLE_PATH, { replace: true })
    } else {
      void navigate(-1)
    }
  }

  if (phase.kind === 'checking') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
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
          <button type="submit" className="guardian-login__provider" disabled={submitting}>
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
          disabled={switchingAccount}
          onClick={() => void switchAccount()}
        >
          {switchingAccount ? 'Signing out…' : 'Not you? Sign out and use a different account'}
        </button>
        {!switchingAccount && switchAccountError ? (
          <p role="alert" className="guardian-login__error">
            Sign-out failed. Check your connection and try again.
          </p>
        ) : null}
      </div>
    )
  }

  return <>{children ?? <Outlet />}</>
}
