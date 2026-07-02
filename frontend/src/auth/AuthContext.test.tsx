import { act, render, screen, waitFor } from '@testing-library/react'
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

  it('useAuth throws when used outside an AuthProvider', () => {
    function Bare() {
      useAuth()
      return null
    }
    expect(() => render(<Bare />)).toThrow('useAuth must be used within an AuthProvider')
  })
})
