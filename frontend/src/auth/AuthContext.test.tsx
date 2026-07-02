import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from './AuthContext'
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
const mockSignOut = vi.fn()
vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]) => mockOnAuthStateChange(...args),
      signInWithOAuth: (...args: unknown[]) => mockSignInWithOAuth(...args),
      signOut: (...args: unknown[]) => mockSignOut(...args),
    },
  },
}))

function Probe() {
  const { status, principal } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{principal?.role ?? 'none'}</span>
    </div>
  )
}

function ActionsProbe() {
  const { signInWithOAuth, signOut } = useAuth()
  return (
    <div>
      <button type="button" onClick={() => void signInWithOAuth('google')}>
        sign in
      </button>
      <button type="button" onClick={() => void signOut()}>
        sign out
      </button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  mockGet.mockReset()
  mockGetSession.mockReset()
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  mockSignInWithOAuth.mockReset()
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
    expect(localStorage.getItem('auth_token')).toBeNull()
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
    expect(mockGet).toHaveBeenCalledWith('/v1/me')
    expect(localStorage.getItem('auth_token')).toBe('tok-1')
  })

  it('fails closed to signed-out when /me rejects a session', async () => {
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
    expect(localStorage.getItem('auth_token')).toBeNull()
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
    await waitFor(() => expect(mockSignInWithOAuth).toHaveBeenCalledWith({ provider: 'google' }))
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

  it('useAuth throws when used outside an AuthProvider', () => {
    function Bare() {
      useAuth()
      return null
    }
    expect(() => render(<Bare />)).toThrow('useAuth must be used within an AuthProvider')
  })
})
