import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GUARDIAN_LOGIN_PATH } from '../routes'
import { AuthProvider } from './AuthContext'
import { getChildSession, setChildSession } from './childSession'
import { adultGateRemainingMs, clearAdultGate, warmAdultGate } from './parentalGateState'
import { useAuth } from './useAuth'

const mockGet = vi.fn()
// A stable object, not a fresh literal per call: useApi() is memoized in
// production (useMemo(..., [config])), and AuthContext's effect depends on
// [api]. A fresh object per render here would re-fire the effect on every
// state update, re-running getSession()/onAuthStateChange spuriously.
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const mockGetSession = vi.fn()
const mockOnAuthStateChange = vi.fn()
const mockSignInWithOAuth = vi.fn()
const mockSignInWithPassword = vi.fn()
const mockSignOut = vi.fn()
const mockResetPasswordForEmail = vi.fn()
const mockUpdateUser = vi.fn()
// Drives the recovery seed (AuthProvider's useState(isPasswordRecovery)).
// A `mock`-prefixed let so vitest allows referencing it inside the hoisted
// factory; a getter re-reads it at each mount so tests can flip it before
// render to simulate a password-recovery landing.
let mockIsPasswordRecovery = false
// Each mock method's return type is annotated `unknown`, not inferred, so the
// untyped vi.fn() mocks don't leak a bare `any` past this seam: the real
// AuthContext.tsx compiles against supabaseClient.ts's actual Supabase types
// regardless of this test-only substitution.
vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]): unknown => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]): unknown => mockOnAuthStateChange(...args),
      signInWithOAuth: (...args: unknown[]): unknown => mockSignInWithOAuth(...args),
      signInWithPassword: (...args: unknown[]): unknown => mockSignInWithPassword(...args),
      signOut: (...args: unknown[]): unknown => mockSignOut(...args),
      resetPasswordForEmail: (...args: unknown[]): unknown => mockResetPasswordForEmail(...args),
      updateUser: (...args: unknown[]): unknown => mockUpdateUser(...args),
    },
  },
  get isPasswordRecovery(): boolean {
    return mockIsPasswordRecovery
  },
}))

function Probe() {
  const { status, principal, authError, recovery } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{principal?.role ?? 'none'}</span>
      <span data-testid="isAdmin">{principal ? String(principal.isAdmin) : 'none'}</span>
      <span data-testid="authError">{authError ?? 'none'}</span>
      <span data-testid="recovery">{String(recovery)}</span>
    </div>
  )
}

/** Exercises the recovery actions and surfaces the rejections they rethrow. */
function RecoveryProbe() {
  const { recovery, requestPasswordReset, updatePassword } = useAuth()
  const [caught, setCaught] = useState('none')
  return (
    <div>
      <span data-testid="recovery">{String(recovery)}</span>
      <span data-testid="caught">{caught}</span>
      <button
        type="button"
        onClick={() =>
          void requestPasswordReset('reset@example.com').catch((e: Error) => setCaught(e.message))
        }
      >
        request reset
      </button>
      <button
        type="button"
        onClick={() =>
          void updatePassword('new-password-123').catch((e: Error) => setCaught(e.message))
        }
      >
        update password
      </button>
    </div>
  )
}

function ActionsProbe() {
  const { signInWithOAuth, signInWithPassword, signOut } = useAuth()
  return (
    <div>
      <button type="button" onClick={() => void signInWithOAuth('google')}>
        sign in
      </button>
      <button type="button" onClick={() => void signInWithPassword({ email: 'a@b.com', password: 'pw' })}>
        sign in password
      </button>
      <button type="button" onClick={() => void signOut()}>
        sign out
      </button>
    </div>
  )
}

