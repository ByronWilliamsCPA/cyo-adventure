import { AuthApiError } from '@supabase/supabase-js'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { InitialEntry } from 'react-router-dom'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue } from '../auth/authContext'
import { getDeviceGrant, setDeviceGrant } from '../auth/deviceGrant'
import type { Principal } from '../auth/types'
import { DEVICE_MINT_WATCHDOG_MS, LoginPage, SIGN_IN_WATCHDOG_MS } from './LoginPage'

const mockSignInWithOAuth = vi.fn()
const mockSignInWithPassword = vi.fn()
const mockSignOut = vi.fn()
const mockRequestPasswordReset = vi.fn()
const mockUpdatePassword = vi.fn()
let authStatus: AuthContextValue['status'] = 'signed-out'
let authErrorValue: AuthContextValue['authError'] = null
let principalValue: Principal | null = null
let recoveryValue = false
let recoveryErrorValue: AuthContextValue['recoveryError'] = null

function principal(role: 'guardian' | 'admin' | 'child', isAdmin = role === 'admin'): Principal {
  return { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] }
}

// The mock covers the full AuthContextValue surface the login page and its
// recovery child (SetNewPasswordForm, which imports the same useAuth) consume.
vi.mock('../auth/useAuth', () => ({
  useAuth: (): Pick<
    AuthContextValue,
    | 'status'
    | 'authError'
    | 'recovery'
    | 'recoveryError'
    | 'signInWithOAuth'
    | 'signInWithPassword'
    | 'signOut'
    | 'principal'
    | 'requestPasswordReset'
    | 'updatePassword'
  > => ({
    status: authStatus,
    authError: authErrorValue,
    recovery: recoveryValue,
    recoveryError: recoveryErrorValue,
    principal: principalValue,
    signInWithOAuth: mockSignInWithOAuth,
    signInWithPassword: mockSignInWithPassword,
    signOut: mockSignOut,
    requestPasswordReset: mockRequestPasswordReset,
    updatePassword: mockUpdatePassword,
  }),
}))

