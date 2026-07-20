import { isAuthApiError } from '@supabase/supabase-js'
import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { hasValidDeviceGrant, setDeviceGrant } from '../auth/deviceGrant'
import { makeDeviceGrantApi } from '../auth/deviceGrantApi'
import type { Principal } from '../auth/types'
import { useAuth } from '../auth/useAuth'
import { flagEnabled } from '../env'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import {
  ADMIN_CONSOLE_PATH,
  AUTHORIZE_DEVICE_INTENT_PARAM,
  AUTHORIZE_DEVICE_INTENT_VALUE,
  GUARDIAN_AWAITING_APPROVAL_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  KID_PICKER_PATH,
} from '../routes'
import './guardian.css'
import { SetNewPasswordForm } from './SetNewPasswordForm'

/**
 * Whether `pathname` is a location `principal` can actually land on, mirroring
 * router.tsx's ProtectedRoute allowedRoles config: `/admin/*` requires the
 * admin CAPABILITY; `/guardian/*` admits either the guardian base role or the
 * admin capability (an admin-only adult who deep-links into /guardian is not
 * bounced there, per router.tsx's comment on that route). Anything outside
 * the adult subtree is treated as reachable; ProtectedRoute is the real
 * enforcement boundary, this only picks a sane post-login destination so we
 * do not hand a `from` to `<Navigate>` that ProtectedRoute would reject.
 *
 * #ASSUME: security: this duplicates ProtectedRoute's allowedRoles logic
 * instead of importing it (ProtectedRoute is a component, not an exported
 * predicate). A drift between the two would only misroute the post-login
 * landing spot; ProtectedRoute still independently enforces access.
 * #VERIFY: LoginPage.test.tsx "does not honor a from path the principal
 * cannot reach".
 */
function isReachableForPrincipal(pathname: string, principal: Principal): boolean {
  if (pathname.startsWith(ADMIN_CONSOLE_PATH)) return principal.isAdmin
  if (pathname.startsWith(GUARDIAN_CONSOLE_PATH)) {
    return principal.role === 'guardian' || principal.isAdmin
  }
  return true
}

/**
 * Whether a login return path (`location.state.from.pathname`, the contract
 * ProtectedRoute and DeviceAuthorizedRoute share via `state={{ from: location }}`)
 * stays inside this app.
 *
 * #CRITICAL: security: `state.from` rides in history state, which is
 * script-writable (a crafted link or a compromised page can plant it), so
 * honoring it blindly would turn the post-login redirect into an open-redirect
 * vector. Only a same-app path is followed: it must start with '/' (rejects
 * absolute URLs such as 'https://evil.example') and must not start with '//'
 * or '/\' (both become scheme-relative URLs once they reach the History API /
 * URL parser, which treats a backslash like a forward slash). Anything else
 * falls back to the role-based console default.
 * #VERIFY: LoginPage.test.tsx "open-redirect guard" cases (absolute URL,
 * '//host', and '/\host' state.from all fall back to the default).
 */
function isSameAppPath(pathname: string): boolean {
  return pathname.startsWith('/') && !pathname.startsWith('//') && !pathname.startsWith('/\\')
}

/**
 * How long the form waits, after a successful password submit, for
 * AuthProvider to resolve /me out-of-band (status -> signed-in, or authError)
 * before the watchdog re-enables it. Exported for the fake-timer tests.
 */
export const SIGN_IN_WATCHDOG_MS = 10_000

/**
 * How long the device-authorization effect waits for the grant mint to
 * settle before giving up. Exported for the fake-timer tests.
 */
export const DEVICE_MINT_WATCHDOG_MS = 10_000

/** Cancel a pending sign-in watchdog, if one is armed. */
function clearWatchdog(ref: RefObject<number | null>): void {
  if (ref.current !== null) {
    window.clearTimeout(ref.current)
    ref.current = null
  }
}

