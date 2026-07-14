import type { Session } from '@supabase/supabase-js'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import type { MeResponse } from '../client/types.gen'
import { useApi } from '../hooks/useApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import {
  AuthContext,
  type AuthContextValue,
  type AuthError,
  type AuthStatus,
} from './authContext'
import { clearChildSession } from './childSession'
import { clearAdultGate, warmAdultGate } from './parentalGateState'
import { supabase } from './supabaseClient'
import { isRole, type Principal } from './types'

const TOKEN_STORAGE_KEY = 'auth_token'

/**
 * Clears the stored bearer token, swallowing the DOMException that some
 * browsers throw from localStorage in private/locked-down modes. Clearing is a
 * best-effort cleanup on the fail-closed path, so a throw here must not mask
 * the sign-out it accompanies.
 *
 * #ASSUME: security: also clears any active child session (G1 / P6-04). Both
 * call sites below represent "the guardian is no longer authenticated"
 * (an explicit sign-out, or a Supabase session that never resolved to a
 * principal), and a child session sharing this device's storage must not
 * outlive the guardian session that made the device available for a kid to
 * use. clearChildSession() is a no-op when no child session is stored.
 * #VERIFY: AuthContext.test.tsx "sign-out clears an active child session".
 */
function safeRemoveToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // #EDGE: browser-compat: storage unavailable; nothing to clean up.
  }
  clearChildSession()
}

// Alias, not a hand-typed shadow interface: the shape is the generated
// OpenAPI client's MeResponse (frontend/src/client/types.gen.ts), the single
// source of truth for the backend's GET /v1/me contract (Finding 7).
type MeResponseBody = MeResponse

