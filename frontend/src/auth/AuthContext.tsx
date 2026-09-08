import type { AuthChangeEvent, Session } from '@supabase/supabase-js'
import { isAxiosError } from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import type { MeResponse } from '../client/types.gen'
import { useApi } from '../hooks/useApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import {
  AuthContext,
  type AuthContextValue,
  type AuthError,
  type AuthStatus,
  type VerificationStatus,
} from './authContext'
import { clearChildSession } from './childSession'
import { makeConsentApi } from './consentApi'
import { CONSENT_POLICY_VERSION, makeOnboardingApi } from './onboardingApi'
import { clearAdultGate, warmAdultGate } from './parentalGateState'
import { clearResidenceDraft, rememberResidenceDraft } from './residenceDraft'
import {
  consumeEarlySignInUserId,
  isPasswordRecovery,
  RECOVERY_BROADCAST_CHANNEL_NAME,
  recoveryErrorFromUrl,
  supabase,
} from './supabaseClient'
import { TOKEN_STORAGE_KEY } from './tokenStorageKey'
import { isRole, type Principal } from './types'

/**
 * Splits a failed principal resolution into "the backend never answered"
 * (transient, session still good) and "the backend answered and said no"
 * (terminal, session must be discarded).
 *
 * #CRITICAL: security: this decides whether a Supabase session SURVIVES a
 * failed resolution, so it fails closed by construction: 'terminal' is the
 * default and only two explicit signals escape it. A non-axios throw (the
 * unrecognized-role Error below, a TypeError, anything unforeseen) is
 * terminal because it is unclassifiable. A 401/403 is terminal because the
 * backend actively REJECTED this JWT; calling that transient would park a
 * dead session behind a retry button and tell the guardian to keep waiting
 * for a recovery that can never happen.
 * #VERIFY: AuthContext.test.tsx classification cases: network error and 503
 * reach 'backend-unreachable' with the token retained; 401, 403, 404, 422
 * and a plain Error reach 'signed-out' with the token removed.
 */