// The device-authorization mint (ADR-014 section 5) goes through useApi's
// axios instance; mocking it here (same pattern as ConsolePage.test.tsx) lets
// each test control the mint's success/failure without a real HTTP call.
const mockPost = vi.fn()
const fakeApi = { post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

/** The login page plus stand-in targets so a redirect is observable. */
function loginUi(initialEntries: InitialEntry[] = ['/guardian/login']) {
  return (
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/guardian/login" element={<LoginPage />} />
        <Route path="/guardian" element={<div>console landing</div>} />
        <Route path="/guardian/review/:id" element={<div>review landing</div>} />
        <Route path="/admin" element={<div>admin landing</div>} />
        <Route path="/admin/moderation-dashboard" element={<div>admin moderation landing</div>} />
        <Route path="/kids" element={<div>kid picker landing</div>} />
        <Route path="/read/:profileId/:storybookId/:version" element={<div>reader landing</div>} />
      </Routes>
    </MemoryRouter>
  )
}

function renderLogin(initialEntries?: InitialEntry[]) {
  return render(loginUi(initialEntries))
}

function fillCredentials(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
}

beforeEach(() => {
  authStatus = 'signed-out'
  authErrorValue = null
  principalValue = null
  recoveryValue = false
  recoveryErrorValue = null
  mockSignInWithOAuth.mockReset()
  mockSignInWithPassword.mockReset()
  mockSignOut.mockReset()
  mockRequestPasswordReset.mockReset()
  mockRequestPasswordReset.mockResolvedValue(undefined)
  mockUpdatePassword.mockReset()
  mockUpdatePassword.mockResolvedValue(undefined)
  // Default: signOut resolves. LoginPage calls signOut().catch(...), so the
  // mock must return a promise; a bare vi.fn() would return undefined and blow
  // up on .catch. Individual tests override with mockRejectedValue.
  mockSignOut.mockResolvedValue(undefined)
  mockPost.mockReset()
  localStorage.clear()
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

  it('submits via native Enter-key form submission, not only the button click', async () => {
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
    await waitFor(() =>
      expect(mockSignInWithPassword).toHaveBeenCalledWith({
        email: 'parent@example.com',
        password: 'test-password',
      })
    )
  })

  it('does not submit a second time while the first attempt is still in flight', async () => {
    // The button disables on `busy`; a double-click (or a slow network plus
    // an impatient parent) must not fire signInWithPassword twice.
    let resolveSignIn: (value?: unknown) => void = () => {}
    mockSignInWithPassword.mockReturnValue(
      new Promise((resolve) => {
        resolveSignIn = resolve
      })
    )
    renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    const button = screen.getByRole('button', { name: 'Sign in' })
    fireEvent.click(button)
    fireEvent.click(await screen.findByRole('button', { name: /signing in/i }))
    expect(mockSignInWithPassword).toHaveBeenCalledTimes(1)
    resolveSignIn()
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
    principalValue = principal('guardian')
    renderLogin([
      { pathname: '/guardian/login', state: { from: { pathname: '/guardian/review/123' } } },
    ])
    expect(screen.getByText('review landing')).toBeInTheDocument()
  })

  describe('role-based post-login redirect', () => {
    it('sends a guardian-only principal to the guardian console', () => {
      authStatus = 'signed-in'
      principalValue = principal('guardian')
      renderLogin()
      expect(screen.getByText('console landing')).toBeInTheDocument()
    })

    it('sends an admin-only principal to the admin console', () => {
      authStatus = 'signed-in'
      principalValue = principal('admin')
      renderLogin()
      expect(screen.getByText('admin landing')).toBeInTheDocument()
    })

    it('sends a dual-role (guardian + admin capability) principal to the guardian console', () => {
      // Their day-to-day home; the admin console link is one hop away via
      // GuardianShell's cross-link.
      authStatus = 'signed-in'
      principalValue = principal('guardian', true)
      renderLogin()
      expect(screen.getByText('console landing')).toBeInTheDocument()
    })

    it('honors a role-valid state.from over the role-based default', () => {
      authStatus = 'signed-in'
      principalValue = principal('admin')
      renderLogin([
        {
          pathname: '/guardian/login',
          state: { from: { pathname: '/admin/moderation-dashboard' } },
        },
      ])
      expect(screen.getByText('admin moderation landing')).toBeInTheDocument()
    })

    it('does not honor a state.from path the principal cannot reach, falling back to the default', () => {
      // A guardian-only principal (no admin capability) cannot reach /admin;
      // ProtectedRoute would bounce them, so the default is used instead of
      // handing <Navigate> an unreachable path.
      authStatus = 'signed-in'
      principalValue = principal('guardian')
      renderLogin([
        {
          pathname: '/guardian/login',
          state: { from: { pathname: '/admin/moderation-dashboard' } },
        },
      ])
      expect(screen.getByText('console landing')).toBeInTheDocument()
      expect(screen.queryByText('admin moderation landing')).not.toBeInTheDocument()
    })

    describe('open-redirect guard (isSameAppPath)', () => {
      it.each([
        ['an absolute URL', 'https://evil.example/phish'],
        ['a scheme-relative "//host" path', '//evil.example/phish'],
        ['a backslash-scheme "/\\\\host" path', '/\\evil.example/phish'],
      ])('falls back to the default when state.from is %s', (_label, badPath) => {
        authStatus = 'signed-in'
        principalValue = principal('guardian')
        renderLogin([
          { pathname: '/guardian/login', state: { from: { pathname: badPath } } },
        ])
        expect(screen.getByText('console landing')).toBeInTheDocument()
      })
    })
  })
})

describe('LoginPage sign-in watchdog', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('re-enables the form and shows a stall note if resolution never arrives', async () => {
    // signInWithPassword resolves (a session exists) but neither status nor
    // authError ever changes: a hung /me lookup that AuthProvider never
    // surfaces. Without the watchdog the button reads "Signing in..." forever.
    vi.useFakeTimers()
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SIGN_IN_WATCHDOG_MS)
    })

    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).not.toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(/taking longer than expected/i)
  })

  it('does not fire the stall note once authError resolves before the watchdog', async () => {
    // authError already un-busies the form on the same render (the `busy`
    // derivation), so a watchdog that later fires anyway must not stack a
    // second, contradictory message on top of the real failure.
    vi.useFakeTimers()
    mockSignInWithPassword.mockResolvedValue(undefined)
    const { rerender } = render(loginUi())
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // Simulate AuthProvider's real state (unlike this plain mock variable)
    // flipping authError, which re-renders LoginPage with the new value; the
    // effect keyed on authError then clears the pending watchdog.
    authErrorValue = 'principal-unresolved'
    rerender(loginUi())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SIGN_IN_WATCHDOG_MS)
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load your account/i)
  })

  it('never fires into an unmounted page', async () => {
    // The happy path unmounts LoginPage via the signed-in redirect while the
    // watchdog is still pending; the cleanup must cancel it so setState never
    // runs against a torn-down component.
    vi.useFakeTimers()
    mockSignInWithPassword.mockResolvedValue(undefined)
    const { unmount } = renderLogin()
    fillCredentials('parent@example.com', 'test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    unmount()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SIGN_IN_WATCHDOG_MS)
    })
    // No assertion beyond "did not throw": React logs a setState-after-unmount
    // warning as a test failure via the shared console-error guard in
    // test/setup.ts, so reaching this line at all is the pass condition.
  })
})

