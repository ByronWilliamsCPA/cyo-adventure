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
import {
  isPasswordRecovery,
  RECOVERY_BROADCAST_CHANNEL_NAME,
  recoveryErrorFromUrl,
  supabase,
} from './supabaseClient'
import { TOKEN_STORAGE_KEY } from './tokenStorageKey'
import { isRole, type Principal } from './types'

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

/**
 * Best-effort purge of authenticated data at rest on sign-out (SEC-F5).
 *
 * The Workbox runtime caches ('api-cache', 'storybook-blobs') and the offline
 * reading-state store hold children's names, story content, and progress that
 * would otherwise survive a sign-out on a returned or hand-me-down device.
 * Every step is wrapped so a failure never blocks the sign-out; the offline
 * store is imported dynamically to keep IndexedDB code out of the eager bundle.
 */
async function purgeAuthenticatedDataAtRest(): Promise<void> {
  try {
    if (typeof caches !== 'undefined') {
      await Promise.all(['api-cache', 'storybook-blobs'].map((name) => caches.delete(name)))
    }
  } catch {
    // Cache Storage unavailable or blocked: best-effort only.
  }
  try {
    const { clearReadingStates } = await import('../offline/db')
    await clearReadingStates()
  } catch {
    // IndexedDB unavailable or blocked: best-effort only.
  }
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
  // Seeded from the frozen hash flag (supabaseClient captured it before
  // createClient stripped the fragment). Also flipped on by a PASSWORD_RECOVERY
  // event below, so a recovery landing is caught whether the flag or the event
  // wins the race. Cleared on a successful updatePassword or on sign-out.
  const [recovery, setRecovery] = useState(isPasswordRecovery)
  // Frozen once per page load, same as isPasswordRecovery/recoveryErrorFromUrl
  // themselves; a failed recovery link never transitions into a successful
  // one within a single load, so this needs no setter.
  const recoveryError = recoveryErrorFromUrl

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
      // supabase-js emits PASSWORD_RECOVERY once it has processed a recovery
      // link's hash. Flip into recovery here (in addition to the module-level
      // seed) so the set-new-password form shows even when the event, not the
      // frozen flag, is what surfaces the recovery intent.
      // #ASSUME: timing dependencies: this races the module-level
      // isPasswordRecovery seed above (both can set recovery=true for the
      // same landing); relying on either alone would miss the case where the
      // other loses its race, so both stay in place.
      // #VERIFY: AuthContext.test.tsx "sets recovery from the PASSWORD_RECOVERY
      // event" and the module-level-seed recovery test.
      if (event === 'PASSWORD_RECOVERY') setRecovery(true)
      void syncPrincipal(session, event)
    })

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [api])

  // #CRITICAL: concurrency: see RECOVERY_BROADCAST_CHANNEL_NAME's doc comment
  // in supabaseClient.ts. A stale second guardian tab never sees the recovery
  // hash or a PASSWORD_RECOVERY event (both scoped to the tab that followed
  // the link), so without this listener Supabase's cross-tab session sync
  // would flip this tab straight to signed-in on the guardian's OLD password.
  // #VERIFY: AuthContext.test.tsx "a second tab enters recovery when notified
  // over the recovery broadcast channel".
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const channel = new BroadcastChannel(RECOVERY_BROADCAST_CHANNEL_NAME)
    channel.onmessage = () => setRecovery(true)
    return () => channel.close()
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      principal,
      authError,
      recovery,
      recoveryError,
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
        // Abandoning a recovery flow (signing out from the set-new-password
        // form) must not leave the provider stuck in recovery for the next
        // session on this device. Cleared unconditionally, before the network
        // call, for the same fail-closed reason as safeRemoveToken() and
        // clearAdultGate() above: a device must never be left parked on the
        // set-new-password gate just because the network revoke below failed.
        setRecovery(false)
        // #ASSUME: security (SEC-F5): purge authenticated data at rest so a
        // returned or handed-over device does not retain children's names,
        // story content, or reading progress after sign-out. Best-effort and
        // fire-and-forget: it must never block or fail the sign-out itself.
        // #VERIFY: AuthContext.test.tsx "sign-out purges cached data".
        void purgeAuthenticatedDataAtRest()
        const { error } = await supabase.auth.signOut()
        if (error) throw error
      },
      // #ASSUME: security: resetPasswordForEmail resolves regardless of whether
      // the address is registered (Supabase does not disclose it) and returns
      // { error } only on operational failures (e.g. rate limiting), so rethrow
      // lets the form surface a retryable error while the success path stays
      // neutral. redirectTo mirrors signInWithOAuth: the reset link must return
      // to the guardian login page, the only surface that loads supabase-js and
      // can process the recovery hash into a session + PASSWORD_RECOVERY event.
      // #VERIFY: AuthContext.test.tsx requestPasswordReset delegation + rejection.
      requestPasswordReset: async (email) => {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}`,
        })
        if (error) throw error
      },
      // #CRITICAL: security: updateUser sets the new password on the CURRENT
      // recovery session; rethrow on { error } so a weak/invalid password keeps
      // the user on the form to retry instead of silently failing. Clear
      // recovery only AFTER a confirmed success so the app auto-continues to the
      // console (the recovery session is now an ordinary signed-in session); a
      // failed update leaves recovery set and the form visible.
      // #VERIFY: AuthContext.test.tsx updatePassword clears/keeps recovery.
      // #ASSUME: security: this does not revoke any OTHER active session for
      // the account (e.g. a guardian signed in on a second device with the old
      // password). supabase-js's client-side updateUser() has no session-scope
      // parameter for this; only the Supabase Auth server config ("revoke
      // sessions on password change") or the admin API (auth.admin.signOut with
      // a scope) can do it, and neither is wired up here.
      // #VERIFY: confirm the Supabase project's Auth settings before R2
      // (revoke-other-sessions-on-password-change), or accept this as a known
      // limitation and document it in SECURITY.md.
      updatePassword: async (newPassword) => {
        const { error } = await supabase.auth.updateUser({ password: newPassword })
        if (error) throw error
        setRecovery(false)
      },
    }),
    [status, principal, authError, recovery, recoveryError]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