function classifyPrincipalError(err: unknown): 'transient' | 'terminal' {
  if (!isAxiosError(err)) return 'terminal'
  // #ASSUME: external-resources: axios leaves `response` undefined precisely
  // when the request never completed, which is the outage signature we care
  // about: connection refused, DNS failure, or the ECONNABORTED/ETIMEDOUT
  // timeout that the 2026-07-23 docker-host outage produced. Checking for the
  // absent response rather than matching err.code keeps this robust across
  // the several codes axios uses for that one situation.
  // #VERIFY: AuthContext.test.tsx network-error case asserts the transient
  // branch without setting err.code.
  if (err.response === undefined) return 'transient'
  // 5xx covers both our own API and an intermediary (Traefik 502/503/504),
  // neither of which is a statement about this session's validity.
  return err.response.status >= 500 ? 'transient' : 'terminal'
}

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
    const { clearReadingStates, clearPersonalizationValues } = await import('../offline/db')
    // ADR-023 P6: the values payload holds a child's real first name, a sibling's
    // name, and a pet name. On a returned or hand-me-down device that is exactly
    // the data a sign-out is asked to remove, and unlike reading state it says
    // nothing about which book it belongs to, so there is no narrower purge to
    // prefer.
    //
    // The two purges touch different stores, so they run independently via
    // allSettled rather than chained: awaiting them in sequence meant a
    // transient IndexedDB error in the first silently skipped the second, and
    // sign-out reported success with the child's name still at rest. A rejected
    // settlement is warned (the store name and the error only, never the
    // values) so the failure is observable instead of silent; neither failure
    // ever blocks the sign-out itself.
    const results = await Promise.allSettled([clearReadingStates(), clearPersonalizationValues()])
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const store = index === 0 ? 'reading states' : 'personalization values'
        console.warn(`sign-out purge failed for ${store}:`, result.reason)
      }
    })
  } catch (err) {
    // The offline-store module itself failed to load (or IndexedDB is wholly
    // unavailable): best-effort only, but still observable.
    console.warn('sign-out purge could not load the offline store:', err)
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
  const onboardingApi = useMemo(() => makeOnboardingApi(api), [api])
  const consentApi = useMemo(() => makeConsentApi(api), [api])
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [authError, setAuthError] = useState<AuthError | null>(null)
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | null>(null)
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
  // Set true on unmount (effect cleanup below); a ref, not an effect-local
  // closure variable, so recordConsent's manual re-sync (called from outside
  // the effect, after a guardian submits consent) observes the same
  // unmounted-provider guard as the effect's own calls.
  const cancelledRef = useRef(false)

  // #ASSUME: timing-dependencies: this re-fetches /me on every
  // onAuthStateChange event, including a periodic TOKEN_REFRESHED with an
  // unchanged role/family. That's wasted work, not a correctness bug, and
  // guardian sessions are low-frequency; revisit only if /me load becomes
  // measurable.
  // #VERIFY: test_auth_context.test_refetches_principal_on_token_refresh.
  //
  // `event` is Supabase's onAuthStateChange discriminator (undefined for the
  // initial getSession()-driven call in the effect below, which resolves a
  // possibly PERSISTED session, not a fresh sign-in, and for
  // recordConsent's manual re-sync). It is used for exactly one thing:
  // warming the adult gate (ADR-014 Phase 5) ONLY on a genuine 'SIGNED_IN'
  // event (a password submit or an OAuth redirect return), the moment the
  // guardian has just proven full credentials. Warming on any other event
  // -- in particular the initial session restore or a silent
  // 'TOKEN_REFRESHED' -- would let a stale/cached session, or a walked-away
  // auto-refreshing tab, look identical to a guardian who just typed a
  // password, defeating the step-up entirely.
  // The one documented exception is an OAuth return leg, whose 'SIGNED_IN'
  // can land before this provider subscribes and so is not always observable
  // here; that arm reads supabaseClient's early-sign-in capture instead, which
  // holds the same supabase-js event recorded by a module-scope subscriber.
  // Consuming that capture is single-use, so it warms one resolution and no
  // more. See the warm call below.
  // #CRITICAL: security: gate the warm call on event === 'SIGNED_IN' or a
  // consumed early sign-in, never on session presence alone.
  // #VERIFY: AuthContext.test.tsx "warms the adult gate on a SIGNED_IN
  // event, but not on session restore or token refresh".
  const syncPrincipal = useCallback(
    async (session: Session | null, event?: AuthChangeEvent) => {
      // #CRITICAL: security: consume the early-sign-in capture BEFORE any early
      // return below. Every exit from syncPrincipal has to spend it, or it
      // outlives the resolution it belonged to: a guardian who lands on the
      // needs-verification, awaiting-approval, or needs-consent interstitial
      // leaves through one of those returns and comes back later through
      // refreshStatus, recordConsent, or startVerification, and a capture still
      // pending then warms the gate and slides its idle TTL forward long after
      // the credential proof it stands for. Read it once here, hold it locally,
      // and decide whether to warm further down.
      // #VERIFY: AuthContext.test.tsx "does not warm a later resolution from a
      // capture an interstitial return left pending".
      const earlySignInUserId = consumeEarlySignInUserId()
      const seq = ++requestSeq.current
      // A later handler already superseded this one, or the provider unmounted.
      const isStale = () => cancelledRef.current || seq !== requestSeq.current

      if (session === null) {
        safeRemoveToken()
        clearResidenceDraft()
        if (!isStale()) {
          setPrincipal(null)
          setStatus('signed-out')
          setAuthError(null)
          setVerificationStatus(null)
        }
        return
      }
      try {
        // #EDGE: browser-compat: setItem throws in private-mode / quota-full
        // browsers. Keep it inside the try so a storage failure routes to the
        // fail-closed signed-out path below instead of stranding status on
        // 'loading' (it used to sit outside the try, where a throw was fatal).
        localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token)
        // #CRITICAL: security: resolve onboarding BEFORE /v1/me. A guardian
        // who has not passed parent verification, one awaiting approval, or
        // one who has not yet completed VPC consent, gets a User row that
        // require_principal rejects for GET /v1/me (401 "unknown subject" for
        // the first two; the third is merely ungated at /me but blocked later
        // at profile creation) -- calling /me first would just dump all three
        // cases into the generic 'principal-unresolved' catch below with no
        // way for the UI to tell them apart from a real failure. This is also
        // why the onboarding response, not MeResponse, is what carries the
        // verification pair: it is the only one these callers can read.
        // #VERIFY: AuthContext.test.tsx "awaiting-approval guardian never
        // calls /me", "unverified guardian never calls /me", and "unconsented
        // guardian never calls /me".
        const onboarded = await onboardingApi.onboard()
        if (isStale()) return
        setVerificationStatus(onboarded.verification_status)
        // #CRITICAL: security: ADR-018 D1 orders parent verification BEFORE
        // admin approval, so this branch must stay ABOVE the approval one
        // below. Reversing them would show an unverified guardian the
        // "awaiting approval" dead end and never route them to the one screen
        // that can move them forward, because approval will not arrive for an
        // account nobody has been asked to verify.
        //
        // Gated on verification_required, not on the status alone: a tier with
        // the flag off reports 'none' for every caller, which is the same
        // value a gated guardian who has not started reads, so keying on
        // `!== 'verified'` by itself would park every guardian on every
        // ungated deployment in front of a verification screen.
        // #VERIFY: AuthContext.test.tsx "routes an unverified guardian to
        // needs-verification ahead of awaiting-approval" and "leaves a
        // guardian alone while the tier does not require verification".
        if (
          onboarded.role === 'guardian' &&
          onboarded.verification_required &&
          onboarded.verification_status !== 'verified'
        ) {
          setPrincipal(null)
          setStatus('needs-verification')
          setAuthError(null)
          return
        }
        if (onboarded.role === 'guardian' && onboarded.status !== 'active') {
          setPrincipal(null)
          setStatus('awaiting-approval')
          setAuthError(null)
          return
        }
        if (onboarded.role === 'guardian' && !onboarded.consent_recorded) {
          setPrincipal(null)
          setStatus('needs-consent')
          setAuthError(null)
          return
        }
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
        // #CRITICAL: security: an OAuth return is a genuine fresh sign-in whose
        // 'SIGNED_IN' may never reach this provider: detectSessionInUrl fires
        // it from inside createClient's initialize(), and whether this
        // provider has subscribed by then is a race (see the module-scope
        // subscriber in supabaseClient.ts). Warming on the observed event
        // alone left Google guardians challenged on arrival by a gate whose
        // own "Continue with Google" button returned them to the identical
        // cold state: an endless bounce through Google with no way into the
        // console. The capture below carries that same supabase-js event,
        // recorded by a subscriber that cannot lose the race.
        // The capture was already consumed at the top of syncPrincipal, above
        // every early return, so it is spent exactly once per resolution
        // whether or not this line is reached. Comparing it against this
        // session's user is what stops a capture warming the gate for a
        // different account.
        // #VERIFY: AuthContext.test.tsx "warms the adult gate on an OAuth
        // return leg whose SIGNED_IN arrived before mount", "does not warm when
        // the captured sign-in names a different user", and "does not re-warm
        // on a later refreshStatus in the same page load".
        if (event === 'SIGNED_IN' || earlySignInUserId === session.user.id) {
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
        // A transient failure says nothing about whether this session is
        // valid, so handling it identically to a rejection is what produced
        // the 2026-07-23 login loop (#452): sign-out sent the guardian back to
        // login, login re-established the same working Supabase session, and
        // resolution failed again against the same downed backend. Keep the
        // token and route to the retry interstitial instead. The terminal
        // branch below is unchanged.
        if (classifyPrincipalError(err) === 'transient') {
          if (!isStale()) {
            setPrincipal(null)
            setStatus('backend-unreachable')
            // Not an authError: LoginPage's inline "couldn't load your
            // account" banner is for the terminal case, and this path is
            // leaving the login page entirely.
            setAuthError(null)
          }
          return
        }
        safeRemoveToken()
        if (!isStale()) {
          setPrincipal(null)
          setStatus('signed-out')
          setAuthError('principal-unresolved')
        }
      }
    },
    [api, onboardingApi]
  )

  useEffect(() => {
    cancelledRef.current = false

    // Fire-and-forget: this runs inside a useEffect with no async cleanup
    // seam, and the `cancelledRef` flag (checked inside syncPrincipal)
    // already guards against a resolved-after-unmount state update.
    void supabase.auth.getSession().then(({ data }) => {
      if (!cancelledRef.current) void syncPrincipal(data.session)
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
      cancelledRef.current = true
      subscription.unsubscribe()
    }
  }, [syncPrincipal])

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
      verificationStatus,
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
        // Same deterministic-clear reasoning one field over: the remembered
        // verification country belongs to the adult who is leaving, and a
        // handed-over device must not pre-fill it into the next person's
        // consent form. The SIGNED_OUT event's syncPrincipal(null) clears it
        // too, but that is async and this hand-over is not.
        clearResidenceDraft()
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
        // #VERIFY: AuthContext.test.tsx "sign-out purges cached data" and
        // "sign-out purges cached personalization values (ADR-023 P6)".
        void purgeAuthenticatedDataAtRest()
        // #CRITICAL: security: 'local' is passed EXPLICITLY because supabase-js
        // defaults to scope 'global', which revokes every refresh token the
        // account holds, on every device. Every caller of this primitive is
        // device-local by intent: the shell "Sign out" buttons, AdultGate's
        // switch-account, the verification/approval/backend-down escape
        // hatches, and above all the two kid-handover paths (LoginPage's
        // authorize-device, ConsolePage's handoff), which sign the guardian out
        // OF A KID'S DEVICE. Under the default, a parent handing the iPad to a
        // child silently killed their own session on their phone and laptop,
        // and a guardian signing out of one browser logged themselves out of
        // all the others. There is no "sign out everywhere" surface in this app
        // that would want the global behaviour; if one is ever added it must
        // pass its own scope here rather than removing this argument.
        // 'local' still clears local state on every path: auth-js runs
        // removeCurrentSession() for any scope other than 'others', on both the
        // success and the error branch, so the SIGNED_OUT event and the
        // fail-closed clearing above are unaffected.
        // #VERIFY: AuthContext.test.tsx "signs out only this device, never the
        // account's other sessions".
        const { error } = await supabase.auth.signOut({ scope: 'local' })
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
      // Settled 2026-08-04, taking the second branch of this note's original
      // instruction (confirm the setting, or accept and document it): the live
      // Management API auth config exposes NO
      // revoke-sessions-on-password-change setting to turn on, and the session
      // controls that do exist are all off in production
      // (sessions_single_per_user false, sessions_timebox 0,
      // sessions_inactivity_timeout 0). So this is a platform limitation, not a
      // switch anyone forgot. Accepted and documented in SECURITY.md under
      // "Known Infrastructure Limitations". Reopening this needs a backend
      // endpoint calling auth.admin.signOut with a scope, since
      // sessions_single_per_user would sign legitimate multi-device guardians
      // out of their own sessions.
      // #VERIFY: this acceptance holds only while password change is
      // recovery-only (reached via resetPasswordForEmail above). Re-open it if
      // a logged-in change-password surface is ever added, since an attacker
      // who already holds a session could then change the password and keep
      // every other device signed in.
      updatePassword: async (newPassword) => {
        const { error } = await supabase.auth.updateUser({ password: newPassword })
        if (error) throw error
        setRecovery(false)
      },
      // #ASSUME: security: no signature-image capture (Route B from
      // ADR-018 D1's decision record); signerName is a typed full-legal-name
      // attestation, the FTC 312.5(b)(2)(i) "sign and submit electronically"
      // method layered on the OAuth login that already authenticated this
      // session. residenceCountry (O-117) travels alongside it on the same
      // submission; adulthood_attested (O-119) is hardcoded true here
      // because GuardianConsentPage only allows this call once its own
      // adulthood checkbox is checked, mirroring accepted: true above.
      // Rethrows on failure (e.g. the backend's 422 for an empty name or a
      // malformed country code) so GuardianConsentPage can show it; on
      // success, re-runs the full syncPrincipal flow (fresh getSession(), no
      // event) so the now-consented guardian proceeds straight to /v1/me and
      // 'signed-in' instead of needing a second trigger.
      // #VERIFY: AuthContext.test.tsx recordConsent success/failure cases.
      recordConsent: async (signerName, residenceCountry) => {
        await onboardingApi.onboard({
          accepted: true,
          policy_version: CONSENT_POLICY_VERSION,
          signer_name: signerName,
          residence_country: residenceCountry,
          adulthood_attested: true,
        })
        const { data } = await supabase.auth.getSession()
        await syncPrincipal(data.session)
      },
      // #ASSUME: external-resources: this calls a route that mails a real
      // person, and refusing is a normal answer rather than a fault: the
      // endpoint returns 409 while an email is already in flight and 429 once
      // the hourly cap is spent (api/consent.py). Both are rethrown for the
      // page to render as guidance, not swallowed, because a silent no-op
      // here reads to a waiting parent as "the button is broken".
      //
      // The country is remembered locally BEFORE the request rather than
      // after: the consent form's pre-fill is a convenience that should
      // survive a refused send just as well as a successful one, since the
      // adult picked the same country either way.
      // #VERIFY: GuardianVerificationPage.test.tsx 409/429 cases.
      startVerification: async (location) => {
        rememberResidenceDraft(location)
        await consentApi.startKwsVerification(location)
        // Re-resolve rather than assuming 'pending': the row this call just
        // created is the same row the next onboarding read reports on, so
        // reading it back keeps this state a projection of the server's
        // answer instead of a second, independently-maintained copy of it.
        const { data } = await supabase.auth.getSession()
        await syncPrincipal(data.session)
      },
      // P-6d: same tail as recordConsent above, minus the onboarding submit:
      // re-reads the current Supabase session and re-runs syncPrincipal's
      // onboarding-then-me resolution. For a still-awaiting-approval
      // guardian this correctly re-hits the same short-circuit that keeps
      // GET /v1/me from ever being called (see 'awaiting-approval' doc on
      // AuthStatus), so a recheck before approval is a harmless no-op that
      // just leaves status unchanged.
      // #VERIFY: AuthContext.test.tsx / GuardianAwaitingApprovalPage.test.tsx
      // refreshStatus cases.
      refreshStatus: async () => {
        const { data } = await supabase.auth.getSession()
        await syncPrincipal(data.session)
      },
    }),
    [
      status,
      principal,
      authError,
      verificationStatus,
      recovery,
      recoveryError,
      onboardingApi,
      consentApi,
      syncPrincipal,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
