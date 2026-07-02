import { useEffect } from 'react'
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
  const location = useLocation()
  const state = location.state as { from?: { pathname?: string } } | null
  const from = state?.from?.pathname ?? '/guardian'

  useEffect(() => {
    document.title = 'Sign in - CYO Adventure'
  }, [])

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
        onClick={() => void signInWithOAuth('google')}
      >
        Continue with Google
      </button>
      <button
        type="button"
        className="guardian-login__provider"
        onClick={() => void signInWithOAuth('apple')}
      >
        Continue with Apple
      </button>
    </div>
  )
}
