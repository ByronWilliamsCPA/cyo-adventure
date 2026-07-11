import { isAuthApiError } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Navigate, Outlet, useNavigate } from 'react-router-dom'

import '../guardian/guardian.css'
import { GUARDIAN_LOGIN_PATH } from '../routes'
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
  | { kind: 'no-session' }
  | { kind: 'locked'; user: GateUser }
  | { kind: 'unlocked'; user: GateUser }
  | { kind: 'oauth-bypass'; user: GateUser }

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
  const { signInWithPassword } = useAuth()
  const navigate = useNavigate()
  const [phase, setPhase] = useState<GatePhase>({ kind: 'checking' })
  const [password, setPassword] = useState('')
  const [error, setError] = useState<'credentials' | 'connection' | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Resolve who is behind the current session and whether the gate is already
  // warm for them. getSession() reads supabase-js's local session state; no
  // network round-trip is required to render the challenge.
  useEffect(() => {
    let cancelled = false
    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return
      const sessionUser = data.session?.user
      if (!sessionUser) {
        // ProtectedRoute upstream should have redirected already; this only
        // races a sign-out. Fail closed toward the login page.
        setPhase({ kind: 'no-session' })
        return
      }
      const email =
        typeof sessionUser.email === 'string' && sessionUser.email !== '' ? sessionUser.email : null
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
    return () => {
      cancelled = true
    }
  }, [])

  // #ASSUME: timing dependencies: while unlocked, schedule the re-challenge
  // for the moment the TTL runs out, so a guardian who walks away mid-session
  // does not leave the sensitive surfaces open indefinitely in a live tab.
  // #VERIFY: ParentalGate.test.tsx TTL-expiry test (fake timers).
  useEffect(() => {
    if (phase.kind !== 'unlocked') return
    const user = phase.user
    // Already-expired (a race between the state update and this effect) falls
    // through to a zero-delay timeout rather than a synchronous setState in
    // the effect body (react-hooks/set-state-in-effect).
    const remaining = Math.max(parentalGateRemainingMs(user.userId), 0)
    const timer = setTimeout(() => setPhase({ kind: 'locked', user }), remaining)
    return () => clearTimeout(timer)
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
    if (phase.kind !== 'locked' || phase.user.email === null) return
    setError(null)
    setSubmitting(true)
    try {
      await signInWithPassword({ email: phase.user.email, password })
      warmParentalGate(phase.user.userId)
      setPassword('')
      setPhase({ kind: 'unlocked', user: phase.user })
    } catch (err) {
      // Same discrimination as LoginPage: Supabase's stable `invalid_credentials`
      // code means a wrong password; anything else (network, 429, 5xx) is an
      // operational failure and must not be reported as a wrong password.
      setError(
        isAuthApiError(err) && err.code === 'invalid_credentials' ? 'credentials' : 'connection'
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (phase.kind === 'checking') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }

  if (phase.kind === 'no-session') {
    return <Navigate to={GUARDIAN_LOGIN_PATH} replace />
  }

  if (phase.kind === 'locked') {
    return (
      <div className="guardian-login parental-gate">
        <h1>Grown-ups only</h1>
        <p>
          Re-enter the password for <strong>{phase.user.email}</strong> to continue. This keeps
          reviewing, approving, and family settings behind a parent.
        </p>
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
          <button
            type="button"
            className="guardian-login__provider"
            onClick={() => void navigate(-1)}
          >
            Go back
          </button>
          {!submitting && error === 'credentials' ? (
            <p role="alert" className="guardian-login__error">
              That password didn&apos;t match. Please try again.
            </p>
          ) : null}
          {!submitting && error === 'connection' ? (
            <p role="alert" className="guardian-login__error">
              We couldn&apos;t reach the server. Check your connection and try again.
            </p>
          ) : null}
        </form>
      </div>
    )
  }

  return <>{children ?? <Outlet />}</>
}