/** Mirrors how real call sites consume the rejections these actions now throw. */
function CatchingActionsProbe() {
  const { signInWithOAuth, signInWithPassword, signOut } = useAuth()
  const [caught, setCaught] = useState('none')
  return (
    <div>
      <span data-testid="caught">{caught}</span>
      <button
        type="button"
        onClick={() => void signInWithOAuth('google').catch((e: Error) => setCaught(e.message))}
      >
        sign in
      </button>
      <button
        type="button"
        onClick={() =>
          void signInWithPassword({ email: 'a@b.com', password: 'pw' }).catch((e: Error) => setCaught(e.message))
        }
      >
        sign in password
      </button>
      <button
        type="button"
        onClick={() => void signOut().catch((e: Error) => setCaught(e.message))}
      >
        sign out
      </button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  clearAdultGate()
  mockGet.mockReset()
  mockGetSession.mockReset()
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  mockSignInWithOAuth.mockReset()
  mockSignInWithPassword.mockReset()
  mockSignOut.mockReset()
  mockResetPasswordForEmail.mockReset()
  mockUpdateUser.mockReset()
  mockIsPasswordRecovery = false
})

describe('AuthProvider', () => {
  it('resolves to signed-out with no session, without calling /me', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(mockGet).not.toHaveBeenCalled()
    expect(screen.getByTestId('authError')).toHaveTextContent('none')
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('clears an active child session (G1 / P6-04) when there is no guardian session at all', async () => {
    // Covers the "no guardian ever signed in on this device load" path, not
    // just an explicit sign-out click: safeRemoveToken() runs here too.
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(getChildSession()).toBeNull()
  })

  it('resolves the principal via /me when a session exists', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    // is_admin is absent from this legacy-shaped response: the capability
    // must fail closed to false, never default open.
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('false')
    expect(screen.getByTestId('authError')).toHaveTextContent('none')
    expect(mockGet).toHaveBeenCalledWith('/v1/me')
    expect(localStorage.getItem('auth_token')).toBe('tok-1')
  })

  it('carries the is_admin capability onto the principal for a dual-role adult', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        is_admin: true,
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('true')
  })

  it('fails closed on a malformed truthy is_admin value', async () => {
    // The strict `=== true` guard must reject any non-boolean truthy value
    // (e.g. a stray "true" string or a 1/0 flag from a misbehaving backend),
    // never coerce it to the capability. Fail closed, not open.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: {
        subject: 'sub-1',
        role: 'guardian',
        is_admin: 'true',
        family_id: 'fam-1',
        profile_ids: ['p1'],
      },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(screen.getByTestId('role')).toHaveTextContent('guardian')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('false')
  })

  it('fails closed and sets authError when /me rejects a session', async () => {
    // A session that establishes but cannot resolve a Principal must fail closed
    // AND record authError, so LoginPage can tell the user their account could
    // not be loaded instead of stranding them on an idle form.
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockRejectedValue(new Error('401 from backend'))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(screen.getByTestId('authError')).toHaveTextContent('principal-unresolved')
    expect(localStorage.getItem('auth_token')).toBeNull()
    // A guardian session that never resolves to a principal also ends
    // whatever child session shared this device's storage (G1 / P6-04).
    expect(getChildSession()).toBeNull()
  })

  it('re-syncs from an onAuthStateChange event (e.g. sign-out elsewhere)', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))

    act(() => {
      changeHandler?.('SIGNED_OUT', null)
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('sign-out clears an active child session (G1 / P6-04) alongside the guardian token', async () => {
    setChildSession({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(getChildSession()).not.toBeNull()

    act(() => {
      changeHandler?.('SIGNED_OUT', null)
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(getChildSession()).toBeNull()
  })

  it('fails closed to signed-out when /me returns an unrecognized role', async () => {
    // The role drives ProtectedRoute's allow/deny. A value outside the closed
    // Role set must be rejected (fail closed), not cast into a Principal.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'superuser', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('keeps the latest /me result when responses arrive out of order', async () => {
    // seq 1 (from getSession) resolves AFTER seq 2 (from an auth-change event).
    // The monotonic guard must discard seq 1's stale result so seq 2 survives.
    let resolveFirst: ((value: unknown) => void) | undefined
    const firstResponse = new Promise((resolve) => {
      resolveFirst = resolve
    })
    mockGet.mockReturnValueOnce(firstResponse).mockResolvedValueOnce({
      data: { subject: 'sub-new', role: 'admin', family_id: 'fam', profile_ids: [] },
    })
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    // Let the getSession-driven sync (seq 1) start and park on firstResponse.
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))

    // Fire the newer sync (seq 2); its /me resolves immediately.
    act(() => {
      changeHandler?.('TOKEN_REFRESHED', { access_token: 'tok-2', user: { id: 'u1' } })
    })
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('admin'))

    // Now let seq 1's late response land: it must be ignored, not overwrite seq 2.
    await act(async () => {
      resolveFirst?.({
        data: { subject: 'sub-old', role: 'guardian', family_id: 'fam', profile_ids: [] },
      })
      await firstResponse
    })
    expect(screen.getByTestId('role')).toHaveTextContent('admin')
    expect(screen.getByTestId('status')).toHaveTextContent('signed-in')
  })

  it('delegates signInWithOAuth to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithOAuth.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in'))
    await waitFor(() =>
      expect(mockSignInWithOAuth).toHaveBeenCalledWith({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}` },
      })
    )
  })

  it('delegates signInWithPassword to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() =>
      expect(mockSignInWithPassword).toHaveBeenCalledWith({ email: 'a@b.com', password: 'pw' })
    )
  })

  it('rejects signInWithPassword when supabase reports an error', async () => {
    // Bad credentials resolve with { error } rather than throwing; the context
    // must rethrow so LoginPage can show a failure message instead of no-op'ing.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: new Error('invalid login') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('invalid login'))
  })

  it('clears a stale authError when a new password sign-in starts', async () => {
    // Regression: a session that could not resolve a Principal leaves authError
    // set. A retry must clear it up front, or LoginPage's
    // `busy = submitting && !authError` goes false on the new attempt's first
    // render, re-enabling the button and keeping the old alert visible.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockRejectedValue(new Error('401 from backend'))
    mockSignInWithPassword.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <Probe />
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() =>
      expect(screen.getByTestId('authError')).toHaveTextContent('principal-unresolved')
    )
    fireEvent.click(screen.getByText('sign in password'))
    await waitFor(() => expect(screen.getByTestId('authError')).toHaveTextContent('none'))
  })

  it('delegates signOut to supabase', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
  })

  it('sign-out drops warm adult-gate state', async () => {
    // ADR-014 Phase 5: an explicit sign-out hands the device over, so a warm
    // adult gate must not survive it and greet the next sign-in already
    // unlocked.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    warmAdultGate('u1')
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('clears the local credential and adult gate even when the network revoke fails', async () => {
    // #CRITICAL: security (C1): on a shared kid device the guardian bearer must
    // not survive a sign-out just because the network revoke failed. Supabase's
    // GoTrueClient._signOut removes the local session only AFTER a successful or
    // 4xx revoke, so a transport failure/5xx would otherwise strand auth_token
    // in localStorage for the useApi fallthrough to attach on a kid route.
    // AuthContext therefore clears the token (and the now-meaningless warm adult
    // gate) up front, before the revoke and independently of its outcome; the
    // revoke error still propagates to the caller.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: new Error('revoke failed') })
    warmAdultGate('u1')
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    // A bearer still in storage at sign-out time (set after mount settles so
    // the initial signed-out resolution does not clear it first).
    localStorage.setItem('auth_token', 'guardian-bearer')

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('revoke failed'))
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('warms the adult gate on a genuine SIGNED_IN event', async () => {
    // ADR-014 Phase 5: the guardian just proved full credentials (password
    // submit or an OAuth redirect return), so entering the console
    // immediately after must NOT show the step-up.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(adultGateRemainingMs('u1')).toBe(0)

    act(() => {
      changeHandler?.('SIGNED_IN', { access_token: 'tok-1', user: { id: 'u1' } })
    })

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('does NOT warm the adult gate on a restored session or a silent token refresh', async () => {
    // #CRITICAL: security: only an explicit SIGNED_IN event may warm the
    // gate. Warming on the initial getSession()-driven restore (no event) or
    // on a periodic TOKEN_REFRESHED would let a merely-persisted or
    // auto-refreshing session look identical to a guardian who just typed a
    // password, defeating the step-up.
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'))
    // The session was restored via getSession(), not an explicit sign-in.
    expect(adultGateRemainingMs('u1')).toBe(0)

    act(() => {
      changeHandler?.('TOKEN_REFRESHED', { access_token: 'tok-2', user: { id: 'u1' } })
    })
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(adultGateRemainingMs('u1')).toBe(0)
  })

  it('rejects signInWithOAuth when supabase reports an error', async () => {
    // supabase-js resolves with { error } instead of throwing; the context
    // must rethrow so a failed OAuth redirect is not silently swallowed.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignInWithOAuth.mockResolvedValue({ data: {}, error: new Error('oauth unavailable') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign in'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('oauth unavailable'))
  })

  it('rejects signOut when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: new Error('revoke failed') })
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('revoke failed'))
  })

  it('useAuth throws when used outside an AuthProvider', () => {
    function Bare() {
      useAuth()
      return null
    }
    expect(() => render(<Bare />)).toThrow('useAuth must be used within an AuthProvider')
  })
})

describe('AuthProvider password recovery', () => {
  it('seeds recovery=false on an ordinary load', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'))
    expect(screen.getByTestId('recovery')).toHaveTextContent('false')
  })

  it('seeds recovery=true when the page load is a recovery-link landing', async () => {
    // supabaseClient froze isPasswordRecovery=true from the #type=recovery hash
    // before createClient stripped it; the provider must start in recovery mode
    // so LoginPage shows the set-new-password form instead of redirecting.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
  })

  it('enters recovery on a PASSWORD_RECOVERY auth event', async () => {
    // supabase-js fires PASSWORD_RECOVERY when it processes the recovery hash
    // after mount (the event can arrive slightly after the initial seed race),
    // so the provider must also flip into recovery on the event itself.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    let changeHandler: ((event: string, session: unknown) => void) | undefined
    mockOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      changeHandler = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))

    act(() => {
      changeHandler?.('PASSWORD_RECOVERY', { access_token: 'tok-r', user: { id: 'u1' } })
    })

    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
  })

  it('requestPasswordReset delegates to supabase with a login-page redirect', async () => {
    // The reset email links back to the guardian login page, the only surface
    // that loads supabase-js and can process the recovery hash (same constraint
    // as the OAuth redirectTo).
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockResetPasswordForEmail.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('request reset'))
    await waitFor(() =>
      expect(mockResetPasswordForEmail).toHaveBeenCalledWith('reset@example.com', {
        redirectTo: `${window.location.origin}${GUARDIAN_LOGIN_PATH}`,
      })
    )
  })

  it('rejects requestPasswordReset when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockResetPasswordForEmail.mockResolvedValue({ data: {}, error: new Error('rate limited') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('request reset'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('rate limited'))
  })

  it('updatePassword delegates to supabase.auth.updateUser', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockUpdateUser.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() =>
      expect(mockUpdateUser).toHaveBeenCalledWith({ password: 'new-password-123' })
    )
  })

  it('rejects updatePassword when supabase reports an error', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockUpdateUser.mockResolvedValue({ data: {}, error: new Error('weak password') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('weak password'))
  })

  it('clears recovery after a successful password update (auto-continue)', async () => {
    // Once the new password is saved, the recovery session is a normal signed-in
    // session; clearing recovery lets LoginPage fall through to its role-based
    // redirect (the approved "auto-continue to console" behavior).
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockUpdateUser.mockResolvedValue({ data: {}, error: null })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))
  })

  it('leaves recovery set when the password update fails', async () => {
    // A failed update must keep the user on the set-new-password form to retry,
    // not drop them into the console with the old password still active.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockUpdateUser.mockResolvedValue({ data: {}, error: new Error('weak password') })
    render(
      <AuthProvider>
        <RecoveryProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('update password'))
    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('weak password'))
    expect(screen.getByTestId('recovery')).toHaveTextContent('true')
  })

  it('clears recovery on sign-out', async () => {
    // Abandoning recovery (signing out from the set-new-password form) must not
    // leave the provider stuck in recovery for the next session on this device.
    mockIsPasswordRecovery = true
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    mockSignOut.mockResolvedValue({ error: null })
    render(
      <AuthProvider>
        <Probe />
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('sign out'))
    await waitFor(() => expect(screen.getByTestId('recovery')).toHaveTextContent('false'))
  })
})
