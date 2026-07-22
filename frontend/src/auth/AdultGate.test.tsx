import { AuthApiError } from '@supabase/supabase-js'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdultGate } from './AdultGate'
import {
  ADULT_GATE_TTL_MS,
  adultGateRemainingMs,
  clearAdultGate,
  isAdultGateWarm,
  parkAdultGate,
  warmAdultGate,
} from './parentalGateState'

const mockSignInWithPassword = vi.fn()
const mockSignInWithOAuth = vi.fn()
const mockSignOut = vi.fn()
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({
    signInWithPassword: (...args: unknown[]): unknown => mockSignInWithPassword(...args),
    signInWithOAuth: (...args: unknown[]): unknown => mockSignInWithOAuth(...args),
    signOut: (...args: unknown[]): unknown => mockSignOut(...args),
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

/**
 * A session whose user has BOTH an email/password identity and a linked
 * Google identity, e.g. a guardian who set a password after first signing up
 * with Google, or vice versa. This is the account shape Requirement 2 exists
 * for: locked out of the password-only challenge because they usually sign
 * in via Google.
 */
function googleAndPasswordSession(userId = 'u1', email = 'guardian@example.com') {
  return {
    data: {
      session: {
        access_token: 'tok-1',
        user: {
          id: userId,
          email,
          app_metadata: { provider: 'email', providers: ['email', 'google'] },
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

/**
 * Route tree with TWO sibling gated branches (guardian-ish and admin-ish),
 * mirroring the production shape (router.tsx): one AdultGate wraps both, so
 * navigating between them must not remount the gate or re-trigger the
 * challenge once warm. This is the core requirement of ADR-014 Phase 5.
 */
function gateRoutes() {
  return (
    <Routes>
      <Route path="/previous" element={<div>Previous page</div>} />
      <Route path="/guardian" element={<div>Console home</div>} />
      <Route path="/guardian/login" element={<LoginProbe />} />
      <Route element={<AdultGate />}>
        <Route path="/gated" element={<div>Sensitive content</div>} />
        <Route path="/guardian/console" element={<div>Guardian page</div>} />
        <Route path="/admin/console" element={<div>Admin page</div>} />
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
  clearAdultGate()
  mockSignInWithPassword.mockReset()
  mockSignInWithOAuth.mockReset()
  mockSignOut.mockReset()
  mockGetSession.mockReset().mockResolvedValue(passwordSession())
  sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('AdultGate', () => {
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
    // The unlock warmed the sessionStorage-backed state for this user.
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)
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
    expect(adultGateRemainingMs('u1')).toBe(0)
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
    warmAdultGate('u1')
    renderGate()
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('stays locked when the warm entry belongs to a different user', async () => {
    warmAdultGate('someone-else')
    renderGate()
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-challenges when the TTL expires while the content is open', async () => {
    vi.useFakeTimers()
    warmAdultGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    // Exactly the TTL boundary: at now === expiresAt the warmth is gone.
    act(() => {
      vi.advanceTimersByTime(ADULT_GATE_TTL_MS)
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-locks on visibilitychange when a throttled tab slept past the TTL', async () => {
    // A backgrounded tab can throttle the scheduled setTimeout indefinitely;
    // simulate that by moving the wall clock past the TTL WITHOUT running
    // timers, then surfacing the tab.
    vi.useFakeTimers()
    warmAdultGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    vi.setSystemTime(Date.now() + ADULT_GATE_TTL_MS + 1)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('re-locks on pageshow when a bfcache restore revives expired warm state', async () => {
    vi.useFakeTimers()
    warmAdultGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    vi.setSystemTime(Date.now() + ADULT_GATE_TTL_MS + 1)
    act(() => {
      window.dispatchEvent(new Event('pageshow'))
    })

    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('stays unlocked on visibilitychange while the TTL still has time left', async () => {
    vi.useFakeTimers()
    warmAdultGate('u1')
    renderGate()
    await flushSession()

    vi.setSystemTime(Date.now() + ADULT_GATE_TTL_MS - 1000)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
  })

  it('supports a full re-lock then re-unlock cycle', async () => {
    vi.useFakeTimers()
    mockSignInWithPassword.mockResolvedValue(undefined)
    warmAdultGate('u1')
    renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(ADULT_GATE_TTL_MS + 1)
    })
    expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()

    await typePasswordAndConfirm('correct-horse')

    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
    expect(adultGateRemainingMs('u1')).toBeGreaterThan(0)
  })

  it('clears the re-lock timer on unmount', async () => {
    vi.useFakeTimers()
    warmAdultGate('u1')
    // jsdom's sessionStorage.setItem schedules its own internal timer (to fire
    // a cross-document 'storage' event) that has nothing to do with AdultGate
    // and is never cleared by unmount; flush it now so the assertions below
    // only see the gate's own re-lock timer, not this jsdom-storage artifact
    // (the pre-Phase-5 gate used module memory, not Web Storage, so it never
    // hit this).
    vi.advanceTimersByTime(0)
    const { unmount } = renderGate()
    await flushSession()
    expect(screen.getByText('Sensitive content')).toBeInTheDocument()
    expect(vi.getTimerCount()).toBeGreaterThan(0)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
  })

  it('lets an OAuth-only guardian through with a console warning, and warms the gate', async () => {
    // #ASSUME: security: documented limitation, see AdultGate.tsx: an OAuth
    // guardian has no password to re-enter and supabase-js has no client-side
    // OAuth re-auth challenge, so the gate passes them through loudly rather
    // than locking them out. Unlike the pre-Phase-5 ParentalGate, the bypass
    // also warms the gate so a later crossing is consistent for these users.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(oauthSession())
    renderGate()

    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('AdultGate'))
    expect(isAdultGateWarm('u1')).toBe(true)
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
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('AdultGate'))
  })

  it('treats a user without app_metadata as having no password identity', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockGetSession.mockResolvedValue(sessionWithUser({ id: 'u1', email: 'guardian@example.com' }))
    renderGate()
    expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('AdultGate'))
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
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('AdultGate'))
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

  it('signs out and lets a different account sign back in', async () => {
    // The gate re-authenticates the CURRENT session's owner only (no email
    // field); a guardian who needs a different account (e.g. a test account,
    // or one without a password identity) has to sign out first and go
    // through LoginPage, which supports both Google and password.
    mockSignOut.mockResolvedValue(undefined)
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: /use a different account/i }))
    await act(async () => {})

    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })

  it('shows an inline error when sign-out fails while switching accounts', async () => {
    mockSignOut.mockRejectedValue(new Error('network down'))
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: /use a different account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/sign-out failed/i)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
  })

  it('ignores a re-entrant switch-account click while one is already in flight', async () => {
    let resolveSignOut: (() => void) | undefined
    mockSignOut.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSignOut = () => resolve()
        })
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    const link = screen.getByRole('button', { name: /use a different account/i })
    fireEvent.click(link)
    fireEvent.click(link)
    fireEvent.click(link)

    expect(mockSignOut).toHaveBeenCalledTimes(1)
    resolveSignOut?.()
    await act(async () => {})
  })

  it('disables the switch-account link while a sign-out is in flight', async () => {
    let resolveSignOut: (() => void) | undefined
    mockSignOut.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSignOut = () => resolve()
        })
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    const link = screen.getByRole('button', { name: /use a different account/i })
    fireEvent.click(link)

    expect(link).toBeDisabled()
    expect(link).toHaveTextContent(/signing out/i)
    resolveSignOut?.()
    await act(async () => {})
  })

  it('disables the switch-account link while a password submit is in flight', async () => {
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

    const link = await screen.findByRole('button', { name: /use a different account/i })
    expect(link).toBeDisabled()
    fireEvent.click(link)
    expect(mockSignOut).not.toHaveBeenCalled()

    resolveSignIn?.()
    await waitFor(() => expect(screen.getByText('Sensitive content')).toBeInTheDocument())
  })

  it('disables the Confirm button while a switch-account sign-out is in flight', async () => {
    let resolveSignOut: (() => void) | undefined
    mockSignOut.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSignOut = () => resolve()
        })
    )
    renderGate()
    await screen.findByRole('heading', { name: 'Grown-ups only' })

    fireEvent.click(screen.getByRole('button', { name: /use a different account/i }))

    const confirmButton = screen.getByRole('button', { name: 'Confirm' })
    expect(confirmButton).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(confirmButton)
    expect(mockSignInWithPassword).not.toHaveBeenCalled()

    resolveSignOut?.()
    await act(async () => {})
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
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGetSession.mockRejectedValueOnce(new Error('storage exploded'))
    renderGate()

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't check/i)
    expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('AdultGate'), expect.any(Error))

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('waits for the unlock to settle before rendering anything sensitive', async () => {
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

  it('does not re-challenge navigating between two sibling gated routes once warm (core requirement)', async () => {
    // The whole point of ADR-014 Phase 5: one AdultGate at the root of the
    // adult subtree means guardian<->admin navigation is free once warm,
    // because the gate component itself never unmounts between sibling
    // routes the way the old per-page ParentalGate did.
    warmAdultGate('u1')
    render(<MemoryRouter initialEntries={['/guardian/console']}>{gateRoutes()}</MemoryRouter>)
    expect(await screen.findByText('Guardian page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Grown-ups only' })).not.toBeInTheDocument()
  })

  describe('switch-account regression (ADR-014 Phase 5)', () => {
    // The bug this phase fixes: the old ParentalGate kept warmth in module
    // memory, which a full-page reload (exactly what the switch-account OAuth
    // round-trip does) always wiped, re-prompting even for the SAME user.
    // Warmth now lives in sessionStorage, which survives a same-tab reload;
    // simulate "the page reloaded and the gate remounted" by warming
    // sessionStorage BEFORE mounting a fresh AdultGate instance, rather than
    // relying on any in-memory state carried from a previous render.

    it('stays warm across a simulated reload/remount for the SAME user', async () => {
      warmAdultGate('u1')
      mockGetSession.mockResolvedValue(passwordSession('u1'))

      const { unmount } = renderGate()
      expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
      unmount()

      // A fresh mount (simulating the reload) with the same sessionStorage
      // entry still in place and the same user's session restored.
      renderGate()
      expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Grown-ups only' })).not.toBeInTheDocument()
    })

    it('challenges again after a simulated reload/remount that returns as a DIFFERENT user', async () => {
      warmAdultGate('u1')
      mockGetSession.mockResolvedValue(passwordSession('u1'))
      const { unmount } = renderGate()
      expect(await screen.findByText('Sensitive content')).toBeInTheDocument()
      unmount()

      // The switch-account sign-out clears the warm entry (AuthContext), and
      // the new user's own sign-in warms it for THEIR id, not 'u1'. Simulate
      // the post-switch state directly: warm entry now belongs to 'u2', and
      // the restored session is for 'u2'.
      clearAdultGate()
      warmAdultGate('u2')
      mockGetSession.mockResolvedValue(passwordSession('u2', 'other@example.com'))

      renderGate()
      expect(await screen.findByText('Sensitive content')).toBeInTheDocument()

      // Sanity: had the switch NOT warmed 'u2', it would be cold.
      clearAdultGate()
      renderGate()
      expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    })
  })

  describe('idle-window activity reset (Requirement 1: 30-minute idle TTL)', () => {
    // #ASSUME: timing dependencies: ADULT_GATE_TTL_MS is an IDLE window, not
    // an absolute one: pointerdown/keydown while unlocked slides the warm
    // expiry forward (throttled to ~30s so it does not thrash sessionStorage
    // on every keystroke), and the re-lock check is a periodic poll instead
    // of a single setTimeout so it can observe an expiry that moved after the
    // effect first scheduled it.
    // #VERIFY: the three tests below (stays unlocked across throttled
    // activity, re-locks after true inactivity, throttles rapid activity).

    it('slides the idle window forward on activity, staying unlocked past the original TTL', async () => {
      vi.useFakeTimers()
      warmAdultGate('u1')
      renderGate()
      await flushSession()
      expect(screen.getByText('Sensitive content')).toBeInTheDocument()

      // Advance to just short of the original expiry.
      act(() => {
        vi.advanceTimersByTime(ADULT_GATE_TTL_MS - 1_000)
      })
      expect(screen.getByText('Sensitive content')).toBeInTheDocument()

      // Simulate a keystroke: this must re-warm and reset the idle clock.
      act(() => {
        document.dispatchEvent(new Event('pointerdown'))
      })

      // Advance by nearly the full window again. Without the reset this
      // would be almost 2x the TTL past the original expiry.
      act(() => {
        vi.advanceTimersByTime(ADULT_GATE_TTL_MS - 1_000)
      })
      expect(screen.getByText('Sensitive content')).toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Grown-ups only' })).not.toBeInTheDocument()
    })

    it('re-locks after the full idle window elapses with no activity at all', async () => {
      vi.useFakeTimers()
      warmAdultGate('u1')
      renderGate()
      await flushSession()
      expect(screen.getByText('Sensitive content')).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(ADULT_GATE_TTL_MS)
      })

      expect(screen.getByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
      expect(screen.queryByText('Sensitive content')).not.toBeInTheDocument()
    })

    it('throttles activity re-warm to at most once per ~30s', async () => {
      vi.useFakeTimers()
      vi.setSystemTime(0)
      warmAdultGate('u1', 0)
      renderGate()
      await flushSession()
      expect(screen.getByText('Sensitive content')).toBeInTheDocument()

      // Inside the 30s throttle window since mount: activity must NOT touch
      // the stored expiry.
      vi.setSystemTime(10_000)
      act(() => {
        document.dispatchEvent(new Event('pointerdown'))
      })
      expect(adultGateRemainingMs('u1', 10_000)).toBe(ADULT_GATE_TTL_MS - 10_000)

      // Once the throttle window has elapsed, the next activity DOES slide
      // the expiry forward from the current time.
      vi.setSystemTime(35_000)
      act(() => {
        document.dispatchEvent(new Event('keydown'))
      })
      expect(adultGateRemainingMs('u1', 35_000)).toBe(ADULT_GATE_TTL_MS)
    })
  })

  describe('Google re-auth on the locked screen (Requirement 2)', () => {
    it('shows a Continue with Google option for a guardian who also has a Google identity, and starts the OAuth redirect on click', async () => {
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      const googleButton = screen.getByRole('button', { name: /continue with google/i })
      expect(googleButton).toBeInTheDocument()
      // The password form must still be available too (Requirement 2 is
      // additive, not a replacement).
      expect(screen.getByLabelText('Password')).toBeInTheDocument()

      fireEvent.click(googleButton)
      await act(async () => {})

      expect(mockSignInWithOAuth).toHaveBeenCalledWith('google')
    })

    it('does not show a Google option for a password-only guardian (no linked Google identity)', async () => {
      mockGetSession.mockResolvedValue(passwordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      expect(
        screen.queryByRole('button', { name: /continue with google/i })
      ).not.toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
    })

    it('shows a connection error and re-enables the button when the OAuth redirect fails to start', async () => {
      mockSignInWithOAuth.mockRejectedValue(new Error('network down'))
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      fireEvent.click(screen.getByRole('button', { name: /continue with google/i }))
      await act(async () => {})

      expect(await screen.findByRole('alert')).toHaveTextContent(/sign-in didn.t start/i)
      expect(screen.getByRole('button', { name: /continue with google/i })).not.toBeDisabled()
    })

    it('ignores a re-entrant Google click while one is already in flight', async () => {
      let resolveOAuth: (() => void) | undefined
      mockSignInWithOAuth.mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveOAuth = () => resolve()
          })
      )
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      const googleButton = screen.getByRole('button', { name: /continue with google/i })
      fireEvent.click(googleButton)
      fireEvent.click(googleButton)
      fireEvent.click(googleButton)

      expect(mockSignInWithOAuth).toHaveBeenCalledTimes(1)
      resolveOAuth?.()
      await act(async () => {})
    })

    it('disables the password Confirm button while the Google redirect is starting', async () => {
      let resolveOAuth: (() => void) | undefined
      mockSignInWithOAuth.mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveOAuth = () => resolve()
          })
      )
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      fireEvent.click(screen.getByRole('button', { name: /continue with google/i }))

      expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
      resolveOAuth?.()
      await act(async () => {})
    })

    it('ignores a password submit (Enter in the focused input) while a Google redirect is in flight', async () => {
      // The disabled Confirm button blocks clicks, but Enter in the still-focused
      // password input submits the form directly; the submit() guard must drop
      // that so a password re-auth cannot race the in-flight OAuth redirect.
      let resolveOAuth: (() => void) | undefined
      mockSignInWithOAuth.mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveOAuth = () => resolve()
          })
      )
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
      fireEvent.click(screen.getByRole('button', { name: /continue with google/i }))

      const form = document.querySelector('form')
      if (!form) throw new Error('challenge form not rendered')
      fireEvent.submit(form)

      expect(mockSignInWithPassword).not.toHaveBeenCalled()
      resolveOAuth?.()
      await act(async () => {})
    })

    it('ignores a switch-account click while a Google redirect is in flight', async () => {
      // The disabled attribute guards the link, but the switchAccount() body
      // guard must also drop a stray activation so signOut() cannot race the
      // in-flight OAuth sign-in against the same Supabase client.
      let resolveOAuth: (() => void) | undefined
      mockSignInWithOAuth.mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveOAuth = () => resolve()
          })
      )
      mockGetSession.mockResolvedValue(googleAndPasswordSession())
      renderGate()
      await screen.findByRole('heading', { name: 'Grown-ups only' })

      fireEvent.click(screen.getByRole('button', { name: /continue with google/i }))
      fireEvent.click(screen.getByRole('button', { name: /use a different account/i }))

      expect(mockSignOut).not.toHaveBeenCalled()
      resolveOAuth?.()
      await act(async () => {})
    })
  })
})

