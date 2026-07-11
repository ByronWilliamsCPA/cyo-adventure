import { AuthApiError } from '@supabase/supabase-js'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ParentalGate } from './ParentalGate'
import {
  coolParentalGate,
  PARENTAL_GATE_TTL_MS,
  parentalGateRemainingMs,
  warmParentalGate,
} from './parentalGateState'

const mockSignInWithPassword = vi.fn()
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({
    signInWithPassword: (...args: unknown[]): unknown => mockSignInWithPassword(...args),
  }),
}))

const mockGetSession = vi.fn()
vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]): unknown => mockGetSession(...args),
    },
  },
}))

/** A session whose user signed up with email+password. */
function passwordSession(userId = 'u1', email = 'guardian@example.com') {
  return {
    data: {
      session: {
        access_token: 'tok-1',
        user: { id: userId, email, app_metadata: { provider: 'email', providers: ['email'] } },
      },
    },
  }
}

/** A session whose user only ever signed in with an OAuth provider. */
function oauthSession(userId = 'u1') {
  return {
    data: {
      session: {
        access_token: 'tok-1',
        user: {
          id: userId,
          email: 'guardian@example.com',
          app_metadata: { provider: 'google', providers: ['google'] },
        },
      },
    },
  }
}

function renderGate() {
  return render(
    <MemoryRouter initialEntries={['/previous', '/gated']} initialIndex={1}>
      <Routes>
        <Route path="/previous" element={<div>Previous page</div>} />
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route element={<ParentalGate />}>
          <Route path="/gated" element={<div>Sensitive content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

async function typePasswordAndConfirm(password: string) {
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  // Let the signInWithPassword promise settle either way.
  await act(async () => {})
}

beforeEach(() => {
  coolParentalGate()
  mockSignInWithPassword.mockReset()
  mockGetSession.mockReset().mockResolvedValue(passwordSession())
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('ParentalGate', () => {
  it('renders the re-auth challenge instead of the children when cold', async () => {
    renderGate()
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('unlocks and renders the children after a correct password', async () => {
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    await typePasswordAndConfirm('correct-horse')

    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(mockSignInWithPassword).toHaveBeenCalledWith({
      email: 'guardian@example.com',
      password: 'correct-horse',
    })
    // The unlock warmed the module-level state for this user.
    expect(parentalGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('shows an inline wrong-password error and stays locked', async () => {
    mockSignInWithPassword.mockRejectedValue(
      new AuthApiError('Invalid login credentials', 400, 'invalid_credentials')
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    await typePasswordAndConfirm('wrong')

    expect(await screen.findByRole('alert')).toHaveTextContent(/didn't match/)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
    expect(parentalGateRemainingMs('u1')).toBe(0)
  })

  it('reports an operational failure as a connection problem, not a wrong password', async () => {
    mockSignInWithPassword.mockRejectedValue(new Error('network down'))
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    await typePasswordAndConfirm('whatever')

    expect(await screen.findByRole('alert')).toHaveTextContent(/reach the server/)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('renders the children immediately when the gate is already warm for this user', async () => {
    warmParentalGate('u1')
    renderGate()
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('stays locked when the warm entry belongs to a different user', async () => {
    warmParentalGate('someone-else')
    renderGate()
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-challenges when the TTL expires while the content is open', async () => {
    vi.useFakeTimers()
    warmParentalGate('u1')
    renderGate()
    // Flush the getSession() microtask under fake timers.
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(PARENTAL_GATE_TTL_MS + 1)
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('lets an OAuth-only guardian through with a console warning', async () => {
    // #ASSUME: security: documented limitation, see ParentalGate.tsx: an OAuth
    // guardian has no password to re-enter and supabase-js has no client-side
    // OAuth re-auth challenge, so the gate passes them through loudly rather
    // than locking them out of approval.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(oauthSession())
    renderGate()

    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('ParentalGate'))
    // Nothing was warmed: the bypass is per-mount, not a fake unlock.
    expect(parentalGateRemainingMs('u1')).toBe(0)
  })

  it('navigates back when the challenge is cancelled', async () => {
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: 'Go back' }))

    expect(await screen.findByText('Previous page')).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('fails closed to the login page when there is no session', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    renderGate()
    expect(await screen.findByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('never persists warm state outside memory (a reload starts cold)', async () => {
    // The state module keeps warmth in a module-level variable only; nothing
    // is written to localStorage/sessionStorage, so a page reload (fresh
    // module registry) always re-challenges. Assert the storage side of that
    // contract here; the fresh-module side is inherent to the design.
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })
    await typePasswordAndConfirm('correct-horse')
    await screen.findByText('Sensitive content')

    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('waits for the unlock to settle before rendering anything sensitive', async () => {
    // While signInWithPassword is in flight the gate stays on the challenge
    // with the button disabled, so double-submits cannot stack re-auth calls.
    let resolveSignIn: (() => void) | undefined
    mockSignInWithPassword.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSignIn = () => resolve()
        })
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await screen.findByRole('button', { name: 'Checking...' })).toBeDisabled()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()

    resolveSignIn?.()
    await waitFor(() => expect(screen.getByText('Sensitive content')).toBeInTheDocument())
  })
})
