import { AuthApiError } from '@supabase/supabase-js'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
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

/** A session with arbitrary user fields, for the defensive-branch tests. */
function sessionWithUser(user: Record<string, unknown>) {
  return { data: { session: { access_token: 'tok-1', user } } }
}

/** Login page probe that surfaces the `state.from` handed to the redirect. */
function LoginProbe() {
  const location = useLocation()
  const state = location.state as { from?: { pathname?: string } } | null
  return <div>Login page (from {state?.from?.pathname ?? 'nowhere'})</div>
}

function gateRoutes() {
  return (
    <Routes>
      <Route path="/previous" element={<div>Previous page</div>} />
      <Route path="/guardian" element={<div>Console home</div>} />
      <Route path="/guardian/login" element={<LoginProbe />} />
      <Route element={<ParentalGate />}>
        <Route path="/gated" element={<div>Sensitive content</div>} />
      </Route>
    </Routes>
  )
}

function renderGate() {
  return render(
    <MemoryRouter initialEntries={['/previous', '/gated']} initialIndex={1}>
      {gateRoutes()}
    </MemoryRouter>
  )
}

/** Entered on /gated directly (deep link / bookmark): no in-app history. */
function renderGateAsDeepLink() {
  return render(<MemoryRouter initialEntries={['/gated']}>{gateRoutes()}</MemoryRouter>)
}

async function typePasswordAndConfirm(password: string) {
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  // Let the signInWithPassword promise settle either way.
  await act(async () => {})
}