/**
 * Distinguishes a genuine bad-credentials failure from an operational one
 * (network down, rate-limited, 5xx). Supabase returns the SAME
 * `invalid_credentials` code for both a wrong password and an unknown email, so
 * keying on it leaks nothing about whether the email exists. We match on the
 * stable error `code` (Supabase's recommended discriminator) via
 * `isAuthApiError`, not the HTTP status or `instanceof`, per their docs. We must
 * not tell a parent on flaky wifi that their password is wrong.
 */
function isInvalidCredentials(err: unknown): boolean {
  return isAuthApiError(err) && err.code === 'invalid_credentials'
}

/**
 * Guardian sign-in via Supabase Auth (ADR-009): Google OAuth (Apple is gated,
 * see below) plus an email/password form for accounts provisioned directly in
 * Supabase (e.g. the R1 family logins). Both paths establish a Supabase session
 * that the AuthProvider resolves to a backend Principal via /me; the form adds
 * no new auth machinery, only a second entry point into the same flow.
 */
export function LoginPage() {
  const {
    status,
    principal,
    authError,
    recovery,
    recoveryError,
    signInWithOAuth,
    signInWithPassword,
    signOut,
    requestPasswordReset,
  } = useAuth()
  const [signInError, setSignInError] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<'credentials' | 'connection' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // True once the sign-in watchdog fired: the post-submit resolution stalled
  // (neither signed-in nor authError arrived in time), the form has been
  // re-enabled, and the transient "taking longer than expected" note shows.
  const [stalled, setStalled] = useState(false)
  const watchdogRef = useRef<number | null>(null)
  // A failed recovery link (expired/already-used) means there is nothing to
  // recover into, so pre-open the reset-request panel instead of leaving the
  // guardian to rediscover "Forgot your password?" on their own.
  const [showReset, setShowReset] = useState(Boolean(recoveryError))
  const [resetEmail, setResetEmail] = useState('')
  const [resetStatus, setResetStatus] = useState<'idle' | 'sent' | 'error'>('idle')
  const [resetSubmitting, setResetSubmitting] = useState(false)
  const [deviceAuthState, setDeviceAuthState] = useState<'idle' | 'authorizing' | 'failed'>('idle')
  const deviceWatchdogRef = useRef<number | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const api = useApi()
  const state = location.state as { from?: { pathname?: string } } | null
  // ADR-014 section 5: the Kids door (and DeviceAuthorizedRoute, for a kid
  // deep link) sends a signed-out visitor here with ?intent=authorize-device
  // when this device has no valid device grant. Once that guardian resolves
  // to a signed-in principal, the effect below mints a grant for THIS device
  // instead of following the normal role-based redirect, then drops the
  // guardian back to the kid surface they came from (deviceReturnPath).
  const authorizeDeviceIntent =
    new URLSearchParams(location.search).get(AUTHORIZE_DEVICE_INTENT_PARAM) ===
    AUTHORIZE_DEVICE_INTENT_VALUE
  // An admin-only adult (base role 'admin', no family guardianship) lands on
  // the admin console; everyone else (guardian, dual-role) starts at the
  // guardian console, their day-to-day home (the admin link is one hop away
  // via GuardianShell). The role-based default is resolved BEFORE
  // considering `from`, so a `from` that is unreachable for this principal
  // (e.g. a stale deep link into a subtree they no longer/never held) falls
  // back to the default instead of handing <Navigate> a path ProtectedRoute
  // would reject.
  const home = principal?.role === 'admin' ? ADMIN_CONSOLE_PATH : GUARDIAN_CONSOLE_PATH
  const requestedFrom = state?.from?.pathname
  // The same-app screen (isSameAppPath's open-redirect guard) applies first;
  // only a surviving path is then checked for principal reachability.
  const safeFrom = requestedFrom && isSameAppPath(requestedFrom) ? requestedFrom : undefined
  const from =
    safeFrom && principal && isReachableForPrincipal(safeFrom, principal) ? safeFrom : home
  // Where the authorize-device flow drops the guardian after minting: the
  // kid-surface location the child was originally heading for
  // (DeviceAuthorizedRoute's state.from, e.g. a /read/... deep link), or the
  // picker when the Kids door was entered directly. Beyond the same-app
  // guard the path is deliberately not pre-validated here: a kid route still
  // crosses DeviceAuthorizedRoute on arrival, which re-gates it against the
  // freshly minted grant.
  const deviceReturnPath = safeFrom ?? KID_PICKER_PATH

  // Apple sign-in is hidden until it is actually configured in Supabase (it
  // needs a paid Apple Developer account and a signed, expiring client secret).
  // Showing a button that can only fail is worse than hiding it; flip
  // VITE_ENABLE_APPLE_OAUTH=true once the provider is live. Google's button is
  // always rendered; it is the only always-on provider, Apple the only gated one.
  const appleEnabled = flagEnabled(import.meta.env.VITE_ENABLE_APPLE_OAUTH)

  useEffect(() => {
    document.title = 'Sign in - CYO Adventure'
  }, [])

  // ADR-014 section 5: authorize-then-return. Gated on a RESOLVED principal
  // (not just a Supabase session) so this never races AuthProvider's /me
  // lookup; `status === 'signed-in'` only flips once a Principal exists.
  //
  // #CRITICAL: security: minting a device grant requires a guardian/admin
  // bearer, but an admin-only adult with no family (base role 'admin', no
  // guardian capability) will get a mint REJECTION from the backend (no
  // family to scope the grant to). That failure MUST fall through to
  // 'failed' so the guardian still lands on their own console via the normal
  // <Navigate to={from}> below, never a crash or a stuck spinner.
  // #VERIFY: LoginPage.test.tsx "falls back to the normal redirect when the
  // mint is rejected (e.g. admin-only, no family)".
  useEffect(() => {
    // #EDGE: security: an unusual URL could combine a device-authorization
    // intent with an active recovery landing; recovery must win so the
    // guardian sets a new password before any device grant is minted on
    // their behalf.
    if (!authorizeDeviceIntent || status !== 'signed-in' || !principal || recovery) return
    if (hasValidDeviceGrant()) {
      // Defensive: a grant already covers this device (e.g. a second tab
      // completed the mint first). Still shed the guardian session before
      // continuing, for the same reason the mint path does (see the #CRITICAL
      // below): a signed-in guardian landing on the kid surface must not leave
      // a live auth_token behind on a kid device.
      void navigate(deviceReturnPath, { replace: true })
      void signOut().catch((err: unknown) => {
        logApiError('sign-out after device authorization failed', err)
      })
      return
    }
    let cancelled = false
    async function authorizeThisDevice() {
      setDeviceAuthState('authorizing')
      // #ASSUME: timing dependencies: if mint() never settles (a hung
      // request, or a dropped connection the client never surfaces as a
      // rejection), the guardian would be stuck on "Setting up this
      // device..." forever with no way out. The watchdog forces
      // deviceAuthState to 'failed' after DEVICE_MINT_WATCHDOG_MS so the
      // render below falls through to the normal role-based redirect,
      // mirroring the sign-in form's SIGN_IN_WATCHDOG_MS.
      // #VERIFY: LoginPage.test.tsx "device-mint watchdog" cases.
      deviceWatchdogRef.current = window.setTimeout(() => {
        deviceWatchdogRef.current = null
        if (cancelled) return
        setDeviceAuthState('failed')
      }, DEVICE_MINT_WATCHDOG_MS)
      try {
        const view = await makeDeviceGrantApi(api).mint()
        clearWatchdog(deviceWatchdogRef)
        if (cancelled) return
        setDeviceGrant({
          token: view.token,
          expiresAt: view.expires_at,
          familyId: view.family_id,
          id: view.id,
        })
        // Hand the now kid-authorized device back to the kid surface (the
        // deep link the child was heading for, or the picker) BEFORE signing
        // the guardian out: signOut() flips status to 'signed-out', which
        // trips this effect's cleanup (cancelled = true), so anything gated on
        // `cancelled` after it would never run. Navigate first, clean up after.
        void navigate(deviceReturnPath, { replace: true })
        // #CRITICAL: security: the device now holds a durable, revocable device
        // grant, so the guardian's live Supabase session (and its auth_token)
        // must NOT linger on what is henceforth a kid device. If it did, the
        // request interceptor's guardian-bearer fallthrough (useApi.ts) would
        // attach the guardian token on /library and /read, letting a child read
        // the whole family's library instead of only their assigned books.
        // signOut() clears the Supabase session, auth_token, and any child
        // session (via onAuthStateChange -> safeRemoveToken). Fire-and-forget
        // and swallow-with-log: the grant already succeeded, so a signOut
        // failure must neither present as an authorization failure nor block
        // the hand-off, and it is deliberately NOT gated on `cancelled` because
        // navigate() unmounts this page yet the cleanup must still run.
        // #VERIFY: LoginPage.test.tsx "signs the guardian out after minting the
        // device grant".
        void signOut().catch((err: unknown) => {
          logApiError('sign-out after device authorization failed', err)
        })
      } catch (err) {
        clearWatchdog(deviceWatchdogRef)
        if (cancelled) return
        logApiError('device grant mint failed', err)
        setDeviceAuthState('failed')
      }
    }
    void authorizeThisDevice()
    return () => {
      cancelled = true
      clearWatchdog(deviceWatchdogRef)
    }
  }, [authorizeDeviceIntent, status, principal, recovery, api, navigate, signOut, deviceReturnPath])

  // #ASSUME: security: a submitted password leaves `submitting` true on success
  // because sign-in completes out-of-band (status -> signed-in fires the
  // redirect and unmounts this page). If instead the session cannot resolve to a
  // Principal (bad/rejected JWT, unrecognized role, or a Supabase subject with no
  // backend User row, the exact case for a freshly-provisioned login),
  // AuthProvider fails closed and sets authError. Deriving `busy` from both means
  // an authError instantly un-busies the form on the same render, re-enabling the
  // button and revealing the "couldn't load your account" message, with no
  // setState-in-effect (which would trip react-hooks/set-state-in-effect and
  // cause a cascading render).
  // #VERIFY: LoginPage.test.tsx renders the unresolved message when authError is set.
  const busy = submitting && !authError

  // The watchdog only guards the out-of-band wait after a successful submit;
  // once authError lands, the derived `busy` above has already re-enabled the
  // form on the same render, so the pending timer is obsolete. Clearing (not
  // firing) it keeps the transient stall note from stacking on the authError
  // alert. No setState here, so no cascading render.
  useEffect(() => {
    if (authError) clearWatchdog(watchdogRef)
  }, [authError])

  // A late watchdog must never fire into an unmounted page: in the happy path
  // the status -> signed-in redirect unmounts this component mid-wait.
  useEffect(() => () => clearWatchdog(watchdogRef), [])

  // #EDGE: external-resources: signInWithOAuth rejects when Supabase cannot
  // start the OAuth redirect (network down, misconfigured provider). Without
  // this handler the click would silently no-op.
  // #VERIFY: App.test.tsx covers the login error message on OAuth failure.
  async function startSignIn(provider: 'google' | 'apple') {
    setSignInError(false)
    try {
      await signInWithOAuth(provider)
    } catch {
      setSignInError(true)
    }
  }

  // #ASSUME: security: signInWithPassword rejects on failure (the context
  // rethrows Supabase's { error }). We split the outcome: the
  // `invalid_credentials` code is wrong-password OR unknown-email (Supabase
  // returns the same code for both), shown as one generic message so the form
  // never reveals whether an email is registered; anything else (network, 429,
  // 5xx) is an operational failure and says so. On RESOLUTION the user is not yet signed in, only a session
  // exists; the redirect fires when AuthProvider resolves the Principal (status
  // -> signed-in), and the derived `busy` above un-busies the form if it cannot.
  // The password lives only in component state; we never persist it.
  // #VERIFY: LoginPage.test.tsx covers the generic and connection error messages.
  async function submitPassword() {
    setFormError(null)
    setStalled(false)
    clearWatchdog(watchdogRef)
    setSubmitting(true)
    try {
      await signInWithPassword({ email, password })
      // Leave submitting true: success is signalled out-of-band (status ->
      // signed-in triggers the redirect, or authError re-enables the form).
      // #ASSUME: timing dependencies: if NEITHER signal ever arrives (a hung
      // /me lookup, a dropped connection AuthProvider never surfaces), the
      // button would read "Signing in..." forever. The watchdog re-enables
      // the form after SIGN_IN_WATCHDOG_MS with a transient note so the
      // guardian can retry instead of being stranded.
      // #VERIFY: LoginPage.test.tsx "sign-in watchdog" cases.
      watchdogRef.current = window.setTimeout(() => {
        watchdogRef.current = null
        setSubmitting(false)
        setStalled(true)
      }, SIGN_IN_WATCHDOG_MS)
    } catch (err) {
      setFormError(isInvalidCredentials(err) ? 'credentials' : 'connection')
      setSubmitting(false)
    }
  }

  // #ASSUME: security: requestPasswordReset resolves whether or not the address
  // is registered (Supabase does not disclose it), so a resolution always maps
  // to the neutral "if an account exists" confirmation, never a "sent" that
  // would confirm the email. Only an operational rejection (rate limit, network,
  // 5xx) surfaces a distinct, retryable connection error. Enumeration-resistant
  // by construction, matching the login form's generic-credentials stance.
  // #VERIFY: LoginPage.test.tsx forgot-password neutral-confirmation + error.
  async function submitReset() {
    setResetStatus('idle')
    setResetSubmitting(true)
    try {
      await requestPasswordReset(resetEmail)
      setResetStatus('sent')
    } catch (err) {
      // The user-facing message stays the same generic "couldn't send a
      // reset link" regardless of cause (no enumeration leak either way);
      // logging the real cause here is what makes a genuine bug
      // distinguishable from a transient network blip in production
      // monitoring, since nothing else observes this rejection.
      logApiError('password-reset request failed', err)
      setResetStatus('error')
    } finally {
      setResetSubmitting(false)
    }
  }

  // Recovery-link return leg (ADR-009 password reset). The link established a
  // session, so `status` is (or is becoming) 'signed-in', but the guardian must
  // set a new password before continuing rather than being redirected to the
  // console. Checked BEFORE the signed-in redirect for exactly that reason. On a
  // successful update the context clears `recovery`, this branch falls away, and
  // the signed-in redirect below auto-continues them to their console.
  if (recovery) {
    return (
      <div className="guardian-login">
        <SetNewPasswordForm />
      </div>
    )
  }

  // A guardian who navigates straight to /guardian/login already has a real
  // Supabase session in these two states (AuthContext resolved that far
  // before stopping short of 'signed-in'); send them to the matching
  // interstitial instead of showing a login form for a session that already
  // exists. Mirrors ProtectedRoute's own handling of the same two statuses.
  if (status === 'awaiting-approval') {
    return <Navigate to={GUARDIAN_AWAITING_APPROVAL_PATH} replace />
  }
  if (status === 'needs-consent') {
    return <Navigate to={GUARDIAN_CONSENT_PATH} replace />
  }

  if (status === 'signed-in') {
    // While the device-authorization mint is in flight, hold here instead of
    // firing the normal redirect; the effect above navigates to the kid
    // picker on success. On failure (deviceAuthState === 'failed') fall
    // through to the normal redirect so the guardian still lands somewhere
    // useful and can authorize the device manually from their console.
    if (authorizeDeviceIntent && deviceAuthState !== 'failed') {
      return (
        <div role="status" aria-live="polite">
          Setting up this device...
        </div>
      )
    }
    // A failed mint deliberately ignores `from`: in the device flow it points
    // back into the kid surface, which still lacks the grant that just failed
    // to mint, so DeviceAuthorizedRoute would bounce straight back here and
    // retry the mint forever. Land on the role-based console instead, where
    // the guardian can set the device up manually.
    return <Navigate to={authorizeDeviceIntent ? home : from} replace />
  }

  return (
    <div className="guardian-login">
      <h1>Guardian sign-in</h1>
      <p>Sign in to review, approve, and request stories for your family.</p>
      {recoveryError ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          That password reset link is invalid or has expired. Request a new one below.
        </p>
      ) : null}
      <button
        type="button"
        className="guardian-login__provider"
        onClick={() => void startSignIn('google')}
      >
        Continue with Google
      </button>
      {appleEnabled ? (
        <button
          type="button"
          className="guardian-login__provider"
          onClick={() => void startSignIn('apple')}
        >
          Continue with Apple
        </button>
      ) : null}
      {signInError ? (
        <p role="alert" className="guardian-login__error cyo-text-error">
          Sign-in didn&apos;t start. Check your connection and try again.
        </p>
      ) : null}

      <div className="guardian-login__divider">
        <span>or use your email</span>
      </div>

      <form
        className="guardian-login__form"
        onSubmit={(event) => {
          event.preventDefault()
          void submitPassword()
        }}
      >
        <label className="guardian-login__field cyo-field">
          <span>Email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            className="cyo-field__control"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="guardian-login__field cyo-field">
          <span>Password</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            className="cyo-field__control"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="guardian-login__provider" disabled={busy}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
        {!busy && formError === 'credentials' ? (
          <p role="alert" className="guardian-login__error cyo-text-error">
            That email and password didn&apos;t match. Please try again.
          </p>
        ) : null}
        {!busy && formError === 'connection' ? (
          <p role="alert" className="guardian-login__error cyo-text-error">
            We couldn&apos;t reach the server. Check your connection and try again.
          </p>
        ) : null}
        {!busy && !formError && authError ? (
          <p role="alert" className="guardian-login__error cyo-text-error">
            You&apos;re signed in, but we couldn&apos;t load your account. Please try again.
          </p>
        ) : null}
        {!busy && stalled && !formError && !authError ? (
          <p role="status" aria-live="polite" className="guardian-login__note">
            This is taking longer than expected. Please try again.
          </p>
        ) : null}
      </form>

      <button
        type="button"
        className="guardian-login__link"
        onClick={() => setShowReset((open) => !open)}
        aria-expanded={showReset}
      >
        Forgot your password?
      </button>
      {showReset ? (
        <form
          className="guardian-login__form"
          onSubmit={(event) => {
            event.preventDefault()
            void submitReset()
          }}
        >
          <label className="guardian-login__field cyo-field">
            <span>Email for reset link</span>
            <input
              type="email"
              name="reset-email"
              autoComplete="email"
              required
              className="cyo-field__control"
              value={resetEmail}
              onChange={(e) => setResetEmail(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="guardian-login__provider"
            disabled={resetSubmitting}
          >
            {resetSubmitting ? 'Sending...' : 'Send reset link'}
          </button>
          {resetStatus === 'sent' ? (
            <p role="status" aria-live="polite" className="guardian-login__note">
              If an account exists for that email, we&apos;ve sent a reset link. Check your inbox.
            </p>
          ) : null}
          {resetStatus === 'error' ? (
            <p role="alert" className="guardian-login__error cyo-text-error">
              We couldn&apos;t send a reset link. Check your connection and try again.
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  )
}
