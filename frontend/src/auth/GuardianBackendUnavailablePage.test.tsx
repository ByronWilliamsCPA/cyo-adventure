import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianBackendUnavailablePage } from './GuardianBackendUnavailablePage'

const mockSignOut = vi.fn()
const mockRefreshStatus = vi.fn()
let mockAuth: { status: string; principal: { role: string } | null } = {
  status: 'backend-unreachable',
  principal: null,
}
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({
    ...mockAuth,
    signOut: mockSignOut,
    refreshStatus: mockRefreshStatus,
  }),
}))

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/guardian/unavailable']}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route path="/guardian/consent" element={<div>Consent page</div>} />
        <Route path="/guardian/awaiting-approval" element={<div>Awaiting approval</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route path="/guardian/unavailable" element={<GuardianBackendUnavailablePage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockSignOut.mockReset().mockResolvedValue(undefined)
  mockRefreshStatus.mockReset().mockResolvedValue(undefined)
  mockAuth = { status: 'backend-unreachable', principal: null }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('GuardianBackendUnavailablePage', () => {
  it('explains the outage in plain language and says no re-login is needed', () => {
    renderWithRouter()
    expect(screen.getByText(/isn't responding/i)).toBeInTheDocument()
    expect(screen.getByText(/do not need to sign in again/i)).toBeInTheDocument()
  })

  it('offers both a retry and an escape back to sign-in', () => {
    renderWithRouter()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to sign-in' })).toBeInTheDocument()
  })

  it('signs out on request', () => {
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Back to sign-in' }))
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })

  // The whole point of #452: once the backend answers again, a retry reaches
  // the console WITHOUT a re-login, because AuthContext kept the token on the
  // transient branch.
  it('a successful retry advances to the console with no re-login', async () => {
    mockRefreshStatus.mockImplementation(() => {
      mockAuth = { status: 'signed-in', principal: { role: 'guardian' } }
      return Promise.resolve()
    })
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(mockRefreshStatus).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByText('Guardian console')).toBeInTheDocument())
    expect(mockSignOut).not.toHaveBeenCalled()
  })

  // Still-down is the common case while the outage lasts: it must leave the
  // page usable rather than stranding the "Trying…" label or crashing.
  it('a still-failing retry leaves the page on the outage state', async () => {
    mockRefreshStatus.mockRejectedValue(new Error('still down'))
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled())
    expect(screen.getByText(/isn't responding/i)).toBeInTheDocument()
  })

  it('retries automatically in the background', async () => {
    vi.useFakeTimers()
    renderWithRouter()
    expect(mockRefreshStatus).not.toHaveBeenCalled()
    // Same Vitest constraint GuardianAwaitingApprovalPage.test.tsx documents:
    // Testing Library's fake-timer detection keys off a `jest` global, so
    // waitFor cannot advance faked timers here. Drive the flush explicitly.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(mockRefreshStatus).toHaveBeenCalledTimes(1)
  })

  // #ASSUME timing (spec 5): the poll is bounded. An abandoned tab must not
  // keep hitting a downed host forever, but the manual escape must survive
  // the cap, or a long outage would make the page a dead end.
  it('stops auto-retrying after the cap, leaving the manual button live', async () => {
    vi.useFakeTimers()
    renderWithRouter()
    await act(async () => {
      // 20 intervals' worth of time against a cap of 15.
      await vi.advanceTimersByTimeAsync(20_000 * 20)
    })
    expect(mockRefreshStatus).toHaveBeenCalledTimes(15)
    expect(screen.getByText(/stopped checking automatically/i)).toBeInTheDocument()

    const button = screen.getByRole('button', { name: 'Try again' })
    expect(button).toBeEnabled()
    act(() => {
      fireEvent.click(button)
    })
    expect(mockRefreshStatus).toHaveBeenCalledTimes(16)
  })

  // #ASSUME timing (spec 5): clearInterval in the effect teardown is what
  // stops a tick from firing into an unmounted tree.
  it('does not retry after unmount', async () => {
    vi.useFakeTimers()
    const { unmount } = renderWithRouter()
    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000 * 3)
    })
    expect(mockRefreshStatus).not.toHaveBeenCalled()
  })

  // The route sits outside ProtectedRoute, so every other status can arrive
  // here by direct URL. Each must be sent somewhere sensible rather than
  // shown an outage message that does not apply.
  it('redirects a signed-out visitor to login', () => {
    mockAuth = { status: 'signed-out', principal: null }
    renderWithRouter()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects an approval-pending guardian to the awaiting-approval page', () => {
    mockAuth = { status: 'awaiting-approval', principal: null }
    renderWithRouter()
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument()
  })

  it('redirects a consent-pending guardian to the consent page', () => {
    mockAuth = { status: 'needs-consent', principal: null }
    renderWithRouter()
    expect(screen.getByText('Consent page')).toBeInTheDocument()
  })

  it('redirects a signed-in guardian to their console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'guardian' } }
    renderWithRouter()
    expect(screen.getByText('Guardian console')).toBeInTheDocument()
  })

  it('redirects a signed-in admin to the admin console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'admin' } }
    renderWithRouter()
    expect(screen.getByText('Admin console')).toBeInTheDocument()
  })

  it('renders nothing while auth status is still loading', () => {
    mockAuth = { status: 'loading', principal: null }
    const { container } = renderWithRouter()
    expect(container).toBeEmptyDOMElement()
  })
})