/** Flush the getSession() microtask (needed under fake timers). */
async function flushSession() {
  await act(async () => {
    await Promise.resolve()
  })
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
    // The challenge intro is a polite live region, so the loading-to-challenge
    // transition is announced to screen readers instead of happening silently.
    expect(screen.getByRole('status')).toHaveTextContent('Grown-ups only')
  })

  it('shows a polite loading status during the transient checking phase', async () => {
    let resolveSession: ((value: unknown) => void) | undefined
    mockGetSession.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSession = resolve
        })
    )
    renderGate()
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()

    await act(async () => {
      resolveSession?.(passwordSession())
      await Promise.resolve()
    })
    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
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

  it('reports a rate limit distinctly, without inviting an instant retry', async () => {
    mockSignInWithPassword.mockRejectedValue(
      new AuthApiError('Request rate limit reached', 429, 'over_request_rate_limit')
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    await typePasswordAndConfirm('whatever')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/too many attempts/i)
    expect(alert).not.toHaveTextContent(/check your connection/i)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('reports a server-side failure distinctly from a connection problem', async () => {
    mockSignInWithPassword.mockRejectedValue(
      new AuthApiError('Internal server error', 500, 'unexpected_failure')
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    await typePasswordAndConfirm('whatever')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/sign-in service had a problem/i)
    expect(alert).not.toHaveTextContent(/check your connection/i)
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
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    // Exactly the TTL boundary: at now === expiresAt the warmth is gone.
    act(() => {
      vi.advanceTimersByTime(PARENTAL_GATE_TTL_MS)
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-locks on visibilitychange when a throttled tab slept past the TTL', async () => {
    // A backgrounded tab can throttle the scheduled setTimeout indefinitely;
    // simulate that by moving the wall clock past the TTL WITHOUT running
    // timers, then surfacing the tab.
    vi.useFakeTimers()
    warmParentalGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    vi.setSystemTime(Date.now() + PARENTAL_GATE_TTL_MS + 1)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-locks on pageshow when a bfcache restore revives expired warm state', async () => {
    // Module-level warm state survives a bfcache restore; the pageshow
    // listener re-checks the wall clock so the sensitive page cannot come
    // back from the cache already unlocked past its TTL.
    vi.useFakeTimers()
    warmParentalGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    vi.setSystemTime(Date.now() + PARENTAL_GATE_TTL_MS + 1)
    act(() => {
      window.dispatchEvent(new Event('pageshow'))
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('stays unlocked on visibilitychange while the TTL still has time left', async () => {
    vi.useFakeTimers()
    warmParentalGate('u1')
    renderGate()
    await flushSession()

    vi.setSystemTime(Date.now() + PARENTAL_GATE_TTL_MS - 1000)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
  })

  it('supports a full re-lock then re-unlock cycle', async () => {
    vi.useFakeTimers()
    mockSignInWithPassword.mockResolvedValue(undefined)
    warmParentalGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(PARENTAL_GATE_TTL_MS + 1)
    })
    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()

    await typePasswordAndConfirm('correct-horse')

    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
    expect(parentalGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('clears the re-lock timer on unmount', async () => {
    vi.useFakeTimers()
    warmParentalGate('u1')
    const { unmount } = renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
    expect(vi.getTimerCount()).toBeGreaterThan(0)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
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

  it('challenges a mixed-provider guardian who does have a password identity', async () => {
    mockGetSession.mockResolvedValue(
      sessionWithUser({
        id: 'u1',
        email: 'guardian@example.com',
        app_metadata: { provider: 'google', providers: ['google', 'email'] },
      })
    )
    renderGate()
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('falls back to the primary provider when app_metadata.providers is not an array', async () => {
    mockGetSession.mockResolvedValue(
      sessionWithUser({
        id: 'u1',
        email: 'guardian@example.com',
        app_metadata: { provider: 'email', providers: 'email' },
      })
    )
    renderGate()
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
  })

  it('ignores non-string entries in app_metadata.providers', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(
      sessionWithUser({
        id: 'u1',
        email: 'guardian@example.com',
        app_metadata: { provider: 'google', providers: [42, 'google', null] },
      })
    )
    renderGate()
    // No 'email' identity survives validation, so this is an OAuth bypass.
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('ParentalGate'))
  })

  it('treats a user without app_metadata as having no password identity', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(
      sessionWithUser({ id: 'u1', email: 'guardian@example.com' })
    )
    renderGate()
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('ParentalGate'))
  })

  it('never locks with a null email: an email provider without an email bypasses', async () => {
    // hasPassword requires BOTH the 'email' provider AND a usable email, so
    // submit()'s email-null guard is defensive dead space by construction:
    // the locked phase can only ever hold a non-null email.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(
      sessionWithUser({ id: 'u1', app_metadata: { provider: 'email', providers: ['email'] } })
    )
    renderGate()
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('ParentalGate'))
  })

  it('ignores a re-entrant submit while one is already in flight', async () => {
    // The disabled button blocks clicks, but Enter in the still-focused input
    // submits the form directly; the submit() guard must drop that.
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
    const form = document.querySelector('form')
    if (!form) throw new Error('challenge form not rendered')

    fireEvent.submit(form)
    fireEvent.submit(form)
    fireEvent.submit(form)

    expect(mockSignInWithPassword).toHaveBeenCalledTimes(1)
    resolveSignIn?.()
    await waitFor(() => expect(screen.getByText('Sensitive content')).toBeInTheDocument())
  })

  it('navigates back when the challenge is cancelled', async () => {
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: 'Go back' }))

    expect(await screen.findByText('Previous page')).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('falls back to the console root when cancelled with no in-app history', async () => {
    // Deep link / bookmark: /gated is the first (and only) history entry, so
    // navigate(-1) has nothing to pop. Cancel must still lead somewhere.
    renderGateAsDeepLink()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: 'Go back' }))

    expect(await screen.findByText('Console home')).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('fails closed to the login page, carrying the attempted location', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } })
    renderGate()
    const login = await screen.findByText(/Login page/)
    // Like ProtectedRoute, the redirect passes state.from so a re-login can
    // return the guardian to the page they were trying to reach.
    expect(login).toHaveTextContent('from /gated')
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('recovers from a failed session lookup via the retry button', async () => {
    // A getSession() rejection must not strand the gate on the loading state
    // forever; it fails closed to an explicit error phase with a retry.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGetSession.mockRejectedValueOnce(new Error('storage exploded'))
    renderGate()

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't check/i)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('ParentalGate'),
      expect.any(Error)
    )

    // The next lookup succeeds (beforeEach default), so retry reaches the
    // normal challenge.
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('never persists warm state outside memory (a reload starts cold)', async () => {
    // The state module keeps warmth in a module-level variable only; nothing
    // is written to localStorage/sessionStorage, so a page reload (fresh
    // module registry) always re-challenges. Assert the storage side of that
    // contract here (against a snapshot, so unrelated keys other machinery
    // may have set do not matter); the fresh-module side is inherent to the
    // design.
    const localKeysBefore = Object.keys(localStorage).sort()
    const sessionKeysBefore = Object.keys(sessionStorage).sort()
    mockSignInWithPassword.mockResolvedValue(undefined)
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })
    await typePasswordAndConfirm('correct-horse')
    await screen.findByText('Sensitive content')

    expect(Object.keys(localStorage).sort()).toEqual(localKeysBefore)
    expect(Object.keys(sessionStorage).sort()).toEqual(sessionKeysBefore)
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

describe('parentalGateState', () => {
  it('honors the injectable now parameter on warm and read', () => {
    warmParentalGate('u1', 1_000)
    expect(parentalGateRemainingMs('u1', 1_000)).toBe(PARENTAL_GATE_TTL_MS)
    expect(parentalGateRemainingMs('u1', 1_000 + PARENTAL_GATE_TTL_MS / 2)).toBe(
      PARENTAL_GATE_TTL_MS / 2
    )
  })

  it('treats the exact TTL boundary (now === expiresAt) as expired', () => {
    warmParentalGate('u1', 1_000)
    expect(parentalGateRemainingMs('u1', 1_000 + PARENTAL_GATE_TTL_MS - 1)).toBe(1)
    expect(parentalGateRemainingMs('u1', 1_000 + PARENTAL_GATE_TTL_MS)).toBe(0)
    expect(parentalGateRemainingMs('u1', 1_000 + PARENTAL_GATE_TTL_MS + 1)).toBe(0)
  })

  it('is cold for every user after coolParentalGate()', () => {
    warmParentalGate('u1', 1_000)
    coolParentalGate()
    expect(parentalGateRemainingMs('u1', 1_000)).toBe(0)
  })
})
