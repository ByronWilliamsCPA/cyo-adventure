import { AuthApiError } from '@supabase/supabase-js'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { InitialEntry } from 'react-router-dom'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue } from '../auth/authContext'
import { LoginPage } from './LoginPage'

const mockSignInWithOAuth = vi.fn()
const mockSignInWithPassword = vi.fn()
let authStatus: AuthContextValue['status'] = 'signed-out'
let authErrorValue: AuthContextValue['authError'] = null

vi.mock('../auth/useAuth', () => ({
  useAuth: (): Pick<
    AuthContextValue,
    'status' | 'authError' | 'signInWithOAuth' | 'signInWithPassword' | 'signOut'
  > => ({
    status: authStatus,
    authError: authErrorValue,
    signInWithOAuth: mockSignInWithOAuth,
    signInWithPassword: mockSignInWithPassword,
    signOut: vi.fn(),
  }),
}))

/** Renders the login page plus stand-in targets so a redirect is observable. */
function renderLogin(initialEntries: InitialEntry[] = ['/guardian/login']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/guardian/login" element={<LoginPage />} />
        <Route path="/guardian" element={<div>console landing</div>} />
        <Route path="/guardian/review/:id" element={<div>review landing</div>} />
      </Routes>
    </MemoryRouter>
  )
}

function fillCredentials(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
}

beforeEach(() => {
  authStatus = 'signed-out'
  authErrorValue = null
  mockSignInWithOAuth.mockReset()
  mockSignInWithPassword.mockReset()
})

describe('LoginPage password form', () => {
  it('submits the entered credentials to signInWithPassword', async () => {
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() =>
      expect(mockSignInWithPassword).toHaveBeenCalledWith({
        email: 'parent@example.com',
        password: 'test-password',
      })
    )
  })

  it('shows a generic error when the credentials are rejected (HTTP 400)', async () => {
    // Supabase returns 400 invalid_credentials for both wrong-password and
    // unknown-email; the message must not leak which, to resist enumeration.
    mockSignInWithPassword.mockRejectedValue(
      new AuthApiError('Invalid login credentials', 400, 'invalid_credentials')
    )
    renderLogin()
    fillCredentials('parent@example.com', 'wrong')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/email and password didn't match/i)
  })

  it('shows a connection error (not a credentials error) for an operational failure', async () => {
    // A network failure / 429 / 5xx must not be mislabeled as bad credentials,
    // or a parent on flaky wifi resets a password that was never wrong.
    mockSignInWithPassword.mockRejectedValue(new TypeError('Failed to fetch'))
    renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/couldn't reach the server/i)
    expect(alert).not.toHaveTextContent(/didn't match/i)
  })

  it('re-enables the Sign in button after a failed attempt', async () => {
    // Guards the `finally`/catch reset: a mistyped password must not leave the
    // button stuck on "Signing in..." with no way to retry.
    mockSignInWithPassword.mockRejectedValue(
      new AuthApiError('Invalid login credentials', 400, 'invalid_credentials')
    )
    renderLogin()
    fillCredentials('parent@example.com', 'wrong')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('alert')
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeInTheDocument()
    expect(button).not.toBeDisabled()
  })

  it('shows the account-unresolved message when a session cannot resolve a principal', () => {
    // signInWithPassword resolved (a session exists) but AuthProvider failed to
    // resolve a Principal (e.g. the Supabase subject has no backend User row),
    // so the user must get feedback instead of a silent dead-end.
    authErrorValue = 'principal-unresolved'
    renderLogin()
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load your account/i)
  })

  it('offers the Google button and hides Apple until it is configured', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /Continue with Google/ })).toBeInTheDocument()
    // Apple sign-in is gated behind VITE_ENABLE_APPLE_OAUTH, unset by default.
    expect(screen.queryByRole('button', { name: /Continue with Apple/ })).not.toBeInTheDocument()
  })

  it('shows the Apple button when VITE_ENABLE_APPLE_OAUTH is true', () => {
    vi.stubEnv('VITE_ENABLE_APPLE_OAUTH', 'true')
    try {
      // Guard: the component reads import.meta.env (see test/setup.ts), so
      // confirm the stub actually landed there and not only on process.env.
      // Without this, a future Vitest change could make the assertion below
      // pass or fail for the wrong reason.
      expect(import.meta.env.VITE_ENABLE_APPLE_OAUTH).toBe('true')
      renderLogin()
      expect(screen.getByRole('button', { name: /Continue with Apple/ })).toBeInTheDocument()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('redirects to the default console when already signed in', () => {
    authStatus = 'signed-in'
    renderLogin()
    expect(screen.getByText('console landing')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
  })

  it('redirects a signed-in user back to the originally requested page', () => {
    // ProtectedRoute forwards the intended path via location.state.from; a
    // guardian who deep-linked to a review must land there, not on /guardian.
    authStatus = 'signed-in'
    renderLogin([
      { pathname: '/guardian/login', state: { from: { pathname: '/guardian/review/123' } } },
    ])
    expect(screen.getByText('review landing')).toBeInTheDocument()
  })
})
