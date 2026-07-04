import { AuthApiError } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { flagEnabled } from '../env'
import './guardian.css'

/**
 * Distinguishes a genuine bad-credentials failure (Supabase returns HTTP 400
 * `invalid_credentials` for BOTH a wrong password and an unknown email, so this
 * leaks nothing about whether the email exists) from an operational failure
 * (network down, rate-limited, 5xx). We must not tell a parent on flaky wifi
 * that their password is wrong.
 */
function isInvalidCredentials(err: unknown): boolean {
  return err instanceof AuthApiError && err.status === 400
}

/**
 * Guardian sign-in via Supabase Auth (ADR-009): Google OAuth (Apple is gated,
 * see below) plus an email/password form for accounts provisioned directly in
 * Supabase (e.g. the R1 family logins). Both paths establish a Supabase session
 * that the AuthProvider resolves to a backend Principal via /me; the form adds
 * no new auth machinery, only a second entry point into the same flow.
 */
export function LoginPage() {
  const { status, authError, signInWithOAuth, signInWithPassword } = useAuth()
  const [signInError, setSignInError] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<'credentials' | 'connection' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const location = useLocation()
  const state = location.state as { from?: { pathname?: string } } | null
  const from = state?.from?.pathname ?? '/guardian'

  // Apple sign-in is hidden until it is actually configured in Supabase (it
  // needs a paid Apple Developer account and a signed, expiring client secret).
  // Showing a button that can only fail is worse than hiding it; flip
  // VITE_ENABLE_APPLE_OAUTH=true once the provider is live. Google's button is
  // always rendered; it is the only always-on provider, Apple the only gated one.
  const appleEnabled = flagEnabled(import.meta.env.VITE_ENABLE_APPLE_OAUTH)

  useEffect(() => {
    document.title = 'Sign in - CYO Adventure'
  }, [])

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
  // rethrows Supabase's { error }). We split the outcome: a 400 is
  // wrong-password OR unknown-email (Supabase returns the same code for both),
  // shown as one generic message so the form never reveals whether an email is
  // registered; anything else (network, 429, 5xx) is an operational failure and
  // says so. On RESOLUTION the user is not yet signed in, only a session
  // exists; the redirect fires when AuthProvider resolves the Principal (status
  // -> signed-in), and the derived `busy` above un-busies the form if it cannot.
  // The password lives only in component state; we never persist it.
  // #VERIFY: LoginPage.test.tsx covers the generic and connection error messages.
  async function submitPassword() {
    setFormError(null)
    setSubmitting(true)
    try {
      await signInWithPassword({ email, password })
      // Leave submitting true: success is signalled out-of-band (status ->
      // signed-in triggers the redirect, or authError triggers the effect).
    } catch (err) {
      setFormError(isInvalidCredentials(err) ? 'credentials' : 'connection')
      setSubmitting(false)
    }
  }

  if (status === 'signed-in') {
    return <Navigate to={from} replace />
  }

  return (
    <div className="guardian-login">
      <h1>Guardian sign-in</h1>
      <p>Sign in to review, approve, and request stories for your family.</p>
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
        <p role="alert" className="guardian-login__error">
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
        <label className="guardian-login__field">
          <span>Email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="guardian-login__field">
          <span>Password</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="guardian-login__provider" disabled={busy}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
        {!busy && formError === 'credentials' ? (
          <p role="alert" className="guardian-login__error">
            That email and password didn&apos;t match. Please try again.
          </p>
        ) : null}
        {!busy && formError === 'connection' ? (
          <p role="alert" className="guardian-login__error">
            We couldn&apos;t reach the server. Check your connection and try again.
          </p>
        ) : null}
        {!busy && !formError && authError ? (
          <p role="alert" className="guardian-login__error">
            You&apos;re signed in, but we couldn&apos;t load your account. Please try again.
          </p>
        ) : null}
      </form>
    </div>
  )
}
