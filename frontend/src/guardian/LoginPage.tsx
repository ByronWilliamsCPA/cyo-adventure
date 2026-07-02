import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import './guardian.css'

/**
 * Guardian sign-in via Supabase Auth (ADR-009): native Apple and Google.
 * There is no dev-stub form here even locally; Supabase's OAuth flow works
 * the same in every environment, unlike the backend's local-only bearer stub.
 */
export function LoginPage() {
  const { status, signInWithOAuth } = useAuth()
  const [signInError, setSignInError] = useState(false)
  const location = useLocation()
  const state = location.state as { from?: { pathname?: string } } | null
  const from = state?.from?.pathname ?? '/guardian'

  useEffect(() => {
    document.title = 'Sign in - CYO Adventure'
  }, [])

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
      <button
        type="button"
        className="guardian-login__provider"
        onClick={() => void startSignIn('apple')}
      >
        Continue with Apple
      </button>
      {signInError ? (
        <p role="alert" className="guardian-login__error">
          Sign-in didn&apos;t start. Check your connection and try again.
        </p>
      ) : null}
    </div>
  )
}
