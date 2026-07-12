import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GUARDIAN_LOGIN_PATH } from '../routes'
import { AuthProvider } from './AuthContext'
import { getChildSession, setChildSession } from './childSession'
import { coolParentalGate, parentalGateRemainingMs, warmParentalGate } from './parentalGateState'
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
    },
  },
}))

function Probe() {
  const { status, principal, authError } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{principal?.role ?? 'none'}</span>
      <span data-testid="authError">{authError ?? 'none'}</span>
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
  coolParentalGate()
  mockGet.mockReset()
  mockGetSession.mockReset()
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  mockSignInWithOAuth.mockReset()
  mockSignInWithPassword.mockReset()
  mockSignOut.mockReset()
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
    expect(screen.getByTestId('authError')).toHaveTextContent('none')
    expect(mockGet).toHaveBeenCalledWith('/v1/me')
    expect(localStorage.getItem('auth_token')).toBe('tok-1')
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

  it('sign-out drops warm parental-gate state', async () => {
    // P6-08: an explicit sign-out hands the device over, so a warm parental
    // gate must not survive it and greet the next sign-in already unlocked.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: null })
    warmParentalGate('u1')
    render(
      <AuthProvider>
        <ActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())
    expect(parentalGateRemainingMs('u1')).toBeGreaterThan(0)

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(mockSignOut).toHaveBeenCalled())
    expect(parentalGateRemainingMs('u1')).toBe(0)
  })

  it('keeps warm parental-gate state when sign-out itself fails', async () => {
    // A failed sign-out leaves the session in place, so the gate state should
    // stay consistent with it rather than half-clearing.
    mockGetSession.mockResolvedValue({ data: { session: null } })
    mockSignOut.mockResolvedValue({ error: new Error('revoke failed') })
    warmParentalGate('u1')
    render(
      <AuthProvider>
        <CatchingActionsProbe />
      </AuthProvider>
    )
    await waitFor(() => expect(mockGetSession).toHaveBeenCalled())

    fireEvent.click(screen.getByText('sign out'))

    await waitFor(() => expect(screen.getByTestId('caught')).toHaveTextContent('revoke failed'))
    expect(parentalGateRemainingMs('u1')).toBeGreaterThan(0)
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