describe('LoginPage OAuth buttons (startSignIn)', () => {
  it('calls signInWithOAuth with "google" when the Google button is clicked', async () => {
    mockSignInWithOAuth.mockResolvedValue(undefined)
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /Continue with Google/ }))
    await waitFor(() => expect(mockSignInWithOAuth).toHaveBeenCalledWith('google'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('calls signInWithOAuth with "apple" when the Apple button is clicked', async () => {
    vi.stubEnv('VITE_ENABLE_APPLE_OAUTH', 'true')
    try {
      mockSignInWithOAuth.mockResolvedValue(undefined)
      renderLogin()
      fireEvent.click(screen.getByRole('button', { name: /Continue with Apple/ }))
      await waitFor(() => expect(mockSignInWithOAuth).toHaveBeenCalledWith('apple'))
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('shows a sign-in error banner when signInWithOAuth rejects', async () => {
    mockSignInWithOAuth.mockRejectedValue(new Error('provider unreachable'))
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /Continue with Google/ }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/sign-in didn't start/i)
  })
})

describe('LoginPage forgot-password request', () => {
  it('reveals the reset-request field when "Forgot your password?" is clicked', () => {
    renderLogin()
    // Hidden until asked for, so it does not clutter the primary sign-in path.
    expect(screen.queryByLabelText('Email for reset link')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    expect(screen.getByLabelText('Email for reset link')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument()
  })

  it('sends a reset link to the entered email', async () => {
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'parent@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() =>
      expect(mockRequestPasswordReset).toHaveBeenCalledWith('parent@example.com')
    )
  })

  it('shows a neutral confirmation that does not reveal whether the account exists', async () => {
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'parent@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/if an account exists/i)
  })

  it('shows a connection error when the reset request fails operationally', async () => {
    // A rate-limit / network failure must be distinguishable from the neutral
    // success so the guardian knows to retry, without leaking account existence.
    mockRequestPasswordReset.mockRejectedValue(new Error('rate limited'))
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'parent@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't send a reset link/i)
  })

  it('blocks submission via native required/type=email validation when the field is empty', () => {
    // The input is `type="email" required`; the browser's own constraint
    // validation must stop the click from ever reaching submitReset(), not
    // just our own application logic.
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(mockRequestPasswordReset).not.toHaveBeenCalled()
  })

  it('blocks submission via native type=email validation when the value is not an email address', () => {
    renderLogin()
    fireEvent.click(screen.getByRole('button', { name: /forgot your password/i }))
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'not-an-email' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(mockRequestPasswordReset).not.toHaveBeenCalled()
  })
})

describe('LoginPage recovery landing (set new password)', () => {
  it('renders the set-new-password form instead of redirecting while in recovery', () => {
    // The recovery link established a session (status signed-in), but the app
    // must let the guardian set a new password rather than bouncing them to the
    // console.
    recoveryValue = true
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin()
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
    expect(screen.queryByText('console landing')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
  })

  it('auto-continues to the console once recovery clears after the password update', () => {
    // updatePassword clears recovery in the context; on the next render the
    // recovery branch is gone and the normal signed-in redirect takes over.
    recoveryValue = false
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin()
    expect(screen.getByText('console landing')).toBeInTheDocument()
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
  })
})

describe('LoginPage failed recovery-link landing', () => {
  it('shows an alert explaining the link is invalid or expired', () => {
    recoveryErrorValue = { code: 'otp_expired', description: 'Email link is invalid or has expired' }
    renderLogin()
    expect(screen.getByRole('alert')).toHaveTextContent(/invalid or has expired/i)
  })

  it('pre-opens the reset-request panel instead of leaving it collapsed', () => {
    // A guardian who just landed on a dead recovery link should not have to
    // rediscover "Forgot your password?" on their own.
    recoveryErrorValue = { code: 'otp_expired', description: 'Email link is invalid or has expired' }
    renderLogin()
    expect(screen.getByLabelText('Email for reset link')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument()
  })
})

describe('LoginPage authorize-device intent (ADR-014 section 5)', () => {
  const mintResponse = {
    data: { id: 'grant-1', token: 'tok-1', expires_at: '2099-01-01T00:00:00Z', family_id: 'fam-1' },
  }

  it('mints a device grant and drops to the kid picker when no grant exists yet', async () => {
    mockPost.mockResolvedValue(mintResponse)
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login?intent=authorize-device'])

    expect(await screen.findByText('kid picker landing')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/v1/device-grants', undefined)
    expect(getDeviceGrant()).toEqual({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    // Not the normal role-based redirect target.
    expect(screen.queryByText('console landing')).not.toBeInTheDocument()
    // #VERIFY (LoginPage.tsx #CRITICAL): the guardian's own session must not
    // linger on what is now a kid device, or the interceptor's guardian-bearer
    // fallthrough could attach it on /library and /read.
    await waitFor(() => expect(mockSignOut).toHaveBeenCalledTimes(1))
  })

  it('still drops to the kid picker when the post-mint sign-out fails', async () => {
    // The grant already succeeded, so a signOut failure must neither present as
    // an authorization failure nor block the hand-off to the picker.
    mockPost.mockResolvedValue(mintResponse)
    mockSignOut.mockRejectedValue(new Error('supabase sign-out unreachable'))
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login?intent=authorize-device'])

    expect(await screen.findByText('kid picker landing')).toBeInTheDocument()
    expect(getDeviceGrant()).toEqual({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })

  it('falls back to the normal redirect when the mint is rejected (e.g. admin-only, no family)', async () => {
    // #VERIFY (LoginPage.tsx #CRITICAL): an admin-only adult with no family
    // gets a mint rejection from the backend; this must not crash and must
    // still land the guardian somewhere useful.
    mockPost.mockRejectedValue(new Error('no family to authorize a device for'))
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login?intent=authorize-device'])

    expect(await screen.findByText('console landing')).toBeInTheDocument()
    expect(getDeviceGrant()).toBeNull()
    expect(screen.queryByText('kid picker landing')).not.toBeInTheDocument()
  })

  it('navigates straight to the kid picker without minting when a valid grant already exists', async () => {
    setDeviceGrant({
      token: 'existing-tok',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'existing-grant',
    })
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login?intent=authorize-device'])

    expect(await screen.findByText('kid picker landing')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
    // Even the already-authorized path sheds the guardian session.
    await waitFor(() => expect(mockSignOut).toHaveBeenCalledTimes(1))
  })

  it('ignores the intent and uses the normal role-based redirect when absent', async () => {
    mockPost.mockResolvedValue(mintResponse)
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login'])

    expect(await screen.findByText('console landing')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('shows a "setting up this device" status while the mint is in flight', async () => {
    let resolveMint: (value: typeof mintResponse) => void = () => {}
    mockPost.mockReturnValue(
      new Promise((resolve) => {
        resolveMint = resolve
      })
    )
    authStatus = 'signed-in'
    principalValue = principal('guardian')
    renderLogin(['/guardian/login?intent=authorize-device'])

    expect(await screen.findByRole('status')).toHaveTextContent(/setting up this device/i)
    expect(screen.queryByText('console landing')).not.toBeInTheDocument()
    expect(screen.queryByText('kid picker landing')).not.toBeInTheDocument()

    resolveMint(mintResponse)
    expect(await screen.findByText('kid picker landing')).toBeInTheDocument()
  })

  describe('device-mint watchdog', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('falls back to the normal redirect if the mint never settles', async () => {
      // mint() never resolves or rejects (a hung request, or a dropped
      // connection the client never surfaces as a rejection). Without the
      // watchdog the guardian would be stuck on "Setting up this device..."
      // forever.
      vi.useFakeTimers()
      mockPost.mockReturnValue(new Promise(() => {}))
      authStatus = 'signed-in'
      principalValue = principal('guardian')
      renderLogin(['/guardian/login?intent=authorize-device'])

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByRole('status')).toHaveTextContent(/setting up this device/i)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(DEVICE_MINT_WATCHDOG_MS)
      })

      expect(screen.getByText('console landing')).toBeInTheDocument()
      expect(mockSignOut).not.toHaveBeenCalled()
    })

    it('does not override a mint that resolves before the watchdog fires', async () => {
      // A late-firing watchdog must not stomp a deviceAuthState the successful
      // mint already moved past 'authorizing'.
      vi.useFakeTimers()
      mockPost.mockResolvedValue(mintResponse)
      authStatus = 'signed-in'
      principalValue = principal('guardian')
      renderLogin(['/guardian/login?intent=authorize-device'])

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByText('kid picker landing')).toBeInTheDocument()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(DEVICE_MINT_WATCHDOG_MS)
      })

      expect(screen.getByText('kid picker landing')).toBeInTheDocument()
    })

    it('never fires into an unmounted page', async () => {
      // The happy and failure paths both unmount LoginPage (navigate, or the
      // fallback <Navigate>) while the watchdog may still be pending; the
      // effect cleanup must cancel it so setState never runs against a
      // torn-down component.
      vi.useFakeTimers()
      mockPost.mockReturnValue(new Promise(() => {}))
      authStatus = 'signed-in'
      principalValue = principal('guardian')
      const { unmount } = renderLogin(['/guardian/login?intent=authorize-device'])
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      unmount()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(DEVICE_MINT_WATCHDOG_MS)
      })
      // No assertion beyond "did not throw": React logs a setState-after-unmount
      // warning as a test failure via the shared console-error guard in
      // test/setup.ts, so reaching this line at all is the pass condition.
    })
  })
})