describe('parentalGateState (adult gate warm store)', () => {
  it('honors the injectable now parameter on warm and read', () => {
    warmAdultGate('u1', 1_000)
    expect(adultGateRemainingMs('u1', 1_000)).toBe(ADULT_GATE_TTL_MS)
    expect(adultGateRemainingMs('u1', 1_000 + ADULT_GATE_TTL_MS / 2)).toBe(ADULT_GATE_TTL_MS / 2)
  })

  it('treats the exact TTL boundary (now === expiresAt) as expired', () => {
    warmAdultGate('u1', 1_000)
    expect(adultGateRemainingMs('u1', 1_000 + ADULT_GATE_TTL_MS - 1)).toBe(1)
    expect(adultGateRemainingMs('u1', 1_000 + ADULT_GATE_TTL_MS)).toBe(0)
    expect(adultGateRemainingMs('u1', 1_000 + ADULT_GATE_TTL_MS + 1)).toBe(0)
  })

  it('is cold for every user after clearAdultGate()', () => {
    warmAdultGate('u1', 1_000)
    clearAdultGate()
    expect(adultGateRemainingMs('u1', 1_000)).toBe(0)
  })

  it('is cold for every user after parkAdultGate(), same as clearAdultGate', () => {
    warmAdultGate('u1', 1_000)
    parkAdultGate()
    expect(adultGateRemainingMs('u1', 1_000)).toBe(0)
  })

  it('#CRITICAL security: warming one user does not warm a different user', () => {
    warmAdultGate('u1')
    expect(isAdultGateWarm('u1')).toBe(true)
    expect(isAdultGateWarm('u2')).toBe(false)
  })

  it('persists the warm entry in sessionStorage (survives a same-tab reload)', () => {
    warmAdultGate('u1')
    const raw = sessionStorage.getItem('cyo_adult_gate_warm')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw ?? '{}') as { userId: string; expiresAt: number }
    expect(parsed.userId).toBe('u1')
    expect(parsed.expiresAt).toBeGreaterThan(Date.now())
  })

  it('treats a corrupt sessionStorage entry as cold, not a thrown error', () => {
    sessionStorage.setItem('cyo_adult_gate_warm', 'not-json{{{')
    expect(isAdultGateWarm('u1')).toBe(false)
    expect(adultGateRemainingMs('u1')).toBe(0)
  })
})