/**
 * Wraps the Supabase guardian session and resolves it to a backend
 * {@link Principal} via GET /v1/me. The frontend never inspects the bearer
 * token itself (opaque locally, a signed JWT elsewhere); /me is the sole
 * source of truth for role/family, matching api/deps.py's Principal.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [authError, setAuthError] = useState<AuthError | null>(null)

  // #CRITICAL: concurrency: onAuthStateChange can fire several events in quick
  // succession (INITIAL_SESSION, then a near-immediate TOKEN_REFRESHED), each
  // starting an async /me fetch. Without an ordering guard a slow earlier
  // response can land after a newer one and overwrite it, leaving the UI on a
  // stale principal (or a stale signed-out). A monotonic sequence token makes
  // every handler ignore any result that is not the latest it launched.
  // #VERIFY: test_auth_context.test_out_of_order_me_responses_keep_latest.
  const requestSeq = useRef(0)

  useEffect(() => {
    let cancelled = false

    // #ASSUME: timing-dependencies: this re-fetches /me on every
    // onAuthStateChange event, including a periodic TOKEN_REFRESHED with an
    // unchanged role/family. That's wasted work, not a correctness bug, and
    // guardian sessions are low-frequency; revisit only if /me load becomes
    // measurable.
    // #VERIFY: test_auth_context.test_refetches_principal_on_token_refresh.
    //
    // `event` is Supabase's onAuthStateChange discriminator (undefined for
    // the initial getSession()-driven call below, which resolves a possibly
    // PERSISTED session, not a fresh sign-in). It is used for exactly one
    // thing: warming the adult gate (ADR-014 Phase 5) ONLY on a genuine
    // 'SIGNED_IN' event (a password submit or an OAuth redirect return), the
    // moment the guardian has just proven full credentials. Warming on any
    // other event -- in particular the initial session restore or a silent
    // 'TOKEN_REFRESHED' -- would let a stale/cached session, or a walked-away
    // auto-refreshing tab, look identical to a guardian who just typed a
    // password, defeating the step-up entirely.
    // #CRITICAL: security: gate the warm call on event === 'SIGNED_IN', never
    // on session presence alone.
    // #VERIFY: AuthContext.test.tsx "warms the adult gate on a SIGNED_IN
    // event, but not on session restore or token refresh".
    async function syncPrincipal(session: Session | null, event?: string) {
      const seq = ++requestSeq.current
      // A later handler already superseded this one, or the provider unmounted.
      const isStale = () => cancelled || seq !== requestSeq.current

      if (session === null) {
        safeRemoveToken()
        if (!isStale()) {
          setPrincipal(null)
          setStatus('signed-out')
          setAuthError(null)
        }
        return
      }
      try {
        // #EDGE: browser-compat: setItem throws in private-mode / quota-full
        // browsers. Keep it inside the try so a storage failure routes to the
        // fail-closed signed-out path below instead of stranding status on
        // 'loading' (it used to sit outside the try, where a throw was fatal).
        localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token)
        const res = await api.get<MeResponseBody>('/v1/me')
        if (isStale()) return
        // #CRITICAL: security: the role drives ProtectedRoute's allow/deny, so
        // an unexpected value must fail closed rather than being cast blindly.
        // #VERIFY: test_auth_context.test_invalid_role_signs_out.
        if (!isRole(res.data.role)) {
          throw new Error(`Unexpected role from /me: ${String(res.data.role)}`)
        }
        setPrincipal({
          subject: res.data.subject,
          role: res.data.role,
          // #CRITICAL: security: fail closed on anything but an explicit true;
          // a missing or malformed is_admin must never grant the admin console.
          // #VERIFY: AuthContext.test.tsx is_admin true/absent cases.
          isAdmin: res.data.is_admin === true,
          familyId: res.data.family_id,
          profileIds: res.data.profile_ids,
        })
        setStatus('signed-in')
        setAuthError(null)
        if (event === 'SIGNED_IN') {
          warmAdultGate(session.user.id)
        }
      } catch (err) {
        // #CRITICAL: security: a session whose /me call fails (expired,
        // rejected by the backend's real JWT verification) or returns an
        // unrecognized role must never be treated as authenticated. Fail
        // closed to signed-out, but record authError so a caller (LoginPage)
        // can distinguish "session established, principal unresolved" from a
        // plain signed-out and give the user feedback instead of a dead end.
        // Log the cause: without it, "I can't log in" leaves no client trace.
        // #VERIFY: AuthContext.test.tsx sets authError on a failed /me.
        console.error(
          'principal resolution failed after a Supabase session was established:',
          err instanceof Error ? err.message : err
        )
        safeRemoveToken()
        if (!isStale()) {
          setPrincipal(null)
          setStatus('signed-out')
          setAuthError('principal-unresolved')
        }
      }
    }

    // Fire-and-forget: this runs inside a useEffect with no async cleanup
    // seam, and the `cancelled` flag (checked below and inside syncPrincipal)
    // already guards against a resolved-after-unmount state update.
    void supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) void syncPrincipal(data.session)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      void syncPrincipal(session, event)
    })

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [api])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      principal,
      authError,
      // #ASSUME: data-integrity: supabase-js auth methods resolve with
      // { error } instead of throwing, so an unchecked await silently
      // swallows a failed OAuth redirect or sign-out. Rethrow so callers
      // (LoginPage, GuardianShell) can surface the failure.
      // #VERIFY: AuthContext.test.tsx signInWithOAuth/signOut rejection cases.
      // #CRITICAL: security: redirectTo MUST return to a page that loads
      // @supabase/supabase-js so detectSessionInUrl processes the callback hash
      // and this provider's onAuthStateChange bridges the token. That code is
      // scoped to the guardian subtree (router.tsx), so returning to the kid
      // surface ('/', Supabase's default Site URL) would drop the session on the
      // floor and strand the user on an unauthenticated page.
      // #VERIFY: add https://<host>/guardian/login to Supabase Auth redirect URLs.
      signInWithOAuth: async (provider) => {
        const { error } = await supabase.auth.signInWithOAuth({
          provider,
          options: { redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}` },
        })
        if (error) throw error
      },
      // #ASSUME: security: signInWithPassword resolves with { error } on bad
      // credentials rather than throwing (same shape as signInWithOAuth above),
      // so rethrow lets LoginPage surface the failure. Resolving only means a
      // session was established, NOT that the user is authenticated: the effect
      // above still has to resolve a Principal via /me, and that can fail (see
      // authError). Callers must therefore also watch status/authError, not
      // treat resolution as sign-in.
      // #VERIFY: AuthContext.test.tsx signInWithPassword delegation + rejection.
      signInWithPassword: async ({ email, password }) => {
        // Clear any stale authError from a prior attempt BEFORE this request
        // goes out. LoginPage derives `busy = submitting && !authError`; a
        // lingering 'principal-unresolved' would make busy false on the first
        // render of the new attempt, re-enabling the button and keeping the old
        // "couldn't load your account" alert visible while the request is in
        // flight. The next /me resolution sets authError afresh.
        setAuthError(null)
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      },
      signOut: async () => {
        // #CRITICAL: security: clear the LOCAL guardian credential FIRST, before
        // the network revoke and independently of its outcome. Supabase's
        // GoTrueClient._signOut only calls _removeSession() (which clears
        // auth_token and emits SIGNED_OUT) AFTER a successful or 4xx revoke; a
        // transport failure or 5xx returns early and leaves auth_token in
        // localStorage. On a shared kid device (frequently offline, the exact
        // class ADR-014 targets) that stranded guardian bearer is then attached
        // by the useApi fallthrough on any kid route that misses the
        // child-session and device-grant branches, exposing the whole family's
        // guardian-scoped library to the child. Clearing locally up front makes
        // sign-out fail closed regardless of the revoke result. This runs
        // synchronously before the first await, so `void signOut()` callers
        // (LoginPage authorize-device, ConsolePage handoff) get it too.
        // #VERIFY: AuthContext.test.tsx "sign-out clears the local credential
        // even when the network revoke fails".
        safeRemoveToken()
        // #ASSUME: security: an explicit sign-out hands the device over, so
        // any warm adult-gate state (ADR-014 Phase 5) must die with the
        // session rather than surviving in sessionStorage for the next
        // sign-in within the TTL. Clear it here deterministically instead of
        // relying on the async SIGNED_OUT event.
        // #VERIFY: AuthContext.test.tsx "sign-out drops warm adult-gate
        // state".
        clearAdultGate()
        const { error } = await supabase.auth.signOut()
        if (error) throw error
      },
    }),
    [status, principal, authError]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
